# app/scrapers/utils.py
import logging, re, time, json, random
import requests
from typing import Optional
from difflib import SequenceMatcher
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from app.config import config

logger = logging.getLogger(__name__)
ROBOTS_CACHE = {}

HEADERS = {
    "User-Agent": config.USER_AGENT,
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
    
    # Try multiple ScrapingBee configurations
    configs = [
        {
            "render_js": "false",
            "premium_proxy": "true",
            "country_code": "au",
            "wait": "1000",
        },
        {
            "render_js": "true",
            "premium_proxy": "true", 
            "country_code": "au",
            "wait": "3000",
        },
        {
            "render_js": "false",
            "premium_proxy": "false",
            "country_code": "au",
            "wait": "1000",
        }
    ]
    
    for i, config_params in enumerate(configs):
        try:
            logger.info(f"ScrapingBee attempt {i+1}: {url} (render_js={config_params['render_js']})")
            
            params = {
                "api_key": config.SCRAPINGBEE_API_KEY,
                "url": url,
                **config_params
            }
            
            bee = requests.get(
                "https://app.scrapingbee.com/api/v1",
                params=params,
                timeout=max(config.REQUEST_TIMEOUT, 90),
                headers=HEADERS,
            )
            
            if bee.status_code == 200:
                logger.info(f"ScrapingBee success on attempt {i+1}")
                return BeautifulSoup(bee.text, "html.parser")
            
            logger.warning(f"ScrapingBee attempt {i+1} failed {bee.status_code}: {bee.text[:200]}")
            
            # If it's a 503 or 500, try next config
            if bee.status_code in (503, 500) and i < len(configs) - 1:
                time.sleep(2)  # Brief delay before next attempt
                continue
                
        except Exception as e:
            logger.error(f"ScrapingBee attempt {i+1} error {url}: {e}")
            if i < len(configs) - 1:
                time.sleep(2)
                continue
    
    logger.error(f"All ScrapingBee attempts failed for {url}")
    return None

def fetch_url(
    url: str,
    ignore_robots: bool = False,
    max_retries: int = 3,
    render_js: bool | None = None,
) -> BeautifulSoup | None:
    if not ignore_robots and not can_fetch_url(url):
        logger.warning(f"Blocked by robots.txt: {url}")
        return None

    proxies = {}
    if config.HTTP_PROXY:  proxies["http"]  = config.HTTP_PROXY
    if config.HTTPS_PROXY: proxies["https"] = config.HTTPS_PROXY

    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            # Add random delay between requests to avoid rate limits
            if attempt > 1:
                delay = config.CRAWL_DELAY * (2 ** (attempt - 1)) + random.uniform(0.5, 2.0)
                logger.info(f"Retry attempt {attempt}, waiting {delay:.1f}s")
                time.sleep(delay)
            
            resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT, proxies=proxies)
            if resp.status_code == 200:
                time.sleep(config.CRAWL_DELAY + random.uniform(0.1, 0.4))
                return BeautifulSoup(resp.text, "html.parser")

            logger.warning(f"GET {url} -> {resp.status_code}")
            
            # Handle rate limits with exponential backoff
            if resp.status_code in (403, 429, 503):
                if attempt <= max_retries:
                    ra = resp.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        sleep_s = float(ra)
                    else:
                        # Exponential backoff: 3s, 6s, 12s, 24s
                        sleep_s = 3.0 * (2 ** (attempt - 1))
                    
                    logger.warning(f"{resp.status_code} received, sleep {sleep_s}s then retry (attempt {attempt}/{max_retries})")
                    time.sleep(sleep_s)
                    continue
                else:
                    logger.error(f"Max retries exceeded for {url}")
                    break
            
            # For other errors, try ScrapingBee immediately
            bee = _fetch_with_scrapingbee(url, render_js=bool(render_js))
            if bee:
                return bee
            return None
            
        except Exception as e:
            logger.error(f"fetch_url error {url}: {e}")
            if attempt <= max_retries:
                continue
            else:
                # Final attempt with ScrapingBee
                bee = _fetch_with_scrapingbee(url, render_js=bool(render_js))
                return bee
    
    # If all retries failed, try ScrapingBee as last resort
    logger.info(f"All direct attempts failed for {url}, trying ScrapingBee")
    bee = _fetch_with_scrapingbee(url, render_js=bool(render_js))
    return bee

# -------- generic helpers --------

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

# ==== Address & image helpers ============================================

def canonicalize_address(s: str) -> str:
    """Đưa địa chỉ về dạng chuẩn để so khớp: hạ chữ, rút gọn state, bỏ ký tự thừa."""
    s = clean_text(s or "").lower()
    s = re.sub(r"\bqueensland\b", "qld", s)
    s = re.sub(r"\bnew south wales\b", "nsw", s)
    s = re.sub(r"[^a-z0-9/,\s\-]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def address_similarity(a: str | None, b: str | None) -> float:
    a = canonicalize_address(a or "")
    b = canonicalize_address(b or "")
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()

def extract_page_address(soup: BeautifulSoup) -> str | None:
    """Ưu tiên đọc địa chỉ từ JSON-LD, fallback một số selector phổ biến."""
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

def numbers(s: str | None) -> set[str]:
    return set(re.findall(r"\d+", s or ""))

_REJECT_IMG_PATTERNS = [
    r"pixel_", r"/Agencys/", r"contact_", r"domain-insights", r"/akam/", r"\.svg$", r"/icons?/",
]

def filter_photo_urls(urls: list[str]) -> list[str]:
    out = []
    for u in urls or []:
        if any(re.search(p, u) for p in _REJECT_IMG_PATTERNS):
            continue
        out.append(u)
    # dedupe, giữ thứ tự
    return list(dict.fromkeys(out))
def to_int_opt(x) -> Optional[int]:
    if x is None: return None
    if isinstance(x, (int, float)): return int(x)
    s = clean_text(str(x))
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else None

def extract_images_generic(soup: BeautifulSoup) -> list[str]:
    urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if src and src.startswith("http"):
            urls.append(src)
    return filter_photo_urls(list(dict.fromkeys(urls)))[:40]  # limit an toàn

def first_href(soup: BeautifulSoup, css: str) -> str | None:
    a = soup.select_one(css)
    if a:
        href = a.get("href")
        return href if href and href.startswith("http") else None
    return None