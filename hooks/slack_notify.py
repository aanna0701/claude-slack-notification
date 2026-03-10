#!/usr/bin/env python3
"""Notification hook — Claude가 사용자 입력을 기다릴 때 Slack에 즉시 알림."""

import sys
import json
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack_common import load_config, get_server_info, send_slack


def get_first_user_message(transcript_path: str) -> str:
    """transcript에서 첫 번째 user 메시지 텍스트 반환."""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("role") != "user":
                    continue
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
                if text:
                    return text
    except Exception:
        pass
    return ""


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    data = json.loads(raw)
    message = data.get("message", "").strip()
    if not message:
        return

    # 이미 완료 알림이 발송된 세션이면 중복 발송 skip
    session_id = data.get("session_id", "unknown")
    done_path = f"/tmp/claude_done_{session_id}"
    if os.path.exists(done_path):
        return

    cwd = data.get("cwd", "")
    transcript_path = data.get("transcript_path", "")
    first_user = get_first_user_message(transcript_path) if transcript_path else ""

    if first_user:
        task = first_user[:50] + ("…" if len(first_user) > 50 else "")
    else:
        task = os.path.basename(cwd) if cwd else "unknown"

    bot_token, channel_id = load_config()
    if not bot_token or not channel_id:
        print("[slack_notify] Config missing. Check ~/.claude/hooks/slack_config.json", file=sys.stderr)
        return

    info = get_server_info()
    now = datetime.now().strftime("%H:%M:%S")

    text = (
        f"*🔔 확인 필요 — {task}*\n"
        f"{info['agent_emoji']}  {info['agent_name']}\n"
        f"🖥️  {info['hostname']} ({info['ip']})\n"
        f"{info['os_emoji']}  {info['os_name']}  •  {info['arch']}  •  {info['device']}\n"
        f"📁  {cwd}\n"
        f"─────────────────────────────────\n"
        f"❓  {message}\n"
        f"⏳  대기 중 ({now})\n"
        f"\n　"
    )
    send_slack(bot_token, channel_id, text, caller="slack_notify")


if __name__ == "__main__":
    main()
