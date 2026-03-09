#!/usr/bin/env python3
"""공통 유틸리티 — slack_stop.py, slack_notify.py에서 공유."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

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
    ip = run(
        "hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo ''",
        shell=True,
    )
    os_name = run(
        "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2"
        " || sw_vers -productName 2>/dev/null || echo 'Unknown OS'",
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


def send_slack(bot_token: str, channel_id: str, text: str, caller: str = "slack") -> None:
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
                print(f"[{caller}] Slack error: {result.get('error')}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"[{caller}] Network error: {e}", file=sys.stderr)
