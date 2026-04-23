# Backend Python Codebase Analysis Report

**Analysis Date:** 2026-04-23  
**Codebase Location:** #backend (recursively analyzed)  
**Total Python Files Reviewed:** 96  
**Overall Risk Assessment:** Critical  
**Executive Summary**  
The analyzed backend is a Django 5.1 / Django REST Framework / Channels application with a large `api/` module, Podman-based workspace orchestration, proxying for per-project services, and a LangGraph-based agent subsystem. The codebase shows several good foundational choices, including ORM-centric data access, password validators, JWT authentication defaults, and encrypted storage for LLM provider API keys.

The most serious findings are concentrated in the workspace/proxy/orchestration paths rather than the CRUD API surface. The highest-risk issues are: (1) path traversal in workspace file endpoints, (2) shell command injection paths in workspace build and agent command execution flows, (3) JWTs deliberately transported in query strings / injected into HTML, and (4) insecure deployment defaults such as a hardcoded bootstrap admin password plus permissive Django defaults. These findings create realistic paths to arbitrary file access, token leakage, and command execution in environments where user-controlled compose files or tool commands are accepted.

Maintainability is also a concern. The backend contains a very large `views.py`, many broad exception handlers, extensive `print()`-based debugging in production-facing code paths, and at least one clearly broken/dead method body in `workspace_file_views.py`. Remediation effort is moderate-to-high because the highest-risk issues sit in cross-cutting infrastructure components, but the affected areas are identifiable and can be prioritized in a staged hardening pass.

## 1. Project Structure & Technology Stack
- **Framework / platform:** Django 5.1.3, Django REST Framework 3.15.2, Channels 4, SimpleJWT, django-cors-headers
- **Agent / AI stack:** LangGraph, LangChain Core / Community, LangChain OpenAI / Anthropic, MCP, Qdrant, sentence-transformers
- **Infrastructure / runtime:** Podman-based workspace orchestration, Daphne ASGI server, SQLite dev database, `Containerfile`
- **Key config / entry points:** `backend/manage.py`, `backend/backend/settings.py`, `backend/backend/asgi.py`, `backend/backend/urls.py`, `backend/requirements.txt`, `backend/Containerfile`, `backend/llm_config.json`

```text
backend/
├── manage.py
├── requirements.txt
├── Containerfile
├── backend/                 # Django project package
│   ├── settings.py
│   ├── asgi.py
│   └── urls.py
├── api/                     # Main application
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── consumers.py
│   ├── *_proxy*.py
│   ├── workspace_file_views.py
│   ├── podman_*.py
│   ├── frameworks/langgraph/
│   ├── management/commands/
│   └── migrations/
└── workspace-images/agent/
    └── agent_service.py
```

- **Python file distribution:** `backend/api` (89), `backend/backend` (5), `backend/workspace-images/agent` (1), plus `manage.py`
- **Testing footprint:** one backend test module found: `backend/api/tests.py`

