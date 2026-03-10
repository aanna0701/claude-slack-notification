#!/usr/bin/env python3
"""PostToolUse hook — 파일 편집/명령 실행을 session buffer에 기록한다."""

import sys
import json
import os

_READ_ONLY_PREFIXES = (
    "cat ", "ls ", "head ", "tail ", "grep ", "find ", "echo ", "which ",
    "type ", "python3 -c", "node -e", "git log", "git status", "git diff",
    "git show", "curl ", "wget ", "man ", "pwd", "env", "printenv", "wc ",
    "less ", "more ", "diff ", "file ", "stat ", "du ", "df ", "ps ",
    "top ", "htop ", "lsof ", "netstat ", "ifconfig ", "ip ", "ping ",
)

NOTIFY_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash"}


def is_read_only_bash(cmd: str) -> bool:
    cmd = cmd.strip()
    for prefix in _READ_ONLY_PREFIXES:
        if cmd.startswith(prefix):
            return True
    return False


def summarize_tool(tool_name: str, tool_input: dict) -> dict | None:
    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        lines = len(content.splitlines())
        return {
            "type": "write",
            "path": path,
            "lines": lines,
            "label": f"`{os.path.basename(path)}` 신규 생성",
        }

    if tool_name in ("Edit", "NotebookEdit"):
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        delta = len(new.splitlines()) - len(old.splitlines())
        sign = "+" if delta >= 0 else ""
        return {
            "type": "edit",
            "path": path,
            "delta": delta,
            "label": f"`{os.path.basename(path)}` 수정 ({sign}{delta}줄)",
        }

    if tool_name == "Bash":
        cmd = tool_input.get("command", "").strip()
        if is_read_only_bash(cmd):
            return None
        short_cmd = cmd.splitlines()[0][:80]
        return {"type": "bash", "cmd": cmd, "label": f"`{short_cmd}`"}

    return None


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    data = json.loads(raw)
    tool_name = data.get("tool_name", "")
    if tool_name not in NOTIFY_TOOLS:
        return

    entry = summarize_tool(tool_name, data.get("tool_input", {}))
    if entry is None:
        return

    session_id = data.get("session_id", "unknown")
    buf_path = f"/tmp/claude_notify_{session_id}.jsonl"

    # 새 작업 시작 시 완료 마커 제거 — 이후 Notification 다시 활성화
    done_path = f"/tmp/claude_done_{session_id}"
    if os.path.exists(done_path):
        try:
            os.unlink(done_path)
        except Exception:
            pass

    with open(buf_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
