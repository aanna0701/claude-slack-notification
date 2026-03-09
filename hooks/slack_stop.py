#!/usr/bin/env python3
"""Stop hook — session buffer를 읽어 Slack에 1회 요약 발송 후 buffer 삭제."""

import sys
import json
import os
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

_CONFIG_PATH = os.path.expanduser("~/.claude/hooks/slack_config.json")


def load_config() -> tuple[str, str]:
    """(bot_token, channel_id) 반환. 실패 시 빈 문자열."""
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get("bot_token", ""), cfg.get("channel_id", "")
    except Exception:
        return "", ""


def get_server_info() -> dict:
    def run(*args, **kw) -> str:
        try:
            return subprocess.check_output(
                *args, text=True, stderr=subprocess.DEVNULL, **kw
            ).strip()
        except Exception:
            return ""

    hostname = run(["hostname"])
    ip = run("hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo ''", shell=True)
    os_name = run(
        "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2 || sw_vers -productName 2>/dev/null || echo 'Unknown OS'",
        shell=True,
    )
    arch = run(["uname", "-m"])

    try:
        chassis = int(run(["cat", "/sys/class/dmi/id/chassis_type"]))
        device = "Laptop" if chassis in (9, 10) else "Rack" if chassis == 17 else "Desktop"
    except Exception:
        # macOS: check if it's a MacBook
        model = run("sysctl -n hw.model 2>/dev/null || echo ''", shell=True)
        if "MacBook" in model:
            device = "Laptop"
        elif "Mac" in model:
            device = "Desktop"
        else:
            device = "Server"

    os_lower = os_name.lower()
    if "mac" in os_lower or "darwin" in os_lower:
        os_emoji = "🍎"
    elif "windows" in os_lower:
        os_emoji = "🪟"
    else:
        os_emoji = "🐧"

    return {
        "hostname": hostname or "unknown",
        "ip": ip or "?.?.?.?",
        "os_name": os_name or "Unknown OS",
        "arch": arch or "unknown",
        "device": device,
        "os_emoji": os_emoji,
    }


def parse_transcript(transcript_path: str) -> tuple[str, str]:
    """(first_user_text, last_assistant_text) 반환."""
    first_user = ""
    last_assistant = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str):
                    text = content.strip()
                elif isinstance(content, list):
                    text = " ".join(
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ).strip()
                else:
                    text = ""
                if not text:
                    continue
                if role == "user" and not first_user:
                    first_user = text
                elif role == "assistant":
                    last_assistant = text
    except Exception:
        pass
    return first_user, last_assistant


def send_slack(bot_token: str, channel_id: str, text: str) -> None:
    payload = json.dumps(
        {"channel": channel_id, "text": text}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {bot_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                print(f"[slack_stop] Slack error: {result.get('error')}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"[slack_stop] Network error: {e}", file=sys.stderr)


def format_message(
    actions: list[dict],
    info: dict,
    cwd: str = "",
    first_user: str = "",
    last_assistant: str = "",
) -> str:
    # 작업명: 첫 번째 user 메시지 요약 (없으면 디렉토리명)
    if first_user:
        task_name = first_user[:60] + ("…" if len(first_user) > 60 else "")
    else:
        task_name = os.path.basename(cwd) if cwd else "unknown"

    header = (
        f"*🔷 {task_name}*\n"
        f"🖥️  {info['hostname']} ({info['ip']})\n"
        f"{info['os_emoji']}  {info['os_name']}  •  {info['arch']}  •  {info['device']}\n"
        f"📁  {cwd}\n"
        f"─────────────────────────────────"
    )

    # 같은 파일의 편집 작업은 합산
    file_ops: dict[str, dict] = {}
    bash_cmds: list[str] = []

    for a in actions:
        t = a["type"]
        if t in ("write", "edit"):
            rel = os.path.basename(a.get("path", "unknown"))
            if rel not in file_ops:
                file_ops[rel] = {"type": t, "delta": 0, "lines": 0, "count": 0}
            op = file_ops[rel]
            op["count"] += 1
            op["delta"] += a.get("delta", 0)
            if t == "write":
                op["type"] = "write"
                op["lines"] = a.get("lines", 0)
        elif t == "bash":
            cmd = a.get("cmd", "").strip()
            if cmd and cmd not in bash_cmds:
                bash_cmds.append(cmd)

    bullets: list[str] = []

    for rel, op in file_ops.items():
        count_str = f" ×{op['count']}" if op["count"] > 1 else ""
        if op["type"] == "write":
            bullets.append(f"  • 📝 `{rel}` 신규 생성{count_str} ({op['lines']}줄)")
        else:
            sign = "+" if op["delta"] >= 0 else ""
            bullets.append(f"  • ✏️  `{rel}` 수정{count_str} ({sign}{op['delta']}줄)")

    for cmd in bash_cmds:
        lines = cmd.splitlines()
        if len(lines) > 1:
            display = lines[0] + f"  … (+{len(lines) - 1}줄)"
        else:
            display = cmd
        bullets.append(f"  • ⚙️  `{display}`")

    bullet_str = "\n".join(bullets) if bullets else "  • (작업 내용 없음)"

    # 완료 요약: 마지막 assistant 메시지 첫 단락
    summary_str = ""
    if last_assistant:
        first_para = last_assistant.split("\n\n")[0].replace("\n", " ").strip()
        summary = first_para[:300] + ("…" if len(first_para) > 300 else "")
        summary_str = f"💬 요약\n  {summary}\n"

    now = datetime.now().strftime("%H:%M:%S")
    return (
        f"{header}\n"
        f"{summary_str}"
        f"📋 작업 내용\n"
        f"{bullet_str}\n"
        f"✅  완료 ({now})\n"
        f"\n　"
    )


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    data = json.loads(raw)
    session_id = data.get("session_id", "unknown")
    cwd = data.get("cwd", "")
    transcript_path = data.get("transcript_path", "")

    first_user, last_assistant = (
        parse_transcript(transcript_path) if transcript_path else ("", "")
    )

    buf_path = f"/tmp/claude_notify_{session_id}.jsonl"

    if not os.path.exists(buf_path):
        return

    actions: list[dict] = []
    try:
        with open(buf_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    actions.append(json.loads(line))
    except Exception:
        return
    finally:
        try:
            os.unlink(buf_path)
        except Exception:
            pass

    if not actions:
        return

    bot_token, channel_id = load_config()
    if not bot_token or not channel_id:
        print("[slack_stop] Config missing. Check ~/.claude/hooks/slack_config.json", file=sys.stderr)
        return

    info = get_server_info()
    msg = format_message(actions, info, cwd, first_user, last_assistant)
    send_slack(bot_token, channel_id, msg)


if __name__ == "__main__":
    main()
