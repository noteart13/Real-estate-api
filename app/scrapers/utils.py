# app/scrapers/utils.py
import logging, re, time, json, random
import requests
from difflib import SequenceMatcher
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from app.config import config

logger = logging.getLogger(__name__)
ROBOTS_CACHE = {}

HEADERS = {
    "User-Agent": config.USER_AGENT,  # HÃY dùng UA thật (xem gợi ý bên dưới)
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Cache-Control": "no-cache",
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
                "wait": "2000",
                # Kinh nghiệm cho REA/Domain:
                "premium_proxy": "true",      # giảm 429
                "country_code": "au",         # định tuyến tại AU
                "block_resources": "true",    # giảm lỗi/nhẹ trang; đổi "false" nếu thiếu anchors
            },
            timeout=max(config.REQUEST_TIMEOUT, 90),
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
    render_js: bool | None = None,
) -> BeautifulSoup | None:
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
                # thêm jitter nhẹ để né rate-limit theo host
                time.sleep(config.CRAWL_DELAY + random.uniform(0.1, 0.4))
                return BeautifulSoup(resp.text, "html.parser")

            logger.warning(f"GET {url} -> {resp.status_code}")
            if resp.status_code in (403, 429) and attempt <= max_retries:
                ra = resp.headers.get("Retry-After")
                sleep_s = float(ra) if ra and ra.isdigit() else 3.0
                logger.warning(f"{resp.status_code} received, sleep {sleep_s}s then retry")
                time.sleep(sleep_s)
                continue

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
# ==== Address helpers (add) ==============================================


def canonicalize_address(s: str) -> str:
    """Đưa địa chỉ về dạng chuẩn để so khớp: hạ chữ, bỏ ký tự thừa, rút gọn state."""
    s = clean_text(s or "").lower()
    s = re.sub(r"\bqueensland\b", "qld", s)
    s = re.sub(r"\bnew south wales\b", "nsw", s)
    s = re.sub(r"[^a-z0-9/,\s\-]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def address_similarity(a: str | None, b: str | None) -> float:
    """Tính độ giống nhau 0..1 giữa hai địa chỉ (sau khi chuẩn hoá)."""
    a = canonicalize_address(a or "")
    b = canonicalize_address(b or "")
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()

def extract_page_address(soup: BeautifulSoup) -> str | None:
    """Ưu tiên đọc địa chỉ từ JSON-LD, fallback một số selector phổ biến."""
    # 1) JSON-LD
    for blk in jsonld_blocks(soup):
        addr = blk.get("address")
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
            ]
            s = clean_text(" ".join([p for p in parts if p]))
            if s:
                return s
    # 2) Fallback selector
    for sel in [
        'meta[property="og:title"]',
        '[itemprop="streetAddress"]',
        '[data-testid="address"]',
        'h1'
    ]:
        tag = soup.select_one(sel)
        if tag:
            s = tag.get("content") or tag.get_text(" ", strip=True)
            s = clean_text(s)
            if s:
                return s
    return None
# ==== /Address helpers ====================================================
