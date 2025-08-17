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
        ROBOTS_CACHE[base_url] = rp
        return rp
    except Exception as e:
        logger.warning(f"robots.txt load failed for {base_url}: {e}")
        # IMPORTANT: parse([]) để can_fetch() không default False khi lỗi tải robots
        try:
            rp.parse([])
        except Exception:
            pass
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

def _fetch_with_scrapingbee(url: str, render_js: bool = False) -> BeautifulSoup | None:
    if not config.SCRAPINGBEE_API_KEY:
        logger.warning("SCRAPINGBEE_API_KEY not set -> cannot use ScrapingBee fallback")
        return None
    try:
        logger.info(f"ScrapingBee fallback: {url} (render_js={render_js})")
        bee = requests.get(
            "https://app.scrapingbee.com/api/v1",
            params={
                "api_key": config.SCRAPINGBEE_API_KEY,
                "url": url,
                "render_js": "true" if render_js else "false",
                "wait": "2000",              # đợi 2s cho JS
                "block_resources": "false",  # đừng chặn ảnh/script (an toàn cho search)
            },
            timeout=max(config.REQUEST_TIMEOUT, 90),  # search có thể chậm
            headers=HEADERS,
        )
        if bee.status_code == 200:
            return BeautifulSoup(bee.text, "html.parser")
        logger.error(f"ScrapingBee failed {bee.status_code}: {bee.text[:200]}")
    except Exception as e:
        logger.error(f"ScrapingBee error {url}: {e}")
    return None

def fetch_url(
    url: str,
    ignore_robots: bool = False,
    max_retries: int = 1,
    render_js: bool | None = None,   # <— thêm tham số
) -> BeautifulSoup | None:
    # với trang search, bạn có thể đặt ignore_robots=True từ search.py
    if not ignore_robots and not can_fetch_url(url):
        logger.warning(f"Blocked by robots.txt: {url}")
        return None

    proxies = {}
    if config.HTTP_PROXY:  proxies["http"]  = config.HTTP_PROXY
    if config.HTTPS_PROXY: proxies["https"] = config.HTTPS_PROXY

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT, proxies=proxies)
            if resp.status_code == 200:
                time.sleep(config.CRAWL_DELAY)
                return BeautifulSoup(resp.text, "html.parser")

            logger.warning(f"GET {url} -> {resp.status_code}")
            if resp.status_code == 429 and attempt <= max_retries:
                ra = resp.headers.get("Retry-After")
                sleep_s = float(ra) if ra and ra.isdigit() else 3.0
                logger.warning(f"429 received, sleep {sleep_s}s then retry")
                time.sleep(sleep_s)
                continue

            # Fallback Bee (dùng render_js nếu được yêu cầu)
            bee = _fetch_with_scrapingbee(url, render_js=bool(render_js))
            if bee:
                return bee
            return None
        except Exception as e:
            logger.error(f"fetch_url error {url}: {e}")
            bee = _fetch_with_scrapingbee(url, render_js=bool(render_js))
            return bee

# -------- helpers được module khác import --------

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
        try:
            return f"${int(float(m.group(1).replace(',', ''))):,}"
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
    if not text:
        return "N/A"
    m = re.search(r"\d+", text)
    return m.group(0) if m else "N/A"
