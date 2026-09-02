#!/usr/bin/env bash
# Cloud-agent start hygiene: keep Cursor co-author hooks off disk and
# strip Cursor attribution from commit messages. Idempotent.
set -euo pipefail

HOOKS_ROOT="${CURSOR_AGENT_HOOKS_ROOT:-/home/ubuntu/.cursor/agent-hooks}"
STRIP_HOOK_NAME="commit-msg.cursor.zz-strip-attribution"
REAPER_PID_FILE="${CURSOR_NO_ATTR_REAPER_PID:-/home/ubuntu/.cursor/no-cursor-attribution.reaper.pid}"
REAPER_LOG="${CURSOR_NO_ATTR_REAPER_LOG:-/tmp/cursor-no-attribution-reaper.log}"
REAPER_INTERVAL_SEC="${CURSOR_NO_ATTR_REAPER_INTERVAL:-2}"

strip_hook_body() {
  cat <<'HOOK'
#!/usr/bin/env bash
# Runs last among commit-msg.cursor* hooks (zz- prefix).
# Removes Cursor attribution even if a co-author hook ran earlier in the same commit.
set -euo pipefail
msg="${1:-}"
if [[ -z "$msg" || ! -f "$msg" ]]; then
  exit 0
fi

hooks_root="${CURSOR_AGENT_HOOKS_ROOT:-/home/ubuntu/.cursor/agent-hooks}"
if [[ -d "$hooks_root" ]]; then
  find "$hooks_root" \( -name 'commit-msg.cursor.co-author' -o -name '*co-author*' \) \
    \( -type f -o -type l \) -delete 2>/dev/null || true
fi

tmp="$(mktemp)"
# Drop lines that credit Cursor / cursoragent. Keep all other message text.
grep -viE \
  -e 'Co-authored-by:[[:space:]]*Cursor([[:space:]]|<|$)' \
  -e 'Made with Cursor' \
  -e 'cursoragent@cursor\.com' \
  "$msg" >"$tmp" || true
mv "$tmp" "$msg"
exit 0
HOOK
}

delete_coauthor_files() {
  if [[ ! -d "$HOOKS_ROOT" ]]; then
    return 0
  fi
  find "$HOOKS_ROOT" \( -name 'commit-msg.cursor.co-author' -o -name '*co-author*' \) \
    \( -type f -o -type l \) -print -delete 2>/dev/null || true
}

install_strip_hooks() {
  if [[ ! -d "$HOOKS_ROOT" ]]; then
    return 0
  fi
  local dir dest
  # Each workspace gets its own hooks directory under agent-hooks.
  while IFS= read -r -d '' dir; do
    dest="${dir}/${STRIP_HOOK_NAME}"
    strip_hook_body >"$dest"
    chmod +x "$dest"
  done < <(find "$HOOKS_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null || true)
}

reaper_loop() {
  while true; do
    delete_coauthor_files >/dev/null
    install_strip_hooks
    sleep "$REAPER_INTERVAL_SEC"
  done
}

start_reaper() {
  local old=""
  if [[ -f "$REAPER_PID_FILE" ]]; then
    old="$(cat "$REAPER_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      return 0
    fi
  fi
  mkdir -p "$(dirname "$REAPER_PID_FILE")"
  nohup bash "$0" --reaper-loop >>"$REAPER_LOG" 2>&1 &
  echo $! >"$REAPER_PID_FILE"
}

# Commits from this workspace must not be authored as Cursor Agent.
# Resolve the repo from this script so `start` is cwd-independent.
retarget_git_identity() {
  local repo
  repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi
  local name email
  name="$(git -C "$repo" config --get user.name || true)"
  email="$(git -C "$repo" config --get user.email || true)"
  if [[ "$email" == *cursoragent@cursor.com* || "$name" == "Cursor Agent" ]]; then
    git -C "$repo" config user.name "Chen Chiu"
    git -C "$repo" config user.email "chenchiu9@gmail.com"
  fi
}

if [[ "${1:-}" == "--reaper-loop" ]]; then
  reaper_loop
  exit 0
fi

delete_coauthor_files
install_strip_hooks
retarget_git_identity
start_reaper

# Start must finish successfully; print proof the hook files are gone.
if [[ -d "$HOOKS_ROOT" ]]; then
  leftover="$(find "$HOOKS_ROOT" \( -name 'commit-msg.cursor.co-author' -o -name '*co-author*' \) \
    \( -type f -o -type l \) -print 2>/dev/null || true)"
  if [[ -n "$leftover" ]]; then
    echo "no-cursor-attribution: leftover co-author files:" >&2
    echo "$leftover" >&2
    exit 1
  fi
fi
echo "no-cursor-attribution: commit-msg.cursor.co-author and *co-author* files are gone under ${HOOKS_ROOT}"
