#!/usr/bin/env python3
"""공통 유틸리티 — slack_stop.py, slack_notify.py에서 공유."""

import json
import os
import platform
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


def detect_agent() -> tuple[str, str]:
    """실행 중인 AI 에이전트 감지. (name, emoji) 반환."""
    env = os.environ

    # 환경변수 기반 감지
    if any(k.startswith("CURSOR_") for k in env):
        return "Cursor", "🎯"
    if any(k.startswith("CLAUDE_") for k in env):
        return "Claude Code", "🤖"

    # 부모 프로세스 이름 기반 감지 (최대 5단계 순회)
    try:
        pid = os.getpid()
        for _ in range(5):
            result = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "ppid=,comm="],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            parts = result.split(None, 1)
            if len(parts) < 2:
                break
            ppid_str, cmd = parts
            cmd = cmd.lower()
            if "claude" in cmd:
                return "Claude Code", "🤖"
            if "cursor" in cmd:
                return "Cursor", "🎯"
            pid = int(ppid_str)
            if pid <= 1:
                break
    except Exception:
        pass

    return "Unknown Agent", "🤖"


def get_server_info() -> dict:
    def run(*args, **kw) -> str:
        try:
            return subprocess.check_output(
                *args, text=True, stderr=subprocess.DEVNULL, **kw
            ).strip()
        except Exception:
            return ""

    system = platform.system()  # 'Darwin' | 'Linux' | 'Windows'
    hostname = run(["hostname"])
    arch = platform.machine() or run(["uname", "-m"])

    if system == "Darwin":
        ver = platform.mac_ver()[0]
        os_name = f"macOS {ver}" if ver else "macOS"
        os_emoji = "🍎"
        ip = (
            run(["ipconfig", "getifaddr", "en0"])
            or run(["ipconfig", "getifaddr", "en1"])
        )
        model_name = run(
            "system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Name/{print $2; exit}'",
            shell=True,
        )
        device = "Laptop" if "MacBook" in model_name else "Desktop"

    elif system == "Linux":
        os_name = run(
            "[ -f /etc/os-release ] && grep -m1 PRETTY_NAME /etc/os-release | cut -d'\"' -f2 || echo 'Linux'",
            shell=True,
        )
        os_emoji = "🐧"
        ip = run("hostname -I 2>/dev/null | awk '{print $1}'", shell=True)
        try:
            chassis = int(run(["cat", "/sys/class/dmi/id/chassis_type"]))
            device = "Laptop" if chassis in (9, 10) else "Rack" if chassis == 17 else "Desktop"
        except Exception:
            device = "Server"

    else:  # Windows
        os_name = f"Windows {platform.version()}"
        os_emoji = "🪟"
        ip = run("ipconfig | findstr /i 'IPv4' | head -1 | awk '{print $NF}'", shell=True)
        device = "Desktop"

    agent_name, agent_emoji = detect_agent()

    return {
        "hostname": hostname or "unknown",
        "ip": ip or "?.?.?.?",
        "os_name": os_name or "Unknown OS",
        "arch": arch or "unknown",
        "device": device,
        "os_emoji": os_emoji,
        "agent_name": agent_name,
        "agent_emoji": agent_emoji,
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
