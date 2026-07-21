"""Discover listening TCP ports inside a sandbox (mock host or guest microVM).

Guest images are minimal — they often lack `ss`/`netstat`. We therefore prefer
`/proc/net/tcp` (+ tcp6), which is always available on Linux guests.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

ExecFn = Callable[..., Awaitable[tuple[int, str, str]]]

# Harness / internal ports we hide from the Preview "app" dropdown by default.
DEFAULT_EXCLUDED_PORTS: frozenset[int] = frozenset(
    {
        22,  # ssh
        4096,  # OpenCode guest default
        # OpenCode host range starts at 14100; hide a wide band of harness ports
        *range(14100, 14200),
    }
)

# Process name hints that are usually HTTP-ish.
_HTTP_PROCESS_HINTS = (
    "node",
    "nodejs",
    "vite",
    "next",
    "next-server",
    "python",
    "python3",
    "uvicorn",
    "gunicorn",
    "nginx",
    "caddy",
    "httpd",
    "apache",
    "ruby",
    "puma",
    "rails",
    "php",
    "deno",
    "bun",
    "go",
    "java",
    "dotnet",
    "webpack",
    "parcel",
)

# TCP state 0A = LISTEN in /proc/net/tcp
_TCP_LISTEN = 0x0A


@dataclass(frozen=True)
class ListeningPort:
    port: int
    address: str
    protocol: str = "tcp"
    process: str | None = None
    http_likely: bool = False
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "address": self.address,
            "protocol": self.protocol,
            "process": self.process,
            "http_likely": self.http_likely,
            "label": self.label or _default_label(self.port, self.process),
        }


def _default_label(port: int, process: str | None) -> str:
    if process:
        return f"{process} :{port}"
    return f":{port}"


def _http_likely(process: str | None, port: int) -> bool:
    if process:
        pl = process.lower()
        for hint in _HTTP_PROCESS_HINTS:
            if hint in pl:
                return True
    # Common dev/web ports
    if port in (
        80,
        443,
        3000,
        3001,
        4000,
        4173,
        5000,
        5173,
        8000,
        8080,
        8081,
        8765,
        8888,
        9000,
    ):
        return True
    # Unprivileged ports with no process name: still treat as preview candidates
    # (user just started a server; better to show than hide).
    if process is None and 1024 <= port <= 65535:
        return True
    return False


_SS_LINE = re.compile(
    r"^(?P<proto>tcp|tcp6)\s+\S+\s+\S+\s+(?P<local>\S+)\s+\S+(?:\s+users:\(\((?P<users>.*)\)\))?",
    re.IGNORECASE,
)
_ADDR_PORT = re.compile(r"^(?P<addr>.+):(?P<port>\d+)$")
_PROC_NAME = re.compile(r'"([^"]+)"')


def parse_ss_output(text: str) -> list[ListeningPort]:
    """Parse `ss -lntH` or `ss -lntpH` style output into ListeningPort rows."""
    found: dict[int, ListeningPort] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("state") or line.lower().startswith("netid"):
            continue
        # Skip non-LISTEN rows when state column is present
        parts = line.split()
        if not parts:
            continue
        if parts[0].upper() == "LISTEN" or parts[0].lower() in ("tcp", "tcp6"):
            pass
        elif "LISTEN" not in line.upper() and not re.search(r":\d+", line):
            continue

        local = None
        proto = "tcp"
        users = ""
        m = _SS_LINE.match(line)
        if m:
            proto = m.group("proto").lower().replace("tcp6", "tcp")
            local = m.group("local")
            users = m.group("users") or ""
        else:
            for i, tok in enumerate(parts):
                if ":" in tok and re.search(r":\d+$", tok):
                    local = tok
                    if i > 0 and parts[0].lower() in ("tcp", "tcp6", "udp", "udp6"):
                        proto = parts[0].lower().replace("tcp6", "tcp").replace("udp6", "udp")
                    break
            if "users:(" in line:
                users = line.split("users:(", 1)[-1].rstrip(")")

        if not local:
            continue
        ap = _ADDR_PORT.match(local)
        if not ap:
            if ":" not in local:
                continue
            addr, _, port_s = local.rpartition(":")
            try:
                port = int(port_s)
            except ValueError:
                continue
        else:
            addr = ap.group("addr")
            port = int(ap.group("port"))

        if port <= 0 or port > 65535:
            continue

        process = None
        if users:
            pm = _PROC_NAME.search(users)
            if pm:
                process = pm.group(1)

        _merge_port(
            found,
            ListeningPort(
                port=port,
                address=addr,
                protocol=proto if proto.startswith("tcp") else "tcp",
                process=process,
                http_likely=_http_likely(process, port),
                label=_default_label(port, process),
            ),
        )

    return sorted(found.values(), key=lambda p: p.port)


def parse_proc_net_tcp(text: str, *, ipv6: bool = False) -> list[ListeningPort]:
    """Parse Linux `/proc/net/tcp` or `/proc/net/tcp6` for LISTEN sockets.

    local_address is hex IP:port (IPv4 little-endian host order).
    st == 0A means LISTEN.
    """
    found: dict[int, ListeningPort] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("sl "):
            continue
        # Format: " 0: 0100007F:1F90 00000000:0000 0A ..."
        # Drop leading "N:" index if present
        parts = line.split()
        if len(parts) < 4:
            continue
        # parts[0] may be "0:" or just local if already split oddly
        if parts[0].endswith(":") and len(parts[0]) <= 4:
            local_hex = parts[1]
            state_hex = parts[3]
        else:
            local_hex = parts[0] if ":" in parts[0] else parts[1]
            state_hex = parts[2] if parts[0].endswith(":") else parts[3]

        try:
            st = int(state_hex, 16)
        except ValueError:
            continue
        if st != _TCP_LISTEN:
            continue

        try:
            addr, port = _decode_proc_local(local_hex, ipv6=ipv6)
        except ValueError:
            continue
        if port <= 0 or port > 65535:
            continue

        _merge_port(
            found,
            ListeningPort(
                port=port,
                address=addr,
                protocol="tcp",
                process=None,
                http_likely=_http_likely(None, port),
                label=_default_label(port, None),
            ),
        )

    return sorted(found.values(), key=lambda p: p.port)


def _decode_proc_local(local_hex: str, *, ipv6: bool = False) -> tuple[str, int]:
    if ":" not in local_hex:
        raise ValueError("bad local_hex")
    ip_h, port_h = local_hex.rsplit(":", 1)
    port = int(port_h, 16)
    if ipv6:
        # 32 hex chars = 16 bytes, little-endian 32-bit words
        if len(ip_h) != 32:
            # compressed / unexpected — still return port with wildcard
            return ("::", port)
        words = [ip_h[i : i + 8] for i in range(0, 32, 8)]
        # each word is little-endian
        parts: list[str] = []
        for w in words:
            b = bytes.fromhex(w)
            parts.append(f"{b[3]:02x}{b[2]:02x}:{b[1]:02x}{b[0]:02x}")
        # simplify common cases
        joined = ":".join(parts)
        if all(c in "0:" for c in joined):
            return ("::", port)
        if joined.startswith("0000:0000:0000:0000:0000:0000:0000:"):
            # v4-mapped-ish — keep simple
            return ("::", port)
        return (joined, port)

    # IPv4: 8 hex digits, little-endian
    if len(ip_h) != 8:
        raise ValueError("bad ipv4 hex")
    b = bytes.fromhex(ip_h)
    addr = f"{b[3]}.{b[2]}.{b[1]}.{b[0]}"
    return (addr, port)


def _addr_rank(addr: str) -> int:
    a = addr.strip("[]").lower()
    if a in ("*", "0.0.0.0", "::", "::0"):
        return 3
    if a in ("127.0.0.1", "::1", "localhost"):
        return 1
    return 2


def _merge_port(found: dict[int, ListeningPort], entry: ListeningPort) -> None:
    existing = found.get(entry.port)
    if existing is None:
        found[entry.port] = entry
        return
    # Prefer wildcard bind + richer process name
    process = entry.process or existing.process
    addr = entry.address if _addr_rank(entry.address) >= _addr_rank(existing.address) else existing.address
    found[entry.port] = ListeningPort(
        port=entry.port,
        address=addr,
        protocol=entry.protocol,
        process=process,
        http_likely=_http_likely(process, entry.port),
        label=_default_label(entry.port, process),
    )


async def list_listening_ports(
    exec_fn: ExecFn,
    sandbox_name: str,
    *,
    cwd: str = "/workspace",
    exclude: frozenset[int] | None = None,
    probe_http: bool = False,
) -> list[ListeningPort]:
    """Discover listening TCP ports inside the sandbox."""
    exclude = DEFAULT_EXCLUDED_PORTS if exclude is None else exclude
    found: dict[int, ListeningPort] = {}

    # 1) Prefer /proc/net/tcp — always present on Linux guests (no iproute2 needed)
    for path, ipv6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        try:
            code, out, err = await exec_fn(
                sandbox_name,
                "cat",
                [path],
                cwd=cwd,
                env=None,
                timeout_seconds=10,
            )
        except KeyError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("port scan cat %s failed name=%s: %s", path, sandbox_name, exc)
            continue
        if code != 0 or not (out or "").strip():
            logger.debug(
                "port scan cat %s weak name=%s code=%s err=%s",
                path,
                sandbox_name,
                code,
                (err or "")[:200],
            )
            continue
        for p in parse_proc_net_tcp(out, ipv6=ipv6):
            _merge_port(found, p)

    # 2) Optionally enrich with ss (process names) when iproute2 is installed.
    # Many guest images omit `ss`; missing binaries can raise from the runtime —
    # only probe once via `command -v` and never block discovery on failure.
    ss_available = False
    try:
        code, out, _err = await exec_fn(
            sandbox_name,
            "sh",
            ["-c", "command -v ss >/dev/null 2>&1 && echo yes || echo no"],
            cwd=cwd,
            env=None,
            timeout_seconds=5,
        )
        ss_available = code == 0 and "yes" in (out or "")
    except KeyError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("ss availability check failed name=%s: %s", sandbox_name, exc)

    if ss_available:
        for cmd, args in (
            ("ss", ["-lntpH"]),
            ("ss", ["-lntH"]),
            ("ss", ["-lnt"]),
        ):
            try:
                code, out, err = await exec_fn(
                    sandbox_name,
                    cmd,
                    args,
                    cwd=cwd,
                    env=None,
                    timeout_seconds=10,
                )
            except KeyError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("port scan exec failed name=%s cmd=%s: %s", sandbox_name, cmd, exc)
                continue
            if code == 127 or not (out or "").strip():
                continue
            for p in parse_ss_output(out):
                _merge_port(found, p)
            break

    ports = [p for p in sorted(found.values(), key=lambda x: x.port) if p.port not in exclude]

    if probe_http and ports:
        ports = await _probe_http(exec_fn, sandbox_name, ports, cwd=cwd)

    return ports


async def _probe_http(
    exec_fn: ExecFn,
    sandbox_name: str,
    ports: list[ListeningPort],
    *,
    cwd: str,
) -> list[ListeningPort]:
    """Optional HEAD/GET probe to mark http_likely (best-effort, short timeout)."""
    out: list[ListeningPort] = []
    for p in ports:
        if p.http_likely:
            out.append(p)
            continue
        script = (
            "import urllib.request\n"
            f"url='http://127.0.0.1:{p.port}/'\n"
            "try:\n"
            "  r=urllib.request.urlopen(url,timeout=0.8)\n"
            "  print('ok', getattr(r,'status',200))\n"
            "except Exception as e:\n"
            "  import urllib.error\n"
            "  if isinstance(e, urllib.error.HTTPError):\n"
            "    print('ok', e.code)\n"
            "  else:\n"
            "    print('no')\n"
        )
        try:
            code, stdout, _ = await exec_fn(
                sandbox_name,
                "python3",
                ["-c", script],
                cwd=cwd,
                env=None,
                timeout_seconds=3,
            )
            likely = code == 0 and "ok" in (stdout or "")
        except Exception:  # noqa: BLE001
            likely = False
        if likely:
            out.append(
                ListeningPort(
                    port=p.port,
                    address=p.address,
                    protocol=p.protocol,
                    process=p.process,
                    http_likely=True,
                    label=p.label,
                )
            )
        else:
            out.append(p)
    return out