## 2. Security Vulnerabilities
| Severity | File:Line | CWE/OWASP | Description | Evidence (code snippet) | Potential Impact |
|----------|-----------|-----------|-------------|-------------------------|------------------|
| Critical | `backend/api/workspace_file_views.py:207-223` | CWE-22 / OWASP A01 | Workspace file endpoints trust a string-prefix check without normalizing `..`, so `/workspace/../...` paths still pass the guard and are sent to the container shell. The same pattern is reused for create/update/delete. | `filepath = filepath.lstrip('/')`<br>`full_path = f'/workspace/{filepath}'`<br>`if not full_path.startswith('/workspace/')`<br>`cmd = f"cat '{safe_path}'"` | Arbitrary file read/write/delete inside the workspace container; exposure of secrets, source, SSH keys, or service credentials. |
| Critical | `backend/api/workspace_initializer.py:359-374` | CWE-78 / OWASP A03 | Build metadata from compose parsing is interpolated directly into a shell pipeline and executed with `shell=True`. `image`, `target`, `dockerfile`, and build args are derived from parsed service definitions. | `build_args_str = ' '.join(f"--build-arg {k}={v}" for k, v in build_args.items())`<br>`pipeline_cmd = ( ... f"{self.podman} build -t {image} {target_str} {build_args_str} {dockerfile_str} -" )`<br>`subprocess.run(pipeline_cmd, shell=True, ...)` | Command injection during workspace/image provisioning; potential arbitrary command execution on the host running the backend. |
| High | `backend/workspace-images/agent/agent_service.py:283-299` | CWE-78 / OWASP A03 | Agent command validation only checks the first token, then executes the original string through the shell. Shell metacharacters after an allowed command remain dangerous. | `parts = shlex.split(command)`<br>`cmd_name = parts[0]`<br>`if cmd_name not in allowed_commands:`<br>`result = subprocess.run(command, shell=True, cwd=str(WORKSPACE_ROOT), ...)` | Chained-command injection in the in-container agent service, enabling unauthorized file access or command execution. |
| High | `backend/Containerfile:37-39` | CWE-798 / OWASP A07 | The container entrypoint auto-creates an `admin` superuser with a hardcoded fallback password. | `User.objects.create_superuser('admin', 'admin@example.com', '${DJANGO_SUPERUSER_PASSWORD:-admin123}', role='admin')` | Default credential exposure, easy privilege escalation in dev/staging, and high risk of password reuse leaking into production-like environments. |
| High | `backend/api/proxy_views.py:153-185` | CWE-598 / OWASP A07 | JWTs are injected into browser-visible WebSocket URLs. Related code also accepts tokens from query parameters and propagates `_auth_token` in redirect URLs. | `token = (query_dict.get('token') or [None])[0]`<br>`const token = '{token}';`<br>`url = url + separator + 'token=' + token;` | Tokens can leak via browser history, logs, Referer headers, screenshots, and client-side scripts. |
| High | `backend/api/subdomain_proxy.py:145-160`<br>`backend/api/subdomain_proxy.py:275-278` | CWE-598 / OWASP A07 | The subdomain proxy explicitly reads `_auth_token` from URLs / Referer and appends it back to redirect targets. | `token = request.GET.get('_auth_token')`<br>`if not token and '_auth_token=' in referer:`<br>`final_url = f"{redirect_path}?_auth_token={token}"` | Session/JWT disclosure across iframe navigation and downstream requests. |
| Medium | `backend/backend/settings.py:24-29` | CWE-798, CWE-16 / OWASP A05 | Security-sensitive Django defaults are unsafe if this configuration is deployed as-is: fallback secret key, `DEBUG=True` by default, and wildcard hosts. | `SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')`<br>`DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'`<br>`ALLOWED_HOSTS = ['*']` | Secret reuse, verbose error disclosure, host-header abuse, and accidental insecure production deployment. |
| Medium | `backend/api/channels_auth.py:52-54`<br>`backend/api/consumers.py:778-780` | CWE-532 / OWASP A09 | Sensitive request data is logged directly, including token prefixes, raw query strings, headers, and WS metadata. | `print(f"[JWTAuth] Found token in query string: {token[:20]}...")`<br>`print(f"[JWTAuth] No token in query string. Query: {query_string.decode() ...}")`<br>`print(f"[LangGraphStream] Scope headers: {headers}")` | Token / cookie leakage into logs and observability systems. |

Targeted searches did **not** find high-confidence uses of `eval()`, `exec()`, `pickle.loads()`, or raw SQL execution. The codebase relies primarily on Django ORM and serializers for persistence.

## 3. Duplicate Code
- **Location 1:** `backend/api/workspace_file_views.py:273-308`
- **Location 2:** `backend/api/workspace_file_views.py:352-375`
- **Similarity:** ~90%
- **Impact:** `create_file` and `update_file` duplicate the same temp-file / `podman cp` / cleanup workflow, increasing the chance that security fixes land in only one path.

Excerpt 1:
```python
mkdir_cmd = f"mkdir -p '{safe_dir}'"
...
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as tmp:
    tmp.write(content)
    tmp_path = tmp.name
```

Excerpt 2:
```python
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as tmp:
    tmp.write(content)
    tmp_path = tmp.name
...
copy_result = orchestrator._run(['cp', tmp_path, f'{container_name}:{full_path}'])
```

- **Location 1:** `backend/api/channels_auth.py:46-63`
- **Location 2:** `backend/api/service_proxy_views.py:45-63`
- **Location 3:** `backend/backend/asgi.py:360-380`
- **Similarity:** ~80%
- **Impact:** Token extraction / authentication logic is reimplemented in several places with different logging and transport decisions, which contributes directly to the inconsistent URL-token handling noted above.

Excerpt 1:
```python
if not token:
    query_string = scope.get('query_string') or b''
    qs = parse_qs(query_string.decode())
    token = (qs.get('token') or [None])[0]
```

Excerpt 2:
```python
if not token:
    token = request.GET.get('token')
...
META = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
```

## 4. Orphaned / Unused Code
- **Dead / broken method body:** `backend/api/workspace_file_views.py:429-440` defines `get_git_status`, but the implementation stops immediately after `result = self._execute_in_container(...)` and the remaining parsing logic is stranded after `return StreamingHttpResponse(...)` at `backend/api/workspace_file_views.py:744-790`. That code is unreachable in its current location.
- **Unrouted endpoint logic:** `backend/api/workspace_file_views.py:624-744` defines `analyze_stream`, but `backend/api/urls.py:57-75` does not register any `analyze-stream` route and the method lacks an `@action` decorator. It appears to be zombie code.
- **Ambiguous legacy module:** `backend/api/frameworks/langgraph/workers.py` duplicates worker-factory names now also exported by the `backend/api/frameworks/langgraph/workers/` package. Current imports resolve through the package-style `from .workers import ...` sites in `agent.py` and `graph.py`, so the standalone module appears legacy/superseded and is a maintenance trap.

