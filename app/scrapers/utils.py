# utils.py
import random
import time
import logging
import re
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup   
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests
import re
from app.config import config

logger = logging.getLogger(__name__)


# Bộ nhớ cache cho robots.txt
ROBOTS_CACHE = {}

def can_fetch_url(url: str) -> bool:
    """Kiểm tra xem URL có được phép crawl không dựa trên robots.txt"""
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_url = f"{base_url}/robots.txt"
    
    # Lấy robots.txt nếu chưa có trong cache
    if base_url not in ROBOTS_CACHE:
        try:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            ROBOTS_CACHE[base_url] = rp
            logger.info(f"Loaded robots.txt for {base_url}")
        except Exception as e:
            logger.warning(f"Could not load robots.txt for {base_url}: {e}")
            # Nếu không lấy được robots.txt, mặc định cho phép crawl
            rp = RobotFileParser()
            rp.parse([])
            ROBOTS_CACHE[base_url] = rp
    
    # Kiểm tra quyền truy cập
    rp = ROBOTS_CACHE[base_url]
    can_fetch = rp.can_fetch(config.USER_AGENT, url)
    
    if not can_fetch:
        logger.warning(f"URL blocked by robots.txt: {url}")
    
    return can_fetch

def fetch_url(url: str) -> BeautifulSoup:
    """Lấy nội dung trang web với sự tôn trọng robots.txt"""
    # Kiểm tra robots.txt trước
    if not can_fetch_url(url):
        logger.warning(f"Skipping URL blocked by robots.txt: {url}")
        return None
    
    # Ưu tiên sử dụng ScrapingBee nếu có API key
    if hasattr(config, 'SCRAPINGBEE_API_KEY') and config.SCRAPINGBEE_API_KEY:
        return fetch_with_scrapingbee(url)
    
    # Sử dụng Selenium nếu không có API key
    return fetch_with_selenium(url)

def fetch_with_scrapingbee(url: str) -> BeautifulSoup:
    try:
        # Encode URL đúng cách
        encoded_url = requests.utils.quote(url, safe='')
        api_url = f"https://app.scrapingbee.com/api/v1?api_key={config.SCRAPINGBEE_API_KEY}&url={encoded_url}"
        
        response = requests.get(
            api_url, 
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT}
        )
        
        # Kiểm tra status code
        if response.status_code != 200:
            logger.error(f"ScrapingBee error: {response.status_code} - {response.text}")
            return None
            
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        logger.error(f"Error fetching with ScrapingBee: {str(e)}")
        return None

def fetch_with_selenium(url: str) -> BeautifulSoup:
    """Sử dụng Selenium để lấy dữ liệu"""
    try:
        # Cấu hình Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={config.USER_AGENT}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Cấu hình proxy nếu có
        if hasattr(config, 'PROXY_SERVER') and config.PROXY_SERVER:
            chrome_options.add_argument(f"--proxy-server={config.PROXY_SERVER}")
        
        # Khởi tạo WebDriver
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        logger.info(f"Accessing {url} with Selenium")
        driver.get(url)
        
        # Tôn trọng crawl-delay trong robots.txt
        time.sleep(get_crawl_delay(url))
        
        # Chờ trang tải xong
        WebDriverWait(driver, config.REQUEST_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Cuộn trang để kích hoạt tải nội dung
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Lấy HTML
        html = driver.page_source
        driver.quit()
        
        return BeautifulSoup(html, 'html.parser')
    except Exception as e:
        logger.error(f"Error fetching {url} with Selenium: {str(e)}")
        return None

def get_crawl_delay(url: str) -> int:
    """Lấy giá trị crawl-delay từ robots.txt"""
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    if base_url in ROBOTS_CACHE:
        rp = ROBOTS_CACHE[base_url]
        return rp.crawl_delay(config.USER_AGENT) or 5  # Mặc định 5 giây nếu không có
    
    return 5  # Mặc định 5 giây

def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def clean_price(price_text: str) -> str:
    if not price_text:
        return "Contact agent"
    
    price_text = price_text.strip().lower()
    
    # Kiểm tra các trường hợp đặc biệt
    special_cases = ["contact", "price", "offers", "auction", 
                     "expression", "guide", "by", "negotiation", "eoi"]
    if any(case in price_text for case in special_cases):
        return "Contact agent"
    
    # Xử lý các định dạng giá
    price_match = re.search(r'[\$\u20AC\u00A3\uFFE5]?(\d[\d,\.]+\d)', price_text)
    if price_match:
        amount_str = price_match.group(1).replace(',', '').replace('.', '')
        try:
            amount = int(amount_str)
            return f"${amount:,}"
        except ValueError:
            pass
    
    # Xử lý định dạng triệu/k
    if 'm' in price_text:
        match = re.search(r'(\d+\.?\d*)\s*m', price_text)
        if match:
            return f"${float(match.group(1)) * 1000000:,.0f}"
    
    if 'k' in price_text:
        match = re.search(r'(\d+)\s*k', price_text)
        if match:
            return f"${int(match.group(1)) * 1000:,.0f}"
    
    return "Contact agent"