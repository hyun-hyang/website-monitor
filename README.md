# Website Monitor 🔍

특정 웹사이트의 공지사항을 주기적으로 체크하고, 새로운 글이 올라오면 **Slack으로 알림**을 보내주는 파이썬 기반 모니터링 도구입니다.

## 주요 기능
- `requests` + `BeautifulSoup` / `Selenium`을 이용한 동적·정적 페이지 크롤링 지원
- `webdriver-manager`를 통한 자동 ChromeDriver 설치
- 게시글 해시 기반 중복 제거 (제목+링크)
- 카테고리별 그룹핑 및 Slack Block Kit 알림
- 상단 고정글(`cate00` / `top-notice`) 감지 → 🌟 이모지 표시
- 로그 파일 자동 회전 (하루 단위, 7일 보관)
- **지속 실행 모드**와 **1회 실행 모드** 지원
- `manage.sh` 스크립트로 시작/중지/상태/로그 관리
- 재부팅 시 자동 실행 설정 가능 (`cron @reboot`)

---

## 설치 방법

### 1. 프로젝트 클론 및 의존성 설치
```bash
git clone https://github.com/yourname/website-monitor.git
cd website-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 설정 파일 수정

config.json을 열어 Slack Webhook과 모니터링할 사이트 정보를 채워주세요.

예시:
```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/XXXXX/XXXXX/XXXXX",
  "websites": [
    {
      "name": "고려대 일반대학원",
      "url": "https://graduate.korea.ac.kr/community/notice.html",
      "selector": "div.board_inner > div > div",
      "title_selector": "p.tit > a",
      "link_selector": "p.tit > a",
      "category_selector": "span.cate",
      "use_selenium": true,
      "wait_selector": "div.board_inner",
      "wait_timeout": 10,
      "enabled": true,
      "max_items": 20
    }
  ],
  "check_interval": 300,
  "driver_recycle_every": 200,
  "user_agent": "Mozilla/5.0 ..."
}
```

---

## 실행 방법

### 1. 지속 실행 (실시간 모니터링)

``` bash
./manage.sh start      # 백그라운드 실행
./manage.sh status     # 상태 확인
./manage.sh tail       # 실시간 로그 보기
./manage.sh stop       # 중지
./manage.sh restart    # 재시작
```

### 2. 1회 실행 (테스트용)

``` bash
python3 website_monitor.py once
```

---

## 로그 관리

- 모든 로그는 logs/app.log에 저장되며, 매일 자정 기준으로 자동 회전됩니다.
- 최근 7일치 로그가 보관됩니다.
- 데몬 실행 시 표준 출력은 logs/daemon.log에 저장됩니다.

---

## 부팅 시 자동 실행

크론에 @reboot 등록:

``` bash
crontab -e
```

``` cron
@reboot cd /home/jylim3060/website-monitor && ./manage.sh start
```

---

## 프로젝트 구조

```
website-monitor/
 ├─ website_monitor.py     # 메인 모니터링 로직
 ├─ manage.sh              # 실행/중지/상태 관리 스크립트
 ├─ config.json            # 모니터링 설정
 ├─ previous_data.json     # 상태 저장 (본 글 해시값)
 ├─ requirements.txt       # 파이썬 의존성
 ├─ logs/                  # 로그 파일 저장 위치
 └─ run/                   # 실행 중 상태(PID 등)
```

---

## 주의사항

- 첫 실행 시 webdriver-manager가 크롬 드라이버를 자동 다운로드합니다. (서버에 크롬/크로미움이 설치되어 있어야 함)
- 동적 페이지 모니터링은 CPU·메모리 리소스를 조금 더 사용합니다.
- Slack Webhook URL은 비공개로 관리하세요.


