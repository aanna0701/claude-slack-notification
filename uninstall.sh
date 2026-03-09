#!/usr/bin/env bash
# Claude Code Slack Notification — Uninstaller
# Usage: bash uninstall.sh

set -euo pipefail

HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }

echo ""
echo -e "${BOLD}Claude Code Slack 알림 제거${RESET}"
echo ""
warn "다음 파일이 삭제됩니다:"
echo "  $HOOKS_DIR/slack_buffer.py"
echo "  $HOOKS_DIR/slack_stop.py"
echo "  $HOOKS_DIR/slack_notify.py"
echo "  $HOOKS_DIR/slack_config.json"
echo "  settings.json에서 관련 hooks 항목"
echo ""
printf "계속하시겠습니까? [y/N] "; read -r CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  info "취소됨."
  exit 0
fi

# Hook 파일 삭제
for hook in slack_buffer.py slack_stop.py slack_notify.py slack_config.json; do
  if [[ -f "$HOOKS_DIR/$hook" ]]; then
    rm "$HOOKS_DIR/$hook"
    success "삭제됨: $HOOKS_DIR/$hook"
  fi
done

# settings.json에서 slack hook 제거
if [[ -f "$SETTINGS_FILE" ]]; then
  python3 - <<'PYEOF'
import json, os

settings_path = os.path.expanduser("~/.claude/settings.json")
hooks_dir = os.path.expanduser("~/.claude/hooks")

with open(settings_path) as f:
    settings = json.load(f)

hooks = settings.get("hooks", {})

def remove_slack_hooks(entries: list) -> list:
    result = []
    for entry in entries:
        filtered = [
            h for h in entry.get("hooks", [])
            if "slack_" not in h.get("command", "")
        ]
        if filtered:
            result.append({**entry, "hooks": filtered})
    return result

changed = False
for event in list(hooks.keys()):
    cleaned = remove_slack_hooks(hooks[event])
    if cleaned != hooks[event]:
        hooks[event] = cleaned
        changed = True
    if not hooks[event]:
        del hooks[event]
        changed = True

if changed:
    settings["hooks"] = hooks
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  settings.json에서 slack hooks 제거 완료")
else:
    print("  settings.json에 변경 사항 없음")
PYEOF
  success "settings.json 정리 완료"
fi

echo ""
success "제거 완료!"