## 5. Code Injection Risks
- **Shell-backed build pipeline:** `backend/api/workspace_initializer.py:364-374` constructs a full shell command from user-controlled build metadata and runs it with `shell=True`.
- **Shell-backed agent tool:** `backend/workspace-images/agent/agent_service.py:283-299` validates only the first token before invoking `subprocess.run(command, shell=True, ...)`.
- **Weak command validation in portable backend:** `backend/api/frameworks/langgraph/portable/__init__.py:49-64` only allow-lists the first token, and `backend/api/frameworks/langgraph/portable/__init__.py:289-292` forwards the full string to a shell-backed execution path. This is weaker than a strict argv-based allow-list and is prone to bypass via shell operators.
- **Unsafe token injection into client-side script:** `backend/api/proxy_views.py:160-185` embeds raw token material directly into generated JavaScript and rewrites WebSocket URLs on the fly.

## 6. Other Issues & Maintainability Concerns
- **Error Handling:** 196 broad `except:` / `except Exception:` handlers were found across 34 Python files. `backend/api/views.py` alone contains 50 such handlers, which makes failure modes hard to reason about and can hide security-relevant errors.
- **Logging / observability:** 171 `print()` calls were found across the backend, including ASGI tunnel code, auth middleware, proxy consumers, and agent flows. Production-facing networking code should not rely on ad hoc stdout logging.
- **Monolithic modules:** `backend/api/views.py` is a large god-module with multiple long methods, including `_call_provider_api` (`2987-3166`, 180 lines) and `stream` (`3415-3589`, 175 lines). `backend/api/frameworks/langgraph/tools.py:get_workspace_tools` spans ~300 lines.
- **Async / sync complexity:** Several async proxy paths mix direct prints, sync Django ORM calls via wrappers, long inline control flow, and networking logic in the same method (`backend/api/consumers.py`, `backend/backend/asgi.py`, `backend/api/service_proxy_views.py`), which increases operational fragility.
- **Testing depth:** Only one backend test module (`backend/api/tests.py`) was found, and it is focused on CRUD / authorization behavior. High-risk proxy, workspace, ASGI, and agent command paths do not appear to have dedicated tests in-tree.

## 7. Positive Findings & Good Practices
- **No significant issues found in this category.**  
  More specifically:
  - The backend mostly uses Django ORM / DRF serializers rather than raw SQL, reducing SQL injection exposure.
  - Django password validators are enabled in `backend/backend/settings.py:96-109`.
  - Default DRF permissioning is set to authenticated access in `backend/backend/settings.py:169-177`.
  - LLM provider secrets are encrypted with Fernet in `backend/api/models.py:525-543`.
  - The serializer intentionally masks API keys and keeps plaintext input write-only in `backend/api/serializers.py:521-579`.
  - `backend/api/frameworks/langgraph/portable/__init__.py:39-46` includes a proper normalized path validator; that pattern is a good baseline for the workspace file API to emulate consistently.
  - `backend/api/compose_parser.py:161-163` explicitly rejects bind mounts, which is a positive containment choice for multi-tenant workspaces.

## 8. Prioritized Remediation Plan
### Immediate (Critical / High - do first)
1. Eliminate path traversal in `workspace_file_views.py` by normalizing and enforcing canonical paths before every read/write/delete operation.
2. Remove all `shell=True` command construction that incorporates compose metadata or agent/user command strings; switch to argv-based execution and strict allow-lists.
3. Stop transporting JWTs in query strings, redirect URLs, Referer-dependent flows, or injected HTML/JS.
4. Remove the hardcoded admin bootstrap password and require explicit secure provisioning for privileged accounts.

### Short-term (Medium)
2. Make Django production-safe by default: no fallback secret key, no default `DEBUG=True`, and no wildcard `ALLOWED_HOSTS`.
3. Replace token / header `print()` statements with structured, redacted logging.
4. Repair `get_git_status`, remove unreachable code, and either wire up or delete `analyze_stream`.

### Long-term (Architectural / Low priority)
3. Break up `api/views.py`, centralize proxy/auth/token handling, and converge duplicate worker / workspace helper logic into shared utilities.
4. Add automated coverage for workspace file APIs, proxy auth flows, ASGI WebSocket handling, and agent command execution boundaries.
5. Review the LangGraph/agent subsystem for a stricter tool-execution contract that never hands raw shell strings to the runtime.

## 9. Conclusion & Next Steps
This backend has a solid Django/DRF foundation, but the infrastructure-oriented code paths introduce materially higher risk than the standard API layer. The combination of path traversal, shell injection opportunities, and URL-based token handling is sufficient to rate the current backend as **Critical** from a real-world attack-surface perspective.

The highest-value next step is a focused security hardening sprint centered on workspace file handling, build orchestration, and proxy authentication. After those fixes land, the project should be re-audited specifically against CWE-22, CWE-78, and token-transport/logging issues to verify that the most exploitable paths are closed.
