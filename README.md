# Website Monitor 🔍

공지사항 페이지를 주기적으로 크롤링해 Slack으로 새 글을 알리는 경량 모니터링 도구입니다.

Selenium(옵션) + Requests로 페이지를 가져오고, 제목/URL 정규화와 중복 제거 로직으로 중복 알림을 최소화합니다.
실행은 manage.sh(데몬 모드) + 선택적 cron을 사용합니다.

## 주요 기능

-	정적/동적 페이지 크롤링 (requests + BeautifulSoup, Selenium)
-	webdriver-manager 기반 ChromeDriver 자동 설치
-	제목+링크 해시 기반 중복 제거
-	카테고리 그룹핑 + Slack Block Kit 알림
-	상단 고정글(cate00/top-notice) 감지 시 🌟 표시
-	로그 자동 회전 (자정 기준, 7일 보관)
-	지속 실행 모드 / 1회 실행 모드 지원
-	manage.sh로 시작/중지/상태/로그 관리
-	재부팅 후 자동 실행 가능 (cron @reboot)

---

## 설치 & 준비

```bash
git clone https://github.com/hyun-hyang/website-monitor.git
cd website-monitor
python3 -m venv .venv && source .venv/bin/activate    # 선택
pip install -r requirements.txt
cp .env.example .env                                  # 없으면 직접 생성
```

- env 예시:

```env
# (권장) Slack Bot 사용 시 – chat.postMessage/chat.delete 등을 쓰려면 필수
SLACK_BOT_TOKEN=xoxb-...

# Bot이 메시지 보낼 채널 ID (예: C0123456789)
SLACK_CHANNEL_ID=C...

# (옵션) Webhook으로도 보낼 수 있는 폴백 경로
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# (옵션) HTTP 요청/셀레니움 User-Agent 오버라이드
USER_AGENT=Mozilla/5.0 ...
```
Tip: Webhook 대신 Bot 토큰을 쓰면, 잘못 보낸 메시지도 chat.delete로 삭제할 수 있습니다.

---
## 실행 방법

### 1) 데몬 모드 (추천)
```bash
./manage.sh start     # 백그라운드 실행
./manage.sh status    # 상태 확인
./manage.sh logs      # 실시간 로그 보기 (daemon.log tail)
./manage.sh stop      # 중지
./manage.sh restart   # 재시작
```
- 중복 실행 방지: run/instance.lock 파일락 사용
- 로그:
  - logs/daemon.log : 데몬 표준출력
	- logs/app.log : 애플리케이션 로그 (자정 기준 로그 로테이션, 7일 보관)
	-	logs/chromedriver.log : ChromeDriver 로그

### 2) 1회 실행

```bash
python3 website_monitor.py once
```
---

## 부팅 시 자동 시작 + 헬스체크 (선택)

crontab -e 에 아래 추가:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

@reboot  cd /home/<user>/website-monitor && ./manage.sh start >> logs/cron.log 2>&1
*/5 * * * * cd /home/<user>/website-monitor && ./manage.sh status >/dev/null 2>&1 || ( ./manage.sh start >> logs/cron.log 2>&1 )
```

- 재부팅 시 자동 시작.
- 매 5분마다 status 확인 후 꺼져 있으면 자동 재기동.

---

## Chrome / ChromeDriver

Selenium 사용 시 Chrome 필요.
webdriver-manager가 자동으로 맞는 버전의 ChromeDriver를 내려받습니다.

### Debian/Ubuntu 설치 예시

```bash
# Chrome 설치
wget -qO- https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | \
  sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# 기타 의존 패키지
sudo apt-get install -y fonts-noto-cjk libnss3 libxss1 libasound2 unzip xdg-utils
```

---

## 설정 파일

-	config.json – 사이트별 설정

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
      "enabled": true,
      "max_items": 20
    }
  ],
  "check_interval": 300,
  "slack_show_date": true,
  "slack_show_views": true,
  "user_agent": "Mozilla/5.0 ..."
}
```
- .env – 민감 값 관리 (config.json보다 우선 적용)

- previous_data.json – 이미 본 공지 해시 저장 (최대 50개/사이트)

---

## Slack 메시지 삭제 도구

전제: 봇이 chat:write, chat:delete 권한 보유 + 채널 참여 필요.
Webhook으로 보낸 메시지는 삭제 불가.

### 1. **조건 검색 후 삭제**: slack_delete_tool.py


``` bash
# DRY-RUN (날짜 범위)
python3 slack_delete_tool.py --since "2025-08-28 00:00:00" --until "2025-08-28 23:59:59"

# 실제 삭제
python3 slack_delete_tool.py --since "2025-08-28 00:00:00" --until "2025-08-28 23:59:59" --yes

# 텍스트 포함 / 정규식
python3 slack_delete_tool.py --contains "테스트"
python3 slack_delete_tool.py --regex "공지사항"
```

### 2.	**특정 ts 직접 삭제** : slack_delete_ts.py

``` bash
python3 slack_delete_ts.py --ts=1756181407.518089     # DRY-RUN
python3 slack_delete_ts.py --ts=1756181407.518089 --yes
```
Slack의 Webhook으로 보낸 메시지는 삭제할 수 없습니다. 봇으로 보낸 메시지만 삭제 가능해요.

---

## 프로젝트 구조

```
website-monitor/
├─ website_monitor.py       # 메인 실행
├─ manage.sh                # 데몬 관리
├─ watchdog.sh              # (선택) 헬스체크
├─ slack_delete_tool.py     # 조건 검색 삭제
├─ slack_delete_ts.py       # 특정 ts 삭제
├─ config.json              # 사이트 설정
├─ previous_data.json       # 본 글 해시 저장
├─ logs/
│  ├─ app.log               # 애플리케이션 로그
│  └─ chromedriver.log      # ChromeDriver 로그
├─ run/
│  └─ instance.lock         # 중복 실행 방지
└─ .env                     # 환경변수
```
logs/, run/, previous_data.json → .gitignore 권장

---

## 주의사항

- 첫 실행 시 webdriver-manager가 ChromeDriver를 자동 다운로드합니다 (서버에 Chrome 설치 필요).
- Selenium 기반 사이트는 CPU/RAM 사용량이 더 높습니다.
- Slack Webhook URL 및 토큰은 반드시 비공개로 관리하세요.


