# Claude Code Slack 알림

Claude Code가 파일 편집, 명령 실행, 사용자 확인 요청 시 Slack 채널에 자동 알림을 보냅니다.
Rules 파일 없이 **Hooks만으로** 동작합니다.

## 동작 방식

| 이벤트 | Hook | 발송 방식 |
|--------|------|-----------|
| 파일 편집 / 명령 실행 | PostToolUse → `slack_buffer.py` | buffer 누적 후 Stop에서 1회 요약 |
| 확인 요청 / 입력 대기 | Notification → `slack_notify.py` | 즉시 발송 |
| 응답 완료 | Stop → `slack_stop.py` | buffer 요약 발송 후 삭제 |

응답 1회당 Stop 알림 1개 + 확인 요청 시 Notification 알림 추가.
Claude가 읽기만 한 응답(cat, ls, grep 등)은 알림 없음.

## 빠른 시작

### 1) Slack 앱 생성 (최초 1회)

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch**
2. **OAuth & Permissions → Bot Token Scopes** 추가:
   - `chat:write` — 메시지 전송
   - `channels:read` — 채널 조회
   - `channels:join` — 채널 참여
3. **Install to Workspace** → **Bot User OAuth Token** (`xoxb-...`) 복사
4. 알림 받을 채널에 봇 초대: `/invite @앱이름`
5. 채널 ID 확인: Slack 웹에서 채널 열기 → URL 마지막 부분 (`C0XXXXXX` 형태)

### 2) 설치

```bash
git clone https://github.com/your-username/claude-slack-notification
cd claude-slack-notification
bash install.sh
```

설치 중 Bot Token과 채널 ID를 입력하면 끝입니다.

### 3) 제거

```bash
bash uninstall.sh
```

## 파일 구조

```
~/.claude/hooks/
├── slack_config.json   # 토큰 & 채널 ID (install.sh가 생성)
├── slack_buffer.py     # PostToolUse: 액션을 session buffer에 기록
├── slack_stop.py       # Stop: buffer 읽어서 Slack 요약 발송
└── slack_notify.py     # Notification: 확인 요청 시 즉시 발송
```

## 알림 예시

**작업 완료 알림 (Stop)**
```
🔷 파이썬 스크립트에 에러 처리 추가해줘…
🖥️  macbook-pro (192.168.1.10)
🍎  macOS  •  arm64  •  Laptop
📁  /Users/username/my-project
─────────────────────────────────
💬 요약
  에러 처리 로직을 추가했습니다. try-except 블록으로 예외를 처리합니다.
📋 작업 내용
  • ✏️  `main.py` 수정 (+15줄)
  • ⚙️  `pytest tests/`
✅  완료 (14:32:10)
```

**확인 요청 알림 (Notification)**
```
🔔 확인 필요 — 파이썬 스크립트에 에러 처리 추가해줘…
🖥️  macbook-pro (192.168.1.10)
🍎  macOS  •  arm64  •  Laptop
📁  /Users/username/my-project
─────────────────────────────────
❓  파일을 덮어쓸까요?
⏳  대기 중 (14:31:55)
```

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 알림 안 옴 | 설정 파일 오류 | `~/.claude/hooks/slack_config.json` 확인 |
| `not_in_channel` | 봇이 채널에 없음 | `/invite @봇이름` |
| `invalid_auth` | 토큰 만료 | Slack 앱에서 토큰 재발급 |
| 읽기 명령에도 알림 옴 | Python < 3.10 | `python3 --version` 확인 |
| Hook 실행 안 됨 | settings.json 문법 오류 | `python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))"` |

## 요구사항

- Python 3.10+
- Claude Code CLI
- Slack 워크스페이스 및 봇 토큰
