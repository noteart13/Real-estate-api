# app/scrapers/utils.py
import logging, re, time, json
import requests
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from app.config import config

logger = logging.getLogger(__name__)
ROBOTS_CACHE = {}

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _robots_for(base_url: str) -> RobotFileParser:
    if base_url in ROBOTS_CACHE:
        return ROBOTS_CACHE[base_url]
    rp = RobotFileParser()
    rp.set_url(f"{base_url}/robots.txt")
    try:
        rp.read()
    except Exception as e:
        logger.warning(f"robots.txt load failed for {base_url}: {e}")
    ROBOTS_CACHE[base_url] = rp
    return rp

def can_fetch_url(url: str) -> bool:
    if not config.RESPECT_ROBOTS_TXT:
        return True
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_for(base)
    try:
        return rp.can_fetch(config.USER_AGENT, url)
    except Exception:
        return True

def fetch_url(url: str) -> BeautifulSoup | None:
    if not can_fetch_url(url):
        logger.warning(f"Blocked by robots.txt: {url}")
        return None

    proxies = {}
    if config.HTTP_PROXY:  proxies["http"]  = config.HTTP_PROXY
    if config.HTTPS_PROXY: proxies["https"] = config.HTTPS_PROXY

    try:
        resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT, proxies=proxies)
        if resp.status_code != 200:
            logger.warning(f"GET {url} -> {resp.status_code}")
            # Fallback ScrapingBee nếu có
            if config.SCRAPINGBEE_API_KEY:
                bee = requests.get(
                    "https://app.scrapingbee.com/api/v1",
                    params={"api_key": config.SCRAPINGBEE_API_KEY, "url": url, "render_js": "false"},
                    timeout=config.REQUEST_TIMEOUT,
                )
                if bee.status_code == 200:
                    return BeautifulSoup(bee.text, "html.parser")
                logger.error(f"ScrapingBee failed {bee.status_code}: {bee.text[:200]}")
            return None

        time.sleep(config.CRAWL_DELAY)  # lịch sự với host
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.error(f"fetch_url error {url}: {e}")
        return None

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def clean_price(price_text: str) -> str:
    if not price_text:
        return "Contact agent"
    t = price_text.strip().lower()
    special = ["contact", "price", "offers", "auction", "expression", "guide", "negotiation", "eoi"]
    if any(s in t for s in special):
        return "Contact agent"
    m = re.search(r'[\$\u20AC\u00A3\uFFE5]?\s*([\d,.]+)', t)
    if m:
        amt = m.group(1).replace(",", "")
        try:
            return f"${int(float(amt)):,}"
        except Exception:
            pass
    m = re.search(r'(\d+(?:\.\d+)?)\s*m\b', t)
    if m:
        return f"${float(m.group(1))*1_000_000:,.0f}"
    m = re.search(r'(\d+(?:\.\d+)?)\s*k\b', t)
    if m:
        return f"${float(m.group(1))*1_000:,.0f}"
    return "Contact agent"

def jsonld_blocks(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", {"type": re.compile("ld\\+json", re.I)}):
        try:
            txt = tag.string or tag.text or ""
            data = json.loads(txt)
            if isinstance(data, dict):
                blocks.append(data)
            elif isinstance(data, list):
                blocks.extend([d for d in data if isinstance(d, dict)])
        except Exception:
            continue
    return blocks

def extract_number(text: str) -> str:
    if not text: return "N/A"
    m = re.search(r"\d+", text)
    return m.group(0) if m else "N/A"
