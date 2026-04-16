#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import json
import time
import hashlib
import os
import re
from datetime import datetime
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from collections import defaultdict
from logging.handlers import TimedRotatingFileHandler
import signal
import sys
import fcntl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from slack_sdk import WebClient
from pathlib import Path

# ---------- 경로/환경: 루트 기준으로 통일 ----------
ROOT_DIR   = Path(__file__).resolve().parents[1]   # <repo>/src → <repo>
SRC_DIR    = ROOT_DIR / "src"
LOG_DIR    = ROOT_DIR / "logs"
RUN_DIR    = ROOT_DIR / "run"
DATA_DIR   = ROOT_DIR / "data"
CONFIG_DIR = ROOT_DIR / "config"

LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

# ---------- 로깅 ----------
logger = logging.getLogger(__name__)

class WebsiteMonitor:
    def __init__(self, config_file='config.json'):
        # config 불러오기 (루트/config)
        self.config = self.load_config(CONFIG_DIR / config_file)

        # env 우선 적용
        wh = os.getenv("SLACK_WEBHOOK_URL")
        if wh:
            self.config["slack_webhook_url"] = wh
        ua = os.getenv("USER_AGENT")
        if ua:
            self.config["user_agent"] = ua

        # 필요시 채널 ID 등을 config로 전달하고 쓸 수 있음
        self.slack_channel_id = os.getenv("SLACK_CHANNEL_ID")

        # 로깅 셋업
        self._setup_logging()

        # 종료 신호 핸들러 (강제 종료 대비)
        signal.signal(signal.SIGTERM, self._graceful_exit)
        signal.signal(signal.SIGINT, self._graceful_exit)

        # 상태/드라이버
        self.data_file = DATA_DIR / 'previous_data.json'
        self.previous_data = self.load_previous_data()
        self.driver = None
        self._cd_log_file = None

        # 단일 인스턴스 락
        self._instance_lock_fp = open(RUN_DIR / "instance.lock", "w")
        try:
            fcntl.lockf(self._instance_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error("이미 실행 중입니다(파일락 획득 실패). 종료합니다.")
            sys.exit(1)

    # ---------- Selenium ----------
    def setup_selenium_driver(self):
        """Selenium 드라이버 설정 (자동 설치)"""
        if self.driver:
            return self.driver

        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'--user-agent={self.config["user_agent"]}')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')

        try:
            logger.info("ChromeDriver 자동 설치 중...")
            cd_log_path = LOG_DIR / "chromedriver.log"
            if self._cd_log_file is None or self._cd_log_file.closed:
                self._cd_log_file = open(cd_log_path, "a", encoding="utf-8")

            # Chromium 감지 시 ChromeType.CHROMIUM 사용
            import shutil
            if shutil.which("chromium") and not shutil.which("google-chrome-stable"):
                options.binary_location = shutil.which("chromium")
                driver_path = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
            else:
                driver_path = ChromeDriverManager().install()
            service = Service(driver_path, log_output=self._cd_log_file)
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("ChromeDriver 설정 완료!")
            return self.driver
        except Exception as e:
            logger.error(f"Chrome 드라이버 초기화 실패: {e}")
            logger.info("Chrome 브라우저가 설치되어 있는지 확인해주세요.")
            return None

    def close_selenium_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
        if getattr(self, "_cd_log_file", None):
            try:
                self._cd_log_file.close()
            except Exception:
                pass
            self._cd_log_file = None

    # ---------- 설정/상태 파일 ----------
    def load_config(self, config_path: Path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            default_config = {
                "slack_webhook_url": "YOUR_SLACK_WEBHOOK_URL_HERE",
                "websites": [
                    {
                        "name": "예제 사이트",
                        "url": "https://example.com/notice",
                        "selector": ".notice-list li",
                        "title_selector": "a",
                        "link_selector": "a",
                        "use_selenium": True,
                        "wait_selector": ".notice-list",
                        "wait_timeout": 10,
                        "enabled": True,
                        "max_items": 20
                    }
                ],
                "check_interval": 300,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            print(f"설정 파일이 생성되었습니다 → {config_path}")
            return default_config

    def load_previous_data(self):
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_previous_data(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.previous_data, f, ensure_ascii=False, indent=2)

    # ---------- 페이지 로딩 ----------
    def get_page_content(self, url, website_config, headers=None):
        if website_config.get('use_selenium', False):
            return self.get_page_content_selenium(url, website_config)
        else:
            return self.get_page_content_requests(url, headers)

    def get_page_content_requests(self, url, headers=None):
        if not headers:
            headers = {'User-Agent': self.config['user_agent']}
        for attempt in (1, 2):
            try:
                r = requests.get(url, headers=headers, timeout=20)
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                logger.warning(f"페이지 요청 실패 {url} (시도 {attempt}): {e}")
                time.sleep(1)
        logger.error(f"페이지 요청 최종 실패: {url}")
        return None

    def get_page_content_selenium(self, url, website_config):
        for attempt in (1, 2):
            driver = self.setup_selenium_driver()
            if not driver:
                return None
            try:
                logger.info(f"Selenium으로 페이지 로딩: {url} (attempt {attempt})")
                driver.get(url)
                wait_selector = website_config.get('wait_selector')
                wait_timeout = website_config.get('wait_timeout', 10)
                if wait_selector:
                    WebDriverWait(driver, wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                    )
                return driver.page_source
            except WebDriverException as e:
                logger.warning(f"Selenium 로딩 실패(시도 {attempt}): {e}")
                self.close_selenium_driver()
                time.sleep(1)
        logger.error("Selenium 재시도 실패")
        return None

    # ---------- 파싱 ----------
    def parse_notices(self, html, website_config):
        soup = BeautifulSoup(html, 'lxml')
        notices = []
        try:
            elems = soup.select(website_config['selector'])
            take_n = website_config.get('max_items', 20)
            logger.info(f"[{website_config['name']}] matched={len(elems)} take={take_n} selector='{website_config['selector']}'")

            for el in elems[:take_n]:
                pinned_by_td = el.select_one('td.top-notice') is not None
                has_cate00  = any('cate00' in (sp.get('class') or []) for sp in el.select('span.cate'))
                is_pinned   = pinned_by_td or has_cate00

                category = ""
                cate_sel = website_config.get('category_selector')
                if cate_sel:
                    ce = el.select_one(cate_sel)
                    if ce:
                        category = ce.get_text(strip=True)

                title_elem = el.select_one(website_config.get('title_selector', 'a'))
                title = title_elem.get_text(strip=True) if title_elem else "제목 없음"

                link = ""
                link_elem = el.select_one(website_config.get('link_selector', 'a'))
                if link_elem and link_elem.has_attr('href'):
                    href = link_elem['href']
                    if href.startswith('/'):
                        from urllib.parse import urljoin, urlparse
                        base = f"{urlparse(website_config['url']).scheme}://{urlparse(website_config['url']).netloc}"
                        link = urljoin(base, href)
                    elif href.startswith('?') or not href.startswith('http'):
                        from urllib.parse import urljoin
                        link = urljoin(website_config['url'], href)
                    else:
                        link = href

                date, views = "", ""
                try:
                    tds = el.select('td')
                    if len(tds) >= 5:
                        date  = tds[4].get_text(strip=True)
                        views = tds[3].get_text(strip=True)
                except Exception:
                    pass

                if not date:
                    date = self.extract_date(el)
                if not views:
                    for sel in ['.views', '.hit', '.count', '[data-views]']:
                        ve = el.select_one(sel)
                        if ve:
                            views = ve.get_text(strip=True) if ve.text else ve.get('data-views', '')
                            break
                views = self.normalize_views(views)

                title_norm = self._normalize_title(title)
                link_norm  = self._normalize_url(link)

                notices.append({
                    'title': title,
                    'link': link,
                    'date': date,
                    'views': views,
                    'category': category,
                    'hash': hashlib.md5(f"{title_norm}{link_norm}".encode()).hexdigest(),
                    'is_pinned': is_pinned
                })
        except Exception as e:
            logger.error(f"HTML 파싱 실패: {e}")

        before = len(notices)
        notices = self._dedupe_notices(notices)
        after = len(notices)
        if after < before:
            logger.info(f"중복 제거: {before} → {after} (−{before - after})")
        return notices

    # ---------- 유틸 ----------
    def _group_by_category(self, notices):
        groups = defaultdict(list)
        for n in notices:
            key = (n.get("category") or "").strip()
            if not key:
                key = ""
            groups[key].append(n)

        order = ["입학", "장학", "학사", "BK비교과", "기타"]
        ordered_keys = [cat for cat in order if cat in groups] + [cat for cat in groups if cat not in order]
        return ordered_keys, groups

    def normalize_views(self, s: str) -> str:
        if not s:
            return ""
        s = s.strip()
        s = re.sub(r'(?i)\b(views?|hits?|조회수|조회)\b[:：]?\s*', '', s)
        s = re.sub(r'[^\d,\.]', ' ', s)
        m = re.search(r'(\d[\d,\.]*)', s)
        if not m:
            return ""
        num = m.group(1).replace(',', '')
        try:
            return str(int(float(num)))
        except ValueError:
            return num

    def extract_date(self, element):
        for selector in ['.date', '.time', '.created', '[data-date]']:
            date_elem = element.select_one(selector)
            if date_elem:
                return date_elem.get_text(strip=True)
        return datetime.now().strftime('%Y-%m-%d')

    def _normalize_title(self, t: str) -> str:
        return re.sub(r'\s+', ' ', (t or '')).strip()

    def _normalize_url(self, u: str) -> str:
        if not u:
            return u
        s = urlsplit(u)
        q = urlencode(sorted(parse_qsl(s.query, keep_blank_values=True)))
        path = re.sub(r'/+$', '', s.path or '')
        return urlunsplit((s.scheme, s.netloc, path, q, ''))

    def _dedupe_notices(self, items):
        by_key, order = {}, []
        for n in items:
            key = (self._normalize_title(n.get('title')), self._normalize_url(n.get('link')))
            if key not in by_key:
                by_key[key] = n
                order.append(key)
            else:
                if n.get('is_pinned'):
                    by_key[key]['is_pinned'] = True
        return [by_key[k] for k in order]
    
    def _escape_mrkdwn_text(self, text: str) -> str:
        """Slack mrkdwn에서 깨질 수 있는 특수문자 이스케이프"""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

    # ---------- Slack ----------
    def send_slack_notification(self, website_name, new_notices):
        bot_token  = os.getenv("SLACK_BOT_TOKEN")
        channel_id = os.getenv("SLACK_CHANNEL_ID")
        webhook_url = self.config.get("slack_webhook_url")

        show_date  = bool(self.config.get("slack_show_date", True))
        show_views = bool(self.config.get("slack_show_views", True))
        keys, groups = self._group_by_category(new_notices)

        blocks = [{
            "type": "header",
            "text": {"type": "plain_text", "text": f"📢 {website_name} 새 공지사항"}
        }]
        for cat in keys:
            if cat:
                blocks.append({"type": "section","text": {"type": "mrkdwn","text": f"*{cat}*"}})
            for n in groups[cat]:
                title_disp = f"🌟 {self._escape_mrkdwn_text(n['title'])}" if n.get('is_pinned') else self._escape_mrkdwn_text(n['title'])
                date_txt  = f"📅 {n['date']}" if (show_date and n.get('date')) else ""
                views_txt = f"Views {n['views']}" if (show_views and n.get('views')) else ""
                meta = "   ".join([t for t in [date_txt, views_txt] if t])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• <{n['link']}|{title_disp}>" + (f"\n   {meta}" if meta else "")
                    }
                })

        if bot_token and channel_id:
            try:
                client = WebClient(token=bot_token)
                resp = client.chat_postMessage(
                    channel=channel_id,
                    text=f"🔔 *{website_name}*에 새로운 공지사항!",
                    blocks=blocks
                )
                self._last_post_ts = resp["ts"]
                logger.info(f"슬랙(봇) 전송 완료: {len(new_notices)}개 (ts={resp['ts']})")
                return
            except Exception as e:
                logger.error(f"슬랙 봇 전송 실패: {e}")

        if webhook_url and webhook_url != "YOUR_SLACK_WEBHOOK_URL_HERE":
            try:
                payload = {"text": f"🔔 *{website_name}*에 새로운 공지사항!", "blocks": blocks}
                r = requests.post(webhook_url, json=payload)
                r.raise_for_status()
                logger.info(f"슬랙(웹훅) 전송 완료: {len(new_notices)}개")
            except requests.RequestException as e:
                logger.error(f"슬랙 웹훅 전송 실패: {e}")
        else:
            logger.warning("슬랙 전송 경로가 없습니다(Bot 토큰/채널 또는 Webhook URL 설정 필요).")

    # ---------- 메인 루프 ----------
    def check_website(self, website_config):
        if not website_config.get('enabled', True):
            return

        name, url = website_config['name'], website_config['url']
        logger.info(f"{name} 체크 중...")

        html = self.get_page_content(url, website_config)
        if not html:
            return

        all_notices = self.parse_notices(html, website_config)
        if not all_notices:
            logger.warning(f"{name}: 공지사항을 찾을 수 없습니다.")
            return

        site_key = hashlib.md5(url.encode()).hexdigest()
        site_data = self.previous_data.get(site_key, {})
        prev_hashes = set(site_data.get("hashes", []))

        curr_hashes = {n['hash'] for n in all_notices}
        new_hashes  = curr_hashes - prev_hashes
        new_notices = [n for n in all_notices if n['hash'] in new_hashes]

        if new_notices:
            logger.info(f"{name}: {len(new_notices)}개의 새 공지사항 발견")
            self.send_slack_notification(name, new_notices)
            try:
                self.save_previous_data()
            except Exception as e:
                logger.warning(f"임시 저장 실패: {e}")
        else:
            logger.info(f"{name}: 새 공지사항 없음")

        site_data["hashes"] = list(curr_hashes)[:200]
        self.previous_data[site_key] = site_data

    def run_once(self):
        logger.info("웹사이트 모니터링 시작")
        for website in self.config['websites']:
            try:
                self.check_website(website)
                time.sleep(2)
            except Exception as e:
                logger.error(f"웹사이트 체크 오류 {website['name']}: {e}")
        self.save_previous_data()
        logger.info("모니터링 완료")

    def run_continuous(self):
        interval = self.config['check_interval']
        logger.info(f"지속 모니터링 시작 (간격: {interval}초)")
        try:
            recycle_every = int(self.config.get("driver_recycle_every", 200))
            loop_count = 0
            while True:
                try:
                    self.run_once()
                    loop_count += 1
                    if recycle_every > 0 and loop_count % recycle_every == 0:
                        logger.info(f"루프 {loop_count}회차 → 드라이버 재생성")
                        self.close_selenium_driver()
                    interval = self.config['check_interval']
                    logger.info(f"{interval}초 후 다시 체크...")
                    time.sleep(interval)
                except KeyboardInterrupt:
                    logger.info("모니터링 중단됨")
                    break
                except Exception as e:
                    logger.error(f"예상치 못한 오류: {e}")
                    time.sleep(60)
                finally:
                    self.close_selenium_driver()   # 강제 정리
        finally:
            self.close_selenium_driver()

    def _setup_logging(self):
        logger.setLevel(logging.INFO)
        for h in list(logger.handlers):
            logger.removeHandler(h)

        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        fh = TimedRotatingFileHandler(
            filename=LOG_DIR / "app.log",
            when="midnight", interval=1, backupCount=7, encoding="utf-8"
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        logger.propagate = False
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("WDM").setLevel(logging.WARNING)

    def _graceful_exit(self, signum, frame):
        logger.info(f"종료 신호 수신({signum}) → 상태 저장 및 자원 정리")
        try:
            self.save_previous_data()
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")
        try:
            self.close_selenium_driver()
        except Exception as e:
            logger.error(f"드라이버 종료 실패: {e}")
        sys.exit(0)

# ---------- entry ----------
def main():
    monitor = WebsiteMonitor()
    if len(sys.argv) > 1 and sys.argv[1] == 'once':
        monitor.run_once()
    else:
        monitor.run_continuous()

if __name__ == "__main__":
    main()