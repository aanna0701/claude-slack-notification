#!/usr/bin/env python3
"""Notification hook — Claude가 사용자 입력을 기다릴 때 Slack에 즉시 알림."""

import sys
import json
import os
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

_CONFIG_PATH = os.path.expanduser("~/.claude/hooks/slack_config.json")


def load_config() -> tuple[str, str]:
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
                print(f"[slack_notify] Slack error: {result.get('error')}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"[slack_notify] Network error: {e}", file=sys.stderr)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    data = json.loads(raw)
    message = data.get("message", "").strip()
    if not message:
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
        f"🖥️  {info['hostname']} ({info['ip']})\n"
        f"{info['os_emoji']}  {info['os_name']}  •  {info['arch']}  •  {info['device']}\n"
        f"📁  {cwd}\n"
        f"─────────────────────────────────\n"
        f"❓  {message}\n"
        f"⏳  대기 중 ({now})\n"
        f"\n　"
    )
    send_slack(bot_token, channel_id, text)


if __name__ == "__main__":
    main()
