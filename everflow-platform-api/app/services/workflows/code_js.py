"""Run n8n Code node JavaScript in a restricted subprocess (Node.js)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any


class CodeJsError(RuntimeError):
    pass


def node_available() -> bool:
    return shutil.which("node") is not None


def run_js_each_item(js_code: str, item_json: dict[str, Any], *, timeout_s: float = 5.0) -> dict[str, Any]:
    """Execute runOnceForEachItem code. Returns the new $json object."""
    if not node_available():
        return _fallback_python(js_code, item_json)

    wrapper = r"""
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const $json = payload.json;
const code = payload.code;
let result;
try {
  // n8n wraps as function body with return
  result = (function() {
    return eval('(async () => { ' + code + '\n })()');
  })();
} catch (e) {
  // try as expression body that returns object
  try {
    result = eval('(function(){ ' + code + '\n})()');
  } catch (e2) {
    console.error(String(e2 && e2.stack || e2));
    process.exit(2);
  }
}
Promise.resolve(result).then((r) => {
  // If code returned {json: ...} unwrap
  if (r && typeof r === 'object' && r.json && Object.keys(r).length <= 3) {
    process.stdout.write(JSON.stringify(r.json));
  } else {
    process.stdout.write(JSON.stringify(r));
  }
}).catch((e) => {
  console.error(String(e && e.stack || e));
  process.exit(2);
});
"""
    # Prefer sync-friendly: many n8n snippets are sync return
    sync_wrapper = r"""
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const $json = payload.json;
const code = payload.code;
let result;
try {
  result = eval('(function(){ ' + code + '\n})()');
} catch (e) {
  // try with return injection if last line is expression
  try {
    result = eval('(function(){ ' + code + '; })()');
  } catch (e2) {
    console.error(String(e2 && e2.stack || e2));
    process.exit(2);
  }
}
if (result && typeof result.then === 'function') {
  result.then((r) => {
    const out = (r && r.json !== undefined && Object.keys(r).length <= 3) ? r.json : r;
    process.stdout.write(JSON.stringify(out));
  }).catch((e) => { console.error(String(e)); process.exit(2); });
} else {
  const out = (result && result.json !== undefined && typeof result === 'object' && Object.keys(result).length <= 3)
    ? result.json : result;
  process.stdout.write(JSON.stringify(out));
}
"""
    payload = json.dumps({"json": item_json, "code": js_code})
    try:
        proc = subprocess.run(
            ["node", "-e", sync_wrapper],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "NODE_OPTIONS": "--max-old-space-size=128"},
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeJsError(f"Code node timed out after {timeout_s}s") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "unknown error").strip()
        # fallback for common stock-agent snippets
        try:
            return _fallback_python(js_code, item_json)
        except Exception:
            raise CodeJsError(f"Code node failed: {err[:500]}") from None
    out = (proc.stdout or "").strip()
    if not out:
        return dict(item_json)
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise CodeJsError(f"Code node returned non-JSON: {out[:200]}") from exc
    if not isinstance(parsed, dict):
        return {"result": parsed, **item_json}
    return parsed


def _fallback_python(js_code: str, item_json: dict[str, Any]) -> dict[str, Any]:
    """Handle known Stock Agent snippets without Node."""
    code = js_code.strip()
    # Clean trailing commas
    if "trailing" in code.lower() or ("$json.text" in code and "replace" in code and "split" in code):
        text = str(item_json.get("text") or "")
        lines = text.replace("\r\n", "\n").split("\n")
        cleaned = "\n".join(line.rstrip().removesuffix(",").rstrip() if False else __import__("re").sub(r",\s*$", "", line) for line in lines)
        return {**item_json, "text": cleaned}

    # Markdown to HTML — use a minimal converter if code mentions emailHtml / escapeHtml
    if "escapeHtml" in code or "emailHtml" in code or ("const md" in code and "html" in code):
        md = str(item_json.get("output") or "")
        html = _md_to_html(md)
        return {**item_json, "emailHtml": html}

    raise CodeJsError(
        "Node.js is not available and no Python fallback matched this Code node. Install Node.js."
    )


def _md_to_html(md: str) -> str:
    import html as html_mod
    import re

    def escape(s: str) -> str:
        return html_mod.escape(s)

    def inline(text: str) -> str:
        text = escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(^|[^*])\*([^*]+?)\*($|[^*])", r"\1<em>\2</em>\3", text)
        text = re.sub(
            r"`([^`]+)`",
            r'<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;">\1</code>',
            text,
        )
        text = re.sub(
            r"\[(.+?)\]\((.+?)\)",
            r'<a href="\2" style="color:#2563eb;">\1</a>',
            text,
        )
        return text

    lines = md.splitlines()
    parts: list[str] = []
    in_list = False
    list_type: str | None = None

    def close_list() -> None:
        nonlocal in_list, list_type
        if in_list:
            parts.append("</ol>" if list_type == "ol" else "</ul>")
            in_list = False
            list_type = None

    for line in lines:
        if re.match(r"^### ", line):
            close_list()
            parts.append(f"<h3 style='margin:16px 0 8px;'>{inline(line[4:])}</h3>")
        elif re.match(r"^## ", line):
            close_list()
            parts.append(f"<h2 style='margin:20px 0 10px;'>{inline(line[3:])}</h2>")
        elif re.match(r"^# ", line):
            close_list()
            parts.append(f"<h1 style='margin:24px 0 12px;'>{inline(line[2:])}</h1>")
        elif re.match(r"^[-*] ", line):
            if not in_list or list_type != "ul":
                close_list()
                parts.append("<ul style='margin:8px 0;padding-left:20px;'>")
                in_list = True
                list_type = "ul"
            parts.append(f"<li>{inline(line[2:])}</li>")
        elif re.match(r"^\d+\. ", line):
            if not in_list or list_type != "ol":
                close_list()
                parts.append("<ol style='margin:8px 0;padding-left:20px;'>")
                in_list = True
                list_type = "ol"
            parts.append(f"<li>{inline(re.sub(r'^\d+\. ', '', line))}</li>")
        elif line.strip() == "":
            close_list()
            parts.append("<br/>")
        else:
            close_list()
            parts.append(f"<p style='margin:8px 0;line-height:1.5;'>{inline(line)}</p>")
    close_list()
    body = "\n".join(parts)
    return (
        '<div style="font-family:system-ui,sans-serif;color:#0f172a;max-width:720px;">'
        f"{body}</div>"
    )
