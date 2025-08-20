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
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from collections import defaultdict

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WebsiteMonitor:
    def __init__(self, config_file='config.json'):
        self.config = self.load_config(config_file)
        self.data_file = 'previous_data.json'
        self.previous_data = self.load_previous_data()
        self.driver = None
        
    def setup_selenium_driver(self):
        """Selenium 드라이버 설정 (자동 설치)"""
        if self.driver:
            return self.driver
            
        options = Options()
        options.add_argument('--headless')  # 브라우저 창 숨김
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'--user-agent={self.config["user_agent"]}')
        
        # SSL 인증서 오류 무시 (일부 사이트에서 필요)
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        
        try:
            # webdriver-manager로 자동 ChromeDriver 설치
            logger.info("ChromeDriver 자동 설치 중...")
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("ChromeDriver 설정 완료!")
            return self.driver
        except Exception as e:
            logger.error(f"Chrome 드라이버 초기화 실패: {e}")
            logger.info("Chrome 브라우저가 설치되어 있는지 확인해주세요.")
            return None
    
    def close_selenium_driver(self):
        """Selenium 드라이버 종료"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        
    def load_config(self, config_file):
        """설정 파일 로드"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # 기본 설정 파일 생성
            default_config = {
                "slack_webhook_url": "YOUR_SLACK_WEBHOOK_URL_HERE",
                "websites": [
                    {
                        "name": "예제 사이트",
                        "url": "https://example.com/notice",
                        "selector": ".notice-list li",  # CSS 선택자
                        "title_selector": "a",  # 제목 선택자
                        "link_selector": "a",   # 링크 선택자
                        "use_selenium": True,   # JavaScript 사이트면 True
                        "wait_selector": ".notice-list",  # 로딩 대기할 요소
                        "wait_timeout": 10,     # 로딩 대기 시간(초)
                        "enabled": True
                    }
                ],
                "check_interval": 300,  # 5분마다 체크
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            
            print(f"설정 파일 '{config_file}'이 생성되었습니다. 설정을 수정해주세요.")
            return default_config
    
    def load_previous_data(self):
        """이전 데이터 로드"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_previous_data(self):
        """현재 데이터 저장"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.previous_data, f, ensure_ascii=False, indent=2)
    
    def get_page_content(self, url, website_config, headers=None):
        """웹페이지 내용 가져오기 (Selenium 또는 requests 사용)"""
        use_selenium = website_config.get('use_selenium', False)
        
        if use_selenium:
            return self.get_page_content_selenium(url, website_config)
        else:
            return self.get_page_content_requests(url, headers)
    
    def get_page_content_requests(self, url, headers=None):
        """Requests로 페이지 내용 가져오기"""
        if not headers:
            headers = {'User-Agent': self.config['user_agent']}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"페이지 요청 실패 {url}: {e}")
            return None
    
    def get_page_content_selenium(self, url, website_config):
        """Selenium으로 페이지 내용 가져오기"""
        driver = self.setup_selenium_driver()
        if not driver:
            return None
        
        try:
            logger.info(f"Selenium으로 페이지 로딩: {url}")
            driver.get(url)
            
            # 특정 요소가 로드될 때까지 대기
            wait_selector = website_config.get('wait_selector')
            wait_timeout = website_config.get('wait_timeout', 10)
            
            if wait_selector:
                try:
                    WebDriverWait(driver, wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                    )
                    logger.info(f"요소 로딩 완료: {wait_selector}")
                except TimeoutException:
                    logger.warning(f"요소 로딩 타임아웃: {wait_selector}")
            else:
                # 기본 대기
                time.sleep(3)
            
            # 추가 스크롤 (무한 스크롤 사이트 대응)
            if website_config.get('scroll_page', False):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            return driver.page_source
            
        except WebDriverException as e:
            logger.error(f"Selenium 페이지 로딩 실패 {url}: {e}")
            return None
    
    def parse_notices(self, html, website_config):
        soup = BeautifulSoup(html, 'lxml')
        notices = []

        try:
            elems = soup.select(website_config['selector'])  # ← items → elems로 이름 변경
            take_n = website_config.get('max_items', 20)
            logger.info(f"[{website_config['name']}] matched={len(elems)} take={take_n} selector='{website_config['selector']}'")

            for el in elems[:website_config.get('max_items', 20)]:
                # 고정글 판정
                pinned_by_td = el.select_one('td.top-notice') is not None
                has_cate00 = any('cate00' in (sp.get('class') or []) for sp in el.select('span.cate'))
                is_pinned = pinned_by_td or has_cate00

                # 카테고리
                cate_sel = website_config.get('category_selector')
                category = ""
                if cate_sel:
                    ce = el.select_one(cate_sel)
                    if ce:
                        category = ce.get_text(strip=True)

                # 제목
                title_elem = el.select_one(website_config.get('title_selector', 'a'))
                title = title_elem.get_text(strip=True) if title_elem else "제목 없음"

                # 링크
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

                # 날짜/조회수
                date = ""
                views = ""
                try:
                    tds = el.select('td')
                    if len(tds) >= 5:
                        date = tds[4].get_text(strip=True)
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

                notices.append({
                    'title': title,
                    'link': link,
                    'date': date,
                    'views': views,
                    'category': category,
                    'hash': hashlib.md5(f"{title}{link}".encode()).hexdigest(),
                    'is_pinned': is_pinned
                })

        except Exception as e:
            logger.error(f"HTML 파싱 실패: {e}")

        return notices
    
    def _group_by_category(self, notices):
        """카테고리 라벨로 그룹핑. 없으면 '기타'."""
        groups = defaultdict(list)
        for n in notices:
            key = (n.get("category") or "").strip()
            if not key:
                key = "기타"   # 카테고리 없으면 기타
            groups[key].append(n)

        # 원하는 순서
        order = ["입학", "장학", "학사", "BK비교과", "기타"]

        # groups에 있는 key들 중 order에 정의된 건 순서대로, 나머지는 마지막에
        ordered_keys = [cat for cat in order if cat in groups] + \
                    [cat for cat in groups if cat not in order]

        return ordered_keys, groups

    def normalize_views(self, s: str) -> str:
        """'Views 3,921', '조회수 3921회' 같은 문자열에서 숫자만 추출."""
        if not s:
            return ""
        s = s.strip()
        # 라벨 제거 (영/한)
        s = re.sub(r'(?i)\b(views?|hits?|조회수|조회)\b[:：]?\s*', '', s)
        # '회' 같은 접미사 제거
        s = re.sub(r'[^\d,\.]', ' ', s)
        # 첫 숫자 토큰만 사용
        m = re.search(r'(\d[\d,\.]*)', s)
        if not m:
            return ""
        num = m.group(1)
        # 천단위/소수점 정리 → 정수 문자열로
        num = num.replace(',', '')
        try:
            num_int = int(float(num))
            return str(num_int)
        except ValueError:
            return num  # 혹시 모를 예외 시 원본 숫자 문자열

    def extract_date(self, element):
        """날짜 추출 (사이트마다 다를 수 있음)"""
        # 일반적인 날짜 패턴 찾기
        date_selectors = ['.date', '.time', '.created', '[data-date]']
        
        for selector in date_selectors:
            date_elem = element.select_one(selector)
            if date_elem:
                return date_elem.get_text(strip=True)
        
        return datetime.now().strftime('%Y-%m-%d')

    def send_slack_notification(self, website_name, new_notices):
        webhook_url = self.config['slack_webhook_url']
        if webhook_url == "YOUR_SLACK_WEBHOOK_URL_HERE":
            logger.warning("슬랙 웹훅 URL이 설정되지 않았습니다.")
            return

        try:
            show_date = bool(self.config.get("slack_show_date", True))
            show_views = bool(self.config.get("slack_show_views", True))

            keys, groups = self._group_by_category(new_notices)

            blocks = [{
                "type": "header",
                "text": {"type": "plain_text", "text": f"📢 {website_name} 새 공지사항"}
            }]

            for cat in keys:
                if cat:  # 빈 카테고리는 소제목 스킵
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{cat}*"}
                    })

                for n in groups[cat]:
                    # 고정글이면 제목 앞에 이모지
                    title_disp = f"🌟 {n['title']}" if n.get('is_pinned') else n['title']

                    date_txt = f"📅 {n['date']}" if (show_date and n.get('date')) else ""
                    views_txt = f"Views {n['views']}" if (show_views and n.get('views')) else ""
                    meta = "   ".join([t for t in [date_txt, views_txt] if t])

                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• <{n['link']}|{title_disp}>" + (f"\n   {meta}" if meta else "")
                        }
                    })

            payload = {"text": f"🔔 *{website_name}*에 새로운 공지사항!", "blocks": blocks}
            resp = requests.post(webhook_url, json=payload)
            resp.raise_for_status()
            logger.info(f"슬랙 알림 전송 완료: {len(new_notices)}개 (카테고리 {len(keys)}개)")
        except requests.RequestException as e:
            logger.error(f"슬랙 알림 전송 실패: {e}")
    
    def check_website(self, website_config):
        if not website_config.get('enabled', True):
            return

        name, url = website_config['name'], website_config['url']
        logger.info(f"{name} 체크 중...")

        html = self.get_page_content(url, website_config)
        if not html:
            return

        all_notices = self.parse_notices(html, website_config)

        # 고정글도 일반글과 합쳐서 동일하게 처리
        all_notices
        if not all_notices:
            logger.warning(f"{name}: 공지사항을 찾을 수 없습니다.")
            return

        site_key = hashlib.md5(url.encode()).hexdigest()
        site_data = self.previous_data.get(site_key, {})
        prev_hashes = set(site_data.get("hashes", []))

        curr_hashes = {n['hash'] for n in all_notices}
        new_hashes = curr_hashes - prev_hashes
        new_notices = [n for n in all_notices if n['hash'] in new_hashes]

        if new_notices:
            logger.info(f"{name}: {len(new_notices)}개의 새 공지사항 발견")
            self.send_slack_notification(name, new_notices)
        else:
            logger.info(f"{name}: 새 공지사항 없음")

        # 고정/일반 구분 없이 본 것들 저장
        site_data["hashes"] = list(curr_hashes)[:50]
        self.previous_data[site_key] = site_data
    
    def run_once(self):
        """한 번 실행"""
        logger.info("웹사이트 모니터링 시작")
        
        for website in self.config['websites']:
            try:
                self.check_website(website)
                time.sleep(2)  # 사이트별 2초 간격
            except Exception as e:
                logger.error(f"웹사이트 체크 오류 {website['name']}: {e}")
        
        self.save_previous_data()
        logger.info("모니터링 완료")
    
    def run_continuous(self):
        """지속적 실행"""
        interval = self.config['check_interval']
        logger.info(f"지속 모니터링 시작 (간격: {interval}초)")
        
        try:
            while True:
                try:
                    self.run_once()
                    logger.info(f"{interval}초 후 다시 체크...")
                    time.sleep(interval)
                except KeyboardInterrupt:
                    logger.info("모니터링 중단됨")
                    break
                except Exception as e:
                    logger.error(f"예상치 못한 오류: {e}")
                    time.sleep(60)  # 오류 시 1분 대기
        finally:
            # Selenium 드라이버 정리
            self.close_selenium_driver()

def main():
    """메인 함수"""
    monitor = WebsiteMonitor()
    
    # 명령행 인수 확인
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'once':
        monitor.run_once()
    else:
        monitor.run_continuous()

if __name__ == "__main__":
    main()