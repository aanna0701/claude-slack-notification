#!/usr/bin/env bash
# Claude Code Slack Notification — One-command installer
# Usage: bash install.sh

set -euo pipefail

HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERR]${RESET}  $*" >&2; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
check_prerequisites() {
  info "Prerequisites 확인 중..."

  if ! command -v python3 &>/dev/null; then
    error "Python 3가 필요합니다. 설치 후 다시 실행하세요."
    exit 1
  fi

  PY_VER=$(python3 -c "import sys; print(sys.version_info.minor)")
  if [[ "$PY_VER" -lt 10 ]]; then
    error "Python 3.10 이상이 필요합니다. (현재: 3.$PY_VER)"
    exit 1
  fi

  success "Python $(python3 --version) 확인됨"
}

# ── Config ────────────────────────────────────────────────────────────────────
collect_config() {
  echo ""
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}  Claude Code → Slack 알림 설정${RESET}"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""

  CONFIG_FILE="$HOOKS_DIR/slack_config.json"

  # 이미 설정 파일이 있으면 덮어쓸지 확인
  if [[ -f "$CONFIG_FILE" ]]; then
    warn "기존 설정 파일이 있습니다: $CONFIG_FILE"
    printf "덮어쓰시겠습니까? [y/N] "; read -r OVERWRITE
    if [[ "$OVERWRITE" != "y" && "$OVERWRITE" != "Y" ]]; then
      info "기존 설정을 유지합니다."
      return
    fi
  fi

  echo "Slack Bot Token (xoxb-...):"
  printf "  > "; read -r BOT_TOKEN
  echo ""

  echo "Slack 채널 ID (C...) — Slack 채널 URL의 마지막 부분:"
  printf "  > "; read -r CHANNEL_ID
  echo ""

  if [[ -z "$BOT_TOKEN" || -z "$CHANNEL_ID" ]]; then
    error "토큰과 채널 ID를 모두 입력해야 합니다."
    exit 1
  fi

  cat > "$CONFIG_FILE" <<EOF
{
  "bot_token": "$BOT_TOKEN",
  "channel_id": "$CHANNEL_ID"
}
EOF

  success "설정 파일 저장됨: $CONFIG_FILE"
}

# ── Copy hooks ────────────────────────────────────────────────────────────────
install_hooks() {
  info "Hook 파일 설치 중..."
  mkdir -p "$HOOKS_DIR"

  for hook in slack_buffer.py slack_stop.py slack_notify.py; do
    cp "$SCRIPT_DIR/hooks/$hook" "$HOOKS_DIR/$hook"
    chmod +x "$HOOKS_DIR/$hook"
    success "설치됨: $HOOKS_DIR/$hook"
  done
}

# ── Patch settings.json ───────────────────────────────────────────────────────
patch_settings() {
  info "settings.json에 hooks 등록 중..."

  mkdir -p "$(dirname "$SETTINGS_FILE")"

  # settings.json이 없으면 빈 객체로 생성
  if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "{}" > "$SETTINGS_FILE"
    info "settings.json 신규 생성됨"
  fi

  # Python으로 JSON 안전하게 머지
  python3 - <<'PYEOF'
import json, os, sys

settings_path = os.path.expanduser("~/.claude/settings.json")
hooks_dir = os.path.expanduser("~/.claude/hooks")

with open(settings_path) as f:
    settings = json.load(f)

new_hooks = {
    "PostToolUse": [
        {
            "matcher": "Edit|Write|NotebookEdit|Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {hooks_dir}/slack_buffer.py"
                }
            ]
        }
    ],
    "Notification": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {hooks_dir}/slack_notify.py"
                }
            ]
        }
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {hooks_dir}/slack_stop.py"
                }
            ]
        }
    ]
}

existing_hooks = settings.get("hooks", {})

def merge_hook_list(existing: list, new_entries: list, match_key: str) -> list:
    """중복 없이 머지. command 경로로 중복 판별."""
    result = list(existing)
    for new_entry in new_entries:
        new_cmds = {
            h["command"]
            for h in new_entry.get("hooks", [])
            if "command" in h
        }
        # 동일 command가 이미 있으면 스킵
        already_exists = any(
            new_cmds & {
                h["command"]
                for h in existing_entry.get("hooks", [])
                if "command" in h
            }
            for existing_entry in result
        )
        if not already_exists:
            result.append(new_entry)
    return result

for event, entries in new_hooks.items():
    existing_hooks[event] = merge_hook_list(
        existing_hooks.get(event, []), entries, "command"
    )

settings["hooks"] = existing_hooks

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"  settings.json 업데이트 완료")
PYEOF

  success "settings.json hooks 등록 완료"
}

# ── Verify ────────────────────────────────────────────────────────────────────
run_tests() {
  info "동작 확인 테스트 실행 중..."
  echo ""

  SESSION="test_install_$$"

  # 1) buffer 테스트
  echo '{"session_id":"'"$SESSION"'","tool_name":"Edit","tool_input":{"file_path":"/tmp/test.py","old_string":"a","new_string":"a\nb"}}' \
    | python3 "$HOOKS_DIR/slack_buffer.py"

  echo '{"session_id":"'"$SESSION"'","tool_name":"Bash","tool_input":{"command":"make test"}}' \
    | python3 "$HOOKS_DIR/slack_buffer.py"

  # 2) stop 테스트 (Slack 발송)
  echo "  → Stop hook 테스트 (Slack 발송)..."
  echo '{"session_id":"'"$SESSION"'","stop_hook_active":true,"cwd":"/tmp","transcript_path":""}' \
    | python3 "$HOOKS_DIR/slack_stop.py" && success "Stop hook 전송 성공"

  # 3) notify 테스트
  echo "  → Notification hook 테스트..."
  echo '{"session_id":"'"$SESSION"'","message":"파일을 덮어쓸까요?","cwd":"/tmp","transcript_path":""}' \
    | python3 "$HOOKS_DIR/slack_notify.py" && success "Notification hook 전송 성공"

  echo ""
  success "모든 테스트 통과 — Slack 채널을 확인하세요!"
}

# ── Summary ───────────────────────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${GREEN}${BOLD}  설치 완료!${RESET}"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
  echo "  설치된 파일:"
  echo "    $HOOKS_DIR/slack_buffer.py   (PostToolUse)"
  echo "    $HOOKS_DIR/slack_stop.py     (Stop)"
  echo "    $HOOKS_DIR/slack_notify.py   (Notification)"
  echo "    $HOOKS_DIR/slack_config.json (설정)"
  echo ""
  echo "  동작 방식:"
  echo "    파일 편집/명령 실행 → buffer 누적 → Stop 시 Slack 요약"
  echo "    확인 요청/입력 대기 → Slack 즉시 알림"
  echo ""
  echo "  설정 변경: $HOOKS_DIR/slack_config.json"
  echo "  제거:      bash uninstall.sh"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  check_prerequisites
  install_hooks
  collect_config
  patch_settings
  run_tests
  print_summary
}

main "$@"
