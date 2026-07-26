"""FTP, Data Table, and Email executors (with mockable adapters)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.workflows.expression import ExpressionContext, evaluate, evaluate_deep
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


def _cred(ctx: EngineContext, node: ExecNode, cred_type: str) -> dict[str, Any]:
    return ctx.resolve_credential(node, cred_type) or {}


def _ectx(item: ExecutionItem, ctx: EngineContext) -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


# ── FTP ──────────────────────────────────────────────────────────────


async def exec_ftp(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    operation = str(params.get("operation") or "download")
    cred = _cred(ctx, node, "ftp")

    # Mock filesystem from ctx.mocks (path -> bytes|str)
    mock_fs: dict[str, bytes] | None = None
    if ctx.mocks and "ftp_files" in ctx.mocks:
        raw_fs = ctx.mocks["ftp_files"]
        if isinstance(raw_fs, dict):
            mock_fs = {
                str(k): (v if isinstance(v, bytes) else str(v).encode("utf-8"))
                for k, v in raw_fs.items()
            }

    if operation == "list":
        path = str(params.get("path") or "/")
        entries = _ftp_list(path, cred, mock_fs)
        return [(0, [ExecutionItem(json=e) for e in entries])]

    # download
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        path = str(evaluate(params.get("path"), ectx) or item.json.get("path") or "")
        data, name = _ftp_download(path, cred, mock_fs)
        ni = item.clone()
        ni.json = {
            **item.json,
            "path": path,
            "name": name or item.json.get("name") or path.rsplit("/", 1)[-1],
        }
        ni.binary = {
            "data": BinaryFile.from_bytes(
                data,
                file_name=ni.json["name"],
                mime_type="text/csv" if str(ni.json["name"]).endswith(".csv") else "application/octet-stream",
            )
        }
        out.append(ni)
    return [(0, out)]


def _ftp_list(
    path: str,
    cred: dict[str, Any],
    mock_fs: dict[str, bytes] | None,
) -> list[dict[str, Any]]:
    if mock_fs is not None:
        prefix = path.rstrip("/") + "/"
        seen: dict[str, dict[str, Any]] = {}
        for p in mock_fs:
            if p.startswith(prefix) or p.startswith(path):
                name = p.rsplit("/", 1)[-1]
                seen[name] = {"name": name, "path": p, "type": "file", "size": len(mock_fs[p])}
            elif "/" not in p.strip("/") and path in ("/", ""):
                seen[p] = {"name": p, "path": p, "type": "file", "size": len(mock_fs[p])}
        # also match exact keys under path
        for p, data in mock_fs.items():
            name = p.rsplit("/", 1)[-1]
            parent = p.rsplit("/", 1)[0] if "/" in p else ""
            if parent == path.rstrip("/") or p.startswith(path.rstrip("/") + "/"):
                seen[name] = {"name": name, "path": p if p.startswith("/") else f"{path.rstrip('/')}/{name}", "type": "file", "size": len(data)}
        if seen:
            return list(seen.values())
        # flat mock: all files
        return [
            {
                "name": (p.rsplit("/", 1)[-1]),
                "path": p if p.startswith("/") else f"{path.rstrip('/')}/{p}",
                "type": "file",
                "size": len(b),
            }
            for p, b in mock_fs.items()
        ]

    host = cred.get("host") or cred.get("server")
    if not host:
        raise RuntimeError("FTP credential missing host (or provide mocks.ftp_files for dry-run)")
    # Real FTP via ftplib
    from ftplib import FTP, error_perm

    port = int(cred.get("port") or 21)
    user = str(cred.get("user") or cred.get("username") or "anonymous")
    password = str(cred.get("password") or cred.get("pass") or "")
    entries: list[dict[str, Any]] = []
    with FTP() as ftp:
        ftp.connect(host, port, timeout=30)
        ftp.login(user, password)
        try:
            ftp.cwd(path)
        except error_perm:
            pass
        for name, facts in ftp.mlsd():
            entries.append(
                {
                    "name": name,
                    "path": f"{path.rstrip('/')}/{name}",
                    "type": facts.get("type", "file"),
                    "size": int(facts.get("size") or 0),
                }
            )
    return entries


def _ftp_download(
    path: str,
    cred: dict[str, Any],
    mock_fs: dict[str, bytes] | None,
) -> tuple[bytes, str]:
    name = path.rsplit("/", 1)[-1]
    if mock_fs is not None:
        if path in mock_fs:
            return mock_fs[path], name
        # try by basename
        for k, v in mock_fs.items():
            if k.endswith(name) or k == name:
                return v, name
        raise FileNotFoundError(f"Mock FTP file not found: {path}")

    from ftplib import FTP
    from io import BytesIO

    host = cred.get("host") or cred.get("server")
    if not host:
        raise RuntimeError("FTP credential missing host")
    port = int(cred.get("port") or 21)
    user = str(cred.get("user") or cred.get("username") or "anonymous")
    password = str(cred.get("password") or cred.get("pass") or "")
    buf = BytesIO()
    with FTP() as ftp:
        ftp.connect(host, port, timeout=60)
        ftp.login(user, password)
        ftp.retrbinary(f"RETR {path}", buf.write)
    return buf.getvalue(), name


# ── Data Table ───────────────────────────────────────────────────────


async def exec_data_table(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    resource = str(params.get("resource") or "row")
    operation = str(params.get("operation") or "insert")
    store = ctx.data_tables  # name -> {"schema": [], "rows": [dict]}

    def _table_name() -> str:
        tid = params.get("dataTableId") or params.get("tableName")
        if isinstance(tid, dict):
            # Prefer human name (cachedResultName) over opaque n8n id
            cached = tid.get("cachedResultName")
            mode = str(tid.get("mode") or "")
            val = tid.get("value")
            if mode == "name" and val:
                return str(val)
            if cached:
                return str(cached)
            if val:
                return str(val)
        if tid:
            return str(tid)
        return str(params.get("tableName") or "temp_table")

    if resource == "table" or operation in ("create", "delete", "getMany") or (
        params.get("resource") == "table"
    ):
        # list tables
        if params.get("resource") == "table" and not params.get("operation"):
            return [
                (
                    0,
                    [
                        ExecutionItem(json={"name": n, "id": n})
                        for n in sorted(store.keys())
                    ],
                )
            ]
        if operation == "create" or (params.get("resource") == "table" and params.get("operation") == "create"):
            name = str(params.get("tableName") or _table_name())
            cols = params.get("columns") or {}
            schema = []
            if isinstance(cols, dict) and isinstance(cols.get("schema"), list):
                schema = cols["schema"]
            store[name] = {"schema": schema, "rows": []}
            return [(0, [ExecutionItem(json={"name": name, "id": name})])]
        if operation == "delete" or (
            params.get("resource") == "table" and params.get("operation") == "delete"
        ):
            name = _table_name()
            store.pop(name, None)
            # also pop by id alias
            return [(0, [ExecutionItem(json={"deleted": name})])]

    # row ops
    name = _table_name()
    if operation == "get" or params.get("operation") == "get":
        table = store.get(name) or {"rows": []}
        return [(0, [ExecutionItem(json=dict(r)) for r in table.get("rows", [])])]

    # insert (default)
    table = store.setdefault(name, {"schema": [], "rows": []})
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        cols = params.get("columns") or {}
        row: dict[str, Any] = {}
        if isinstance(cols, dict) and isinstance(cols.get("value"), dict):
            for k, v in cols["value"].items():
                row[k] = evaluate(v, ectx)
        else:
            row = dict(item.json)
        row.setdefault("id", str(uuid4()))
        table["rows"].append(row)
        out.append(ExecutionItem(json=dict(row)))
    return [(0, out)]


# ── SSH ──────────────────────────────────────────────────────────────


async def exec_ssh(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """``n8n-nodes-base.ssh`` executor — v1 supports ``executeCommand``.

    Reads ``parameters.command`` (string or ``={{ ... }}``) and optional
    ``parameters.cwd``; emits one item per call with
    ``{stdout, stderr, exitCode, command}``.

    Behavior precedence:

    1. ``ctx.mocks['ssh']`` (dict keyed by command → ``{stdout, stderr,
       exitCode}``) — used in tests and dry-runs.
    2. Real SSH via :mod:`asyncssh` when installed and credentials supply
       a host. Falls back to a clear ``RuntimeError`` otherwise so the
       engine can report a sensible failure instead of silently timing
       out.

    Credentials are resolved from ``ctx.credentials`` keyed by:

    - ``ssh`` — username/password (also accepts ``sshPassword``)
    - ``sshPrivateKey`` — private key auth (with optional ``passphrase``)
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or "executeCommand")
    if operation != "executeCommand":
        raise ValueError(
            f"ssh: unsupported operation {operation!r} "
            "(v1 only supports 'executeCommand')"
        )

    mock_ssh: dict[str, Any] | None = None
    if ctx.mocks and isinstance(ctx.mocks.get("ssh"), dict):
        mock_ssh = ctx.mocks["ssh"]

    cred = _cred(ctx, node, "ssh") or _cred(ctx, node, "sshPassword") or {}
    if not cred:
        cred = _cred(ctx, node, "sshPrivateKey") or {}

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        command = str(evaluate(params.get("command"), ectx) or "")
        cwd_raw = params.get("cwd")
        cwd = str(evaluate(cwd_raw, ectx)) if cwd_raw is not None else ""

        if not command:
            raise ValueError(
                f"ssh: missing parameters.command on node {node.name!r}"
            )

        result = await _ssh_run(
            command=command,
            cwd=cwd,
            cred=cred,
            mock_ssh=mock_ssh,
        )

        ni = item.clone()
        ni.json = {
            **item.json,
            "command": command,
            "cwd": cwd,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "exitCode": result["exitCode"],
        }
        out.append(ni)
        logger.info(
            "ssh executeCommand cmd=%r exitCode=%s",
            command[:120],
            result["exitCode"],
        )
    return [(0, out)]


