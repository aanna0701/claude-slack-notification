#!/usr/bin/env python3
"""Stop hook — session buffer를 읽어 Slack에 1회 요약 발송 후 buffer 삭제."""

import sys
import json
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack_common import load_config, get_server_info, send_slack


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


def format_message(
    actions: list[dict],
    info: dict,
    cwd: str = "",
    first_user: str = "",
    last_assistant: str = "",
) -> str:
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
    send_slack(bot_token, channel_id, msg, caller="slack_stop")


if __name__ == "__main__":
    main()
