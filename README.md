# Website Monitor 🔍

대학교 공지사항 페이지를 주기적으로 크롤링해 **Slack으로 새 글을 실시간 알림**하는 모니터링 도구입니다.

<img src="https://img.shields.io/badge/Python-3.9+-blue" alt="Python"> <img src="https://img.shields.io/badge/Slack-Block%20Kit-4A154B" alt="Slack">

### 핵심 동작

```
공지사항 페이지 크롤링 → 새 글 감지 (해시 비교) → Slack 알림 전송
```

- **정적 페이지**: Requests + BeautifulSoup
- **동적 페이지** (JS 렌더링): Selenium (headless Chrome)
- **알림**: Slack Block Kit 포맷, 카테고리별 그룹핑

---

## 빠른 시작

```bash
git clone https://github.com/hyun-hyang/website-monitor.git
cd website-monitor
pip install -r requirements.txt
```

### 환경변수 설정

`.env` 파일을 생성하고 Slack 인증 정보를 입력합니다.

```env
SLACK_BOT_TOKEN=xoxb-...          # Slack Bot 토큰 (필수)
SLACK_CHANNEL_ID=C0123456789      # 알림 채널 ID (필수)
SLACK_WEBHOOK_URL=https://...     # Webhook 폴백 (선택)
USER_AGENT=Mozilla/5.0 ...       # User-Agent 오버라이드 (선택)
```

> **Tip**: Bot 토큰을 쓰면 잘못 보낸 메시지를 `chat.delete`로 삭제할 수 있습니다.

### 실행

```bash
# 감시 모드 — 크래시 시 자동 재시작, 중복 실행 방지
nohup ./scripts/supervise.sh >> ./logs/supervise.log 2>&1 &

# 1회 실행
python3 src/website_monitor.py once
```

### 워크스페이스 재시작 시 자동 실행

`~/personalize` 스크립트에 등록하면 Coder 워크스페이스 시작 시 자동 실행됩니다.

```bash
#!/bin/bash
setsid bash -c 'cd /home/jylim3060/website-monitor && exec ./scripts/supervise.sh >> ./logs/supervise.log 2>&1' < /dev/null > /dev/null 2>&1 &
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 정적/동적 크롤링 | Requests + BeautifulSoup, Selenium 자동 전환 |
| 중복 제거 | 제목+링크 MD5 해시 비교 (사이트당 최대 200개 추적) |
| Slack 알림 | Block Kit 포맷, 카테고리별 그룹핑 |
| 고정글 감지 | 상단 고정 공지에 🌟 표시 |
| 자동 재시작 | 크래시 시 지수 백오프 (5초 → 최대 5분) 후 재시작 |
| 로그 로테이션 | 자정 기준 회전, 7일 보관 |

---

## 설정

### `config/config.json`

사이트별 크롤링 설정을 정의합니다.

```json
{
  "websites": [
    {
      "name": "일반대학원",
      "url": "https://graduate.korea.ac.kr/community/notice.html",
      "selector": "div.cont",
      "title_selector": "a",
      "link_selector": "a",
      "use_selenium": true,
      "wait_selector": "div.cont",
      "wait_timeout": 10,
      "max_items": 20,
      "enabled": true
    }
  ],
  "check_interval": 300,
  "slack_show_date": true,
  "slack_show_views": true
}
```

| 필드 | 설명 | 기본값 |
|------|------|--------|
| `selector` | 공지 목록 CSS 선택자 | (필수) |
| `title_selector` | 제목 요소 선택자 | (필수) |
| `link_selector` | 링크 요소 선택자 | (필수) |
| `use_selenium` | JS 렌더링 필요 시 `true` | `false` |
| `wait_selector` | Selenium 대기 요소 | - |
| `wait_timeout` | Selenium 대기 시간(초) | `10` |
| `max_items` | 최대 크롤링 항목 수 | `20` |
| `check_interval` | 체크 간격(초) | `300` |

### `data/previous_data.json`

이미 감지한 공지 해시를 저장합니다. 자동 생성되며 직접 수정할 필요 없습니다.

---

## 관리

```bash
# 상태 확인
ps aux | grep supervise

# 로그 보기
tail -f logs/app.log           # 애플리케이션 로그
tail -f logs/supervise.log     # 감시 프로세스 로그

# 중지
kill $(cat run/supervise.pid)

# 자동 시작 제거
rm ~/personalize
```

---

## Slack 메시지 삭제 도구

Bot이 보낸 메시지를 조건별로 삭제할 수 있습니다.
(봇에 `chat:write`, `chat:delete` 권한 필요)

```bash
# 날짜 범위로 삭제 (DRY-RUN → --yes로 실행)
python3 src/slack/delete_tool.py --since "2025-08-28 00:00:00" --until "2025-08-28 23:59:59"
python3 src/slack/delete_tool.py --since "2025-08-28 00:00:00" --until "2025-08-28 23:59:59" --yes

# 텍스트/정규식 필터
python3 src/slack/delete_tool.py --contains "테스트"
python3 src/slack/delete_tool.py --regex "공지사항"

# 특정 메시지 삭제
python3 src/slack/delete_ts.py --ts=1756181407.518089 --yes
```

---

## 프로젝트 구조

```
website-monitor/
├─ src/
│  ├─ website_monitor.py          # 메인 모니터링 엔진
│  └─ slack/
│     ├─ send_manual.py           # 수동 Slack 메시지 전송
│     ├─ delete_tool.py           # 조건별 메시지 삭제
│     └─ delete_ts.py             # 특정 메시지 삭제
├─ scripts/
│  └─ supervise.sh                # 프로세스 감시 + 자동 재시작
├─ config/
│  └─ config.json                 # 사이트별 크롤링 설정
├─ data/
│  └─ previous_data.json          # 감지된 공지 해시 저장
├─ logs/                          # 로그 (자동 생성)
├─ run/                           # PID, 락 파일 (자동 생성)
├─ .env                           # 환경변수 (Slack 토큰 등)
└─ requirements.txt
```

---

## 주의사항

- Selenium 사용 시 서버에 **Google Chrome** 설치 필요. ChromeDriver는 `webdriver-manager`가 자동 설치합니다.
- Selenium 기반 사이트는 CPU/RAM 사용량이 더 높습니다.
- `.env` 파일은 반드시 비공개로 관리하세요.
