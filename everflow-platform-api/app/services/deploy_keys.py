"""Generate and encrypt deploy SSH keys via sandbox ssh-keygen + Fernet."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from app.config import Settings, get_settings
from app.services.credential_crypto import decrypt_secret, encrypt_secret
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

# Under /workspace so mock + guest FS APIs can read the material before cleanup.
_KEY_DIR = "/workspace/.everflow/deploy-keys"
_FINGERPRINT_RE = re.compile(r"(SHA256:[A-Za-z0-9+/=]+)")


def encrypt_private_key(private_key: str, settings: Settings | None = None) -> str:
    ciphertext, _nonce = encrypt_secret(private_key, settings)
    return ciphertext


def decrypt_private_key(ciphertext: str, settings: Settings | None = None) -> str:
    return decrypt_secret(ciphertext, settings=settings)


def _exit_code(res: dict[str, Any] | None) -> int:
    if not res:
        return 1
    code = res.get("exit_code")
    if code is None:
        return 1
    return int(code)


def _parse_fingerprint(stdout: str) -> str:
    m = _FINGERPRINT_RE.search(stdout or "")
    if m:
        return m.group(1)
    # Fallback: first non-empty token after bit length (ssh-keygen -lf format)
    for line in (stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1].startswith("SHA256:"):
            return parts[1]
    raise ValueError(f"Could not parse SSH fingerprint from: {stdout!r}")


async def generate_ssh_keypair_in_sandbox(
    client: SandboxAgentClient,
    sandbox_name: str,
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Run ssh-keygen in the sandbox; return public_key, private_key, fingerprint."""
    del settings  # reserved if we later need settings for key path policy
    key_id = uuid4().hex[:12]
    key_path = f"{_KEY_DIR}/{key_id}"
    pub_path = f"{key_path}.pub"

    mkdir = await client.exec(
        sandbox_name,
        cmd="mkdir",
        args=["-p", _KEY_DIR],
        timeout_seconds=30,
    )
    if _exit_code(mkdir) != 0:
        err = (mkdir.get("stderr") or mkdir.get("stdout") or "mkdir failed").strip()
        raise SandboxAgentError(f"Failed to prepare key directory: {err}", status_code=500)

    gen = await client.exec(
        sandbox_name,
        cmd="ssh-keygen",
        args=[
            "-t",
            "ed25519",
            "-f",
            key_path,
            "-N",
            "",
            "-C",
            "everflow-deploy",
            "-q",
        ],
        timeout_seconds=60,
    )
    if _exit_code(gen) != 0:
        err = (gen.get("stderr") or gen.get("stdout") or "ssh-keygen failed").strip()
        raise SandboxAgentError(f"ssh-keygen failed: {err}", status_code=500)

    try:
        public_key = (await client.read_fs(sandbox_name, pub_path)).strip()
        private_key = await client.read_fs(sandbox_name, key_path)
        if not public_key or not private_key.strip():
            raise SandboxAgentError("ssh-keygen produced empty key material", status_code=500)

        fp_res = await client.exec(
            sandbox_name,
            cmd="ssh-keygen",
            args=["-lf", pub_path],
            timeout_seconds=30,
        )
        if _exit_code(fp_res) != 0:
            err = (fp_res.get("stderr") or fp_res.get("stdout") or "fingerprint failed").strip()
            raise SandboxAgentError(f"Failed to read fingerprint: {err}", status_code=500)
        fingerprint = _parse_fingerprint(str(fp_res.get("stdout") or ""))
    finally:
        # Best-effort cleanup of plaintext keys in the sandbox tmp dir.
        try:
            await client.exec(
                sandbox_name,
                cmd="rm",
                args=["-f", key_path, pub_path],
                timeout_seconds=15,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to clean up temporary deploy key files in sandbox")

    return {
        "public_key": public_key if public_key.endswith("\n") else public_key + "\n",
        "private_key": private_key if private_key.endswith("\n") else private_key + "\n",
        "fingerprint": fingerprint,
    }


async def discover_compose_files(
    client: SandboxAgentClient,
    sandbox_name: str,
) -> list[str]:
    """Find compose*.yml / docker-compose*.yml under /workspace."""
    res = await client.exec(
        sandbox_name,
        cmd="find",
        args=[
            "/workspace",
            "-type",
            "f",
            "(",
            "-name",
            "compose*.yml",
            "-o",
            "-name",
            "compose*.yaml",
            "-o",
            "-name",
            "docker-compose*.yml",
            "-o",
            "-name",
            "docker-compose*.yaml",
            ")",
        ],
        timeout_seconds=60,
    )
    # find returns 0 even with no matches; non-zero often means path missing
    stdout = str(res.get("stdout") or "")
    stderr = str(res.get("stderr") or "")
    if _exit_code(res) != 0 and "No such file" not in stderr:
        logger.info("compose find exited %s: %s", res.get("exit_code"), stderr.strip())
    files: list[str] = []
    for line in stdout.splitlines():
        path = line.strip()
        if path:
            files.append(path)
    # Prefer shorter / more conventional names first
    files.sort(key=lambda p: (p.count("/"), p))
    return files