async def _ssh_run(
    *,
    command: str,
    cwd: str,
    cred: dict[str, Any],
    mock_ssh: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run a single SSH command and return ``{stdout, stderr, exitCode}``.

    Mock lookup is by exact command match, then by basename-key
    (e.g. ``"ls"`` matches ``"ls -la /tmp"``) for convenience.
    """
    if mock_ssh is not None:
        if command in mock_ssh and isinstance(mock_ssh[command], dict):
            entry = mock_ssh[command]
            return {
                "stdout": str(entry.get("stdout") or ""),
                "stderr": str(entry.get("stderr") or ""),
                "exitCode": int(entry.get("exitCode") or 0),
            }
        # basename fallback for dry-runs: key like "ls" matches "ls -la"
        head = command.split(None, 1)[0] if command else ""
        if head and head in mock_ssh and isinstance(mock_ssh[head], dict):
            entry = mock_ssh[head]
            return {
                "stdout": str(entry.get("stdout") or ""),
                "stderr": str(entry.get("stderr") or ""),
                "exitCode": int(entry.get("exitCode") or 0),
            }
        # mocked but no entry — fail loud so the test notices
        raise RuntimeError(
            f"ssh: mock present but no entry for command {command!r}"
        )

    host = cred.get("host") or cred.get("server") or cred.get("hostname")
    if not host:
        raise RuntimeError(
            "ssh: no mock and no credential host "
            "(set ctx.mocks['ssh'] or provide an 'ssh' / 'sshPrivateKey' "
            "credential with a host)"
        )

    # Defer the asyncssh import + real call to the async executor so we
    # can `await` it cleanly without juggling event loops.
    return await _ssh_real_run(command=command, cwd=cwd, cred=cred)


async def _ssh_real_run(
    *, command: str, cwd: str, cred: dict[str, Any]
) -> dict[str, Any]:
    """Open a real SSH connection via :mod:`asyncssh` and run ``command``.

    Raises :class:`RuntimeError` if :mod:`asyncssh` is not installed or
    the credential is missing required fields (username, password or
    private key). The caller must already have verified that no mock is
    in effect and that a host was supplied.
    """
    try:
        import asyncssh  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "ssh: no mock and asyncssh not installed "
            "(install asyncssh or set ctx.mocks['ssh'] for dry-runs)"
        ) from exc

    host = str(cred.get("host") or cred.get("server") or cred.get("hostname") or "")
    port = int(cred.get("port") or 22)
    user = str(cred.get("user") or cred.get("username") or "")
    password = str(cred.get("password") or cred.get("pass") or "")
    private_key = str(
        cred.get("privateKey") or cred.get("key") or cred.get("keyData") or ""
    )
    passphrase = str(cred.get("passphrase") or "")

    if not user:
        raise RuntimeError("ssh: credential missing username")
    if not password and not private_key:
        raise RuntimeError(
            "ssh: credential missing both password and privateKey"
        )

    connect_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": user,
        "known_hosts": None,
    }
    if private_key:
        connect_kwargs["client_keys"] = [private_key]
        if passphrase:
            connect_kwargs["passphrase"] = passphrase
    else:
        connect_kwargs["password"] = password

    async with asyncssh.connect(**connect_kwargs) as conn:
        full_cmd = command if not cwd else f"cd {cwd} && {command}"
        completed = await conn.run(full_cmd, check=False)
        return {
            "stdout": (completed.stdout or ""),
            "stderr": (completed.stderr or ""),
            "exitCode": int(completed.exit_status or 0),
        }


# ── Email ────────────────────────────────────────────────────────────


async def exec_email_send(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    cred = _cred(ctx, node, "smtp")
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        from_email = str(evaluate(params.get("fromEmail"), ectx) or cred.get("fromEmail") or "")
        to_email = str(evaluate(params.get("toEmail"), ectx) or "")
        subject = str(evaluate(params.get("subject"), ectx) or "")
        text = str(evaluate(params.get("text"), ectx) or "")
        html = str(evaluate(params.get("html"), ectx) or "")

        record = {
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "text": text[:500],
            "html_len": len(html),
            "sent": False,
        }

        if ctx.mocks and ctx.mocks.get("capture_email"):
            ctx.mocks.setdefault("sent_emails", []).append(
                {
                    "from": from_email,
                    "to": to_email,
                    "subject": subject,
                    "text": text,
                    "html": html,
                }
            )
            record["sent"] = True
            record["mock"] = True
        else:
            host = cred.get("host") or cred.get("server")
            if not host:
                # dry-run without SMTP: capture
                ctx.mocks = ctx.mocks or {}
                ctx.mocks.setdefault("sent_emails", []).append(
                    {
                        "from": from_email,
                        "to": to_email,
                        "subject": subject,
                        "text": text,
                        "html": html,
                    }
                )
                record["sent"] = True
                record["mock"] = True
            else:
                port = int(cred.get("port") or 587)
                user = str(cred.get("user") or cred.get("username") or "")
                password = str(cred.get("password") or "")
                msg = EmailMessage()
                msg["From"] = from_email
                msg["To"] = to_email
                msg["Subject"] = subject
                if html and text:
                    msg.set_content(text)
                    msg.add_alternative(html, subtype="html")
                elif html:
                    msg.set_content(html, subtype="html")
                else:
                    msg.set_content(text)
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    if cred.get("secure") or port == 465:
                        pass
                    smtp.starttls()
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
                record["sent"] = True

        ni = item.clone()
        ni.json = {**item.json, "emailResult": record}
        out.append(ni)
        logger.info("emailSend to=%s subject=%s", to_email, subject)
    return [(0, out)]
