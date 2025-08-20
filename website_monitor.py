import requests
from bs4 import BeautifulSoup
import json
import time
import hashlib
import os
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
        soup = BeautifulSoup(html, 'lxml')  # 가능하면 lxml
        notices = []

        try:
            items = soup.select(website_config['selector'])
            for el in items[:10]:
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

                # 날짜/조회수: td 인덱스가 없다면 폴백
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
                    # 흔한 패턴 폴백
                    for sel in ['.views', '.hit', '.count', '[data-views]']:
                        ve = el.select_one(sel)
                        if ve:
                            views = ve.get_text(strip=True) if ve.text else ve.get('data-views', '')
                            break

                if views.startswith("Views"):
                    

                notices.append({
                    'title': title,
                    'link': link,
                    'date': date,
                    'views': views,
                    'hash': hashlib.md5(f"{title}{link}".encode()).hexdigest()
                })
        except Exception as e:
            logger.error(f"HTML 파싱 실패: {e}")

        return notices
    
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
        """슬랙 알림 전송"""
        webhook_url = self.config['slack_webhook_url']
        
        if webhook_url == "YOUR_SLACK_WEBHOOK_URL_HERE":
            logger.warning("슬랙 웹훅 URL이 설정되지 않았습니다.")
            return
        
        try:
            # 슬랙 메시지 구성
            text = f"🔔 *{website_name}*에 새로운 공지사항이 있습니다!"
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📢 {website_name} 새 공지사항"
                    }
                }
            ]
            
            for notice in new_notices[:5]:  # 최대 5개만 표시
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• <{notice['link']}|{notice['title']}>\n   📅 {notice['date']}\t Views: {notice['views']}"
                    }
                })
            
            if len(new_notices) > 5:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"그 외 {len(new_notices) - 5}개의 새 공지사항이 더 있습니다."
                        }
                    ]
                })
            
            payload = {
                "text": text,
                "blocks": blocks
            }
            
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"슬랙 알림 전송 완료: {len(new_notices)}개 공지사항")
            
        except requests.RequestException as e:
            logger.error(f"슬랙 알림 전송 실패: {e}")
    
    def check_website(self, website_config):
        """특정 웹사이트 체크"""
        if not website_config.get('enabled', True):
            return
        
        website_name = website_config['name']
        url = website_config['url']
        
        logger.info(f"{website_name} 체크 중...")
        
        # 웹페이지 내용 가져오기
        html = self.get_page_content(url, website_config)
        if not html:
            return
        
        # 공지사항 파싱
        current_notices = self.parse_notices(html, website_config)
        if not current_notices:
            logger.warning(f"{website_name}: 공지사항을 찾을 수 없습니다.")
            return
        
        # 이전 데이터와 비교
        site_key = hashlib.md5(url.encode()).hexdigest()
        previous_hashes = set(self.previous_data.get(site_key, []))
        current_hashes = {notice['hash'] for notice in current_notices}
        
        # 새로운 공지사항 찾기
        new_hashes = current_hashes - previous_hashes
        new_notices = [notice for notice in current_notices if notice['hash'] in new_hashes]
        
        if new_notices:
            logger.info(f"{website_name}: {len(new_notices)}개의 새 공지사항 발견")
            self.send_slack_notification(website_name, new_notices)
        else:
            logger.info(f"{website_name}: 새 공지사항 없음")
        
        # 현재 데이터 저장 (최대 50개까지만)
        self.previous_data[site_key] = list(current_hashes)[:50]
    
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