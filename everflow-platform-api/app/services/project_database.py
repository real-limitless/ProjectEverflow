"""Project database introspection via sandbox exec (psql + .everflow/database.json)."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

DATABASE_JSON_PATH = ".everflow/database.json"
DEFAULT_ROW_LIMIT = 100

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"copy\s+|execute|refresh\s+materialized|reindex|vacuum|"
    r"set\s+role|set\s+session)\b",
    re.IGNORECASE,
)


@dataclass
class DbConfig:
    database_url: str | None
    engine: str | None
    file_status: str | None
    file_message: str | None
    harness_marker: bool


def mask_database_url(url: str) -> str:
    """Mask password in a postgres URL for display."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return url
        netloc = parsed.netloc
        if "@" in netloc:
            userinfo, host = netloc.rsplit("@", 1)
            if ":" in userinfo:
                user, _pw = userinfo.split(":", 1)
                userinfo = f"{user}:***"
            else:
                userinfo = f"{userinfo}:***" if userinfo else "***"
            netloc = f"{userinfo}@{host}"
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
    except Exception:
        return "postgres://***"


def assert_readonly_select(sql: str) -> str:
    """Validate SQL is a single read-only SELECT (or WITH … SELECT). Return cleaned SQL."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("Empty SQL")
    # Reject multiple statements
    if ";" in cleaned:
        raise ValueError("Only a single SELECT statement is allowed")
    # Strip block/line comments for keyword checks
    no_block = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    compact = " ".join(no_line.split())
    upper = compact.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH") or upper.startswith("SHOW") or upper.startswith("EXPLAIN")):
        raise ValueError("Only read-only SELECT / WITH / SHOW / EXPLAIN queries are allowed")
    if _FORBIDDEN_SQL.search(compact):
        raise ValueError("Query contains forbidden keywords (read-only SELECT only)")
    return cleaned


async def _read_text(client: SandboxAgentClient, sandbox_name: str, path: str) -> str | None:
    try:
        return await client.read_fs(sandbox_name, path)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            return None
        # Older sandbox-agents returned 500 for missing guest files (ENOENT).
        body = (exc.body or str(exc) or "").lower()
        if exc.status_code and exc.status_code >= 500 and (
            "no such file" in body or "os error 2" in body
        ):
            return None
        raise


async def load_db_config(client: SandboxAgentClient, sandbox_name: str) -> DbConfig:
    raw = await _read_text(client, sandbox_name, DATABASE_JSON_PATH)
    harness_marker = False
    boot = await _read_text(client, sandbox_name, ".everflow/bootstrapped")
    if boot and ("db-postgres" in boot or "postgres" in boot):
        harness_marker = True

    if not raw:
        return DbConfig(
            database_url=None,
            engine=None,
            file_status="not_provisioned",
            file_message=(
                "No .everflow/database.json yet. Enable the db-postgres harness "
                "(bootstrap) or create the file with a database_url."
            ),
            harness_marker=harness_marker,
        )

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return DbConfig(
            database_url=None,
            engine=None,
            file_status="error",
            file_message="Invalid JSON in .everflow/database.json",
            harness_marker=harness_marker,
        )

    url = data.get("database_url") or data.get("url") or data.get("DATABASE_URL")
    url_s = str(url).strip() if url else None
    return DbConfig(
        database_url=url_s or None,
        engine=str(data.get("engine") or "postgres") if data.get("engine") or url_s else None,
        file_status=str(data.get("status") or "").strip() or None,
        file_message=str(data.get("message") or "").strip() or None,
        harness_marker=harness_marker,
    )


async def _exec(
    client: SandboxAgentClient,
    sandbox_name: str,
    *,
    cmd: str,
    args: list[str],
    env: dict[str, str] | None = None,
    timeout_seconds: float = 30,
) -> tuple[int, str, str]:
    result = await client.exec(
        sandbox_name,
        cmd=cmd,
        args=args,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    return (
        int(result.get("exit_code", 1)),
        str(result.get("stdout") or ""),
        str(result.get("stderr") or ""),
    )


async def check_psql(client: SandboxAgentClient, sandbox_name: str) -> bool:
    code, _out, _err = await _exec(client, sandbox_name, cmd="sh", args=["-c", "command -v psql"])
    return code == 0


async def probe_connection(
    client: SandboxAgentClient,
    sandbox_name: str,
    database_url: str,
) -> tuple[bool, str]:
    """Return (ok, message)."""
    code, out, err = await _exec(
        client,
        sandbox_name,
        cmd="psql",
        args=[database_url, "-v", "ON_ERROR_STOP=1", "-tAc", "SELECT 1"],
        env={"PGCONNECT_TIMEOUT": "5"},
        timeout_seconds=15,
    )
    if code == 0 and "1" in out:
        return True, "Connected"
    detail = (err or out or "connection failed").strip()
    return False, detail[:500]


async def get_status(client: SandboxAgentClient, sandbox_name: str) -> dict[str, Any]:
    cfg = await load_db_config(client, sandbox_name)
    psql_ok = await check_psql(client, sandbox_name)

    if not cfg.database_url:
        return {
            "status": "not_provisioned",
            "engine": cfg.engine,
            "display_url": None,
            "psql_available": psql_ok,
            "message": cfg.file_message
            or "Set DATABASE_URL / database_url in .everflow/database.json",
            "harness_installed": cfg.harness_marker,
        }

    display = mask_database_url(cfg.database_url)
    if not psql_ok:
        return {
            "status": "error",
            "engine": cfg.engine or "postgres",
            "display_url": display,
            "psql_available": False,
            "message": (
                "postgresql-client (psql) is not installed in the sandbox. "
                "Re-run bootstrap with the db-postgres harness."
            ),
            "harness_installed": cfg.harness_marker,
        }

    ok, msg = await probe_connection(client, sandbox_name, cfg.database_url)
    if ok:
        return {
            "status": "ready",
            "engine": cfg.engine or "postgres",
            "display_url": display,
            "psql_available": True,
            "message": cfg.file_message or "Postgres reachable",
            "harness_installed": cfg.harness_marker or True,
        }

    # Config present but server not up — treat as not_provisioned when sample URL / marker says so
    status = "unreachable"
    if cfg.file_status == "not_provisioned":
        status = "not_provisioned"
    return {
        "status": status,
        "engine": cfg.engine or "postgres",
        "display_url": display,
        "psql_available": True,
        "message": (
            cfg.file_message
            or f"Cannot connect with psql: {msg}. "
            "Start Postgres or set a reachable DATABASE_URL in .everflow/database.json."
        ),
        "harness_installed": cfg.harness_marker,
    }


def _parse_csv(stdout: str) -> tuple[list[str], list[list[str]]]:
    text = stdout.strip()
    if not text:
        return [], []
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    columns = rows[0]
    data = rows[1:] if len(rows) > 1 else []
    return columns, data


async def list_tables(client: SandboxAgentClient, sandbox_name: str) -> dict[str, Any]:
    status = await get_status(client, sandbox_name)
    if status["status"] != "ready":
        return {
            "tables": [],
            "status": status["status"],
            "message": status.get("message"),
        }

    cfg = await load_db_config(client, sandbox_name)
    assert cfg.database_url

    sql = (
        "SELECT n.nspname AS schema_name, c.relname AS name, "
        "COALESCE(s.n_live_tup::bigint, 0) AS rows, "
        "pg_size_pretty(pg_total_relation_size(c.oid)) AS size "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid "
        "WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY n.nspname, c.relname"
    )
    code, out, err = await _exec(
        client,
        sandbox_name,
        cmd="psql",
        args=[cfg.database_url, "-v", "ON_ERROR_STOP=1", "--csv", "-c", sql],
        env={"PGCONNECT_TIMEOUT": "5"},
        timeout_seconds=30,
    )
    if code != 0:
        return {
            "tables": [],
            "status": "error",
            "message": (err or out or "Failed to list tables").strip()[:500],
        }

    columns, data = _parse_csv(out)
    # Expected: schema_name,name,rows,size
    tables: list[dict[str, Any]] = []
    for row in data:
        if len(row) < 2:
            continue
        # Map by header when possible
        if columns and len(columns) >= 4:
            mapping = dict(zip(columns, row, strict=False))
            name = mapping.get("name") or row[1]
            schema = mapping.get("schema_name") or row[0]
            rows_raw = mapping.get("rows") or (row[2] if len(row) > 2 else None)
            size = mapping.get("size") or (row[3] if len(row) > 3 else None)
        else:
            schema, name = row[0], row[1]
            rows_raw = row[2] if len(row) > 2 else None
            size = row[3] if len(row) > 3 else None
        try:
            rows_n = int(float(rows_raw)) if rows_raw not in (None, "") else None
        except (TypeError, ValueError):
            rows_n = None
        tables.append(
            {
                "name": name,
                "schema_name": schema or "public",
                "rows": rows_n,
                "size": size,
            }
        )

    return {"tables": tables, "status": "ready", "message": None}


async def run_query(
    client: SandboxAgentClient,
    sandbox_name: str,
    sql: str,
    *,
    limit: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    try:
        cleaned = assert_readonly_select(sql)
    except ValueError as exc:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": str(exc),
        }

    status = await get_status(client, sandbox_name)
    if status["status"] != "ready":
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": status.get("message") or f"Database not ready ({status['status']})",
        }

    cfg = await load_db_config(client, sandbox_name)
    assert cfg.database_url

    # Wrap SELECT/WITH in a subquery with LIMIT when not already limited.
    upper = cleaned.upper()
    is_selectish = upper.startswith("SELECT") or upper.startswith("WITH")
    if is_selectish and " LIMIT " not in f" {upper} ":
        wrapped = f"SELECT * FROM ({cleaned}) AS _ef_q LIMIT {int(limit)}"
    else:
        wrapped = cleaned

    code, out, err = await _exec(
        client,
        sandbox_name,
        cmd="psql",
        args=[cfg.database_url, "-v", "ON_ERROR_STOP=1", "--csv", "-c", wrapped],
        env={"PGCONNECT_TIMEOUT": "5"},
        timeout_seconds=60,
    )
    if code != 0:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": (err or out or "Query failed").strip()[:800],
        }

    columns, data = _parse_csv(out)
    truncated = len(data) >= limit
    if truncated:
        data = data[:limit]
    return {
        "columns": columns,
        "rows": data,
        "row_count": len(data),
        "truncated": truncated,
        "error": None,
    }
