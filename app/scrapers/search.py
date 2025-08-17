# app/scrapers/search.py
import logging, re, time
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from .utils import fetch_url
from .utils import fetch_url
import itertools

logger = logging.getLogger(__name__)

RE_DOMAIN_DETAIL = re.compile(r"https?://(?:www\.)?domain\.com\.au/[^/\s]+(?:/[^/\s]+)*/\d{7,}(?:\?.*)?$", re.I)
RE_REA_DETAIL    = re.compile(r"https?://(?:www\.)?realestate\.com\.au/property-[a-z\-]+-\d+(?:\?.*)?$", re.I)
def _extract_href_from_scripts(soup: BeautifulSoup, base: str, site: str) -> str | None:
    """Tìm URL chi tiết trong các <script> JSON (Next.js/Apollo state...)."""
    patterns = []
    if site == "rea":
        # ví dụ: "/property-house-act-o%27malley-147564924"
        patterns = [
            re.compile(r'"(\/property-[a-z\-]+-[a-z]{2,3}-\d+)"', re.I),
            re.compile(r'https?:\/\/www\.realestate\.com\.au\/property-[^"\\]+', re.I),
        ]
    else:  # domain
        # ví dụ: "/3-1-hermitage-drive-airlie-beach-qld-4802-2019960075"
        patterns = [
            re.compile(r'"(\/[a-z0-9\-]+-\d{7,})"', re.I),
            re.compile(r'https?:\/\/www\.domain\.com\.au\/[a-z0-9\-]+-\d{7,}', re.I),
        ]

    for tag in soup.find_all("script"):
        txt = (tag.string or tag.text or "").strip()
        if not txt:
            continue
        for pat in patterns:
            m = pat.search(txt)
            if m:
                href = m.group(1) if m.groups() else m.group(0)
                return urljoin(base, href)
    return None
def _parse_loc(address: str):
    m = re.search(r"([A-Za-z][A-Za-z\s\-\']+),\s*([A-Za-z]{2,3})\s+(\d{4})", address.strip())
    if not m:
        suburb = re.sub(r"\s+", "-", address.strip()).lower()
        return suburb, "", "", address.strip()
    suburb = re.sub(r"\s+", "-", m.group(1).strip()).lower()
    state  = m.group(2).strip().lower()
    pc     = m.group(3).strip()
    return suburb, state, pc, m.group(1).strip()

def _domain_search_url(address: str) -> str:
    suburb, state, pc, _ = _parse_loc(address)
    if state and pc:
        return f"https://www.domain.com.au/sale/{suburb}-{state}-{pc}/"
    return f"https://www.domain.com.au/sale/{suburb}/"

def _rea_search_url(address: str) -> str:
    suburb, state, pc, suburb_q = _parse_loc(address)
    q = suburb_q if not (state and pc) else f"{suburb_q}, {state.upper()} {pc}"
    return f"https://www.realestate.com.au/buy/in-{quote_plus(q)}/list-1"

def _first_from_domain_search_page(address: str) -> str | None:
    url = _domain_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup:
        return None
    base = "https://www.domain.com.au"

    # Tầng 1: quét tất cả anchor
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        full = urljoin(base, href) if href.startswith("/") else href
        if RE_DOMAIN_DETAIL.search(full):
            return full.split("?")[0]

    # Tầng 2: đào trong <script>
    from_scripts = _extract_href_from_scripts(soup, base, "domain")
    if from_scripts and RE_DOMAIN_DETAIL.search(from_scripts):
        return from_scripts.split("?")[0]
    return None

# --- thay thế toàn bộ _first_from_rea_search_page bằng ---
def _first_from_rea_search_page(address: str) -> str | None:
    url = _rea_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup:
        return None
    base = "https://www.realestate.com.au"

    # Tầng 1: anchor
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        full = urljoin(base, href) if href.startswith("/") else href
        if RE_REA_DETAIL.search(full) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", full, re.I):
            return full.split("?")[0]

    # Tầng 2: script
    from_scripts = _extract_href_from_scripts(soup, base, "rea")
    if from_scripts and (RE_REA_DETAIL.search(from_scripts) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", from_scripts, re.I)):
        return from_scripts.split("?")[0]
    return None

def _normalize_address_variants(address: str) -> list[str]:
    s = address.strip()
    variants = {s}
    # bỏ dấu "/": "107/131" -> "107 131", và bỏ luôn "107/"
    variants.add(re.sub(r"(\d+)/(\d+)", r"\1 \2", s))
    variants.add(re.sub(r"\b\d+/\d+\s*", "", s))
    variants.add(s.replace("/", " "))
    # bớt ràng buộc: bỏ postcode
    variants.add(re.sub(r"\s+\d{4}\b", "", s))
    # bớt ràng buộc: chỉ street + suburb
    m = re.search(r"([A-Za-z][A-Za-z\s']+Drive|Street|Road|Ave(?:nue)?)", s, re.I)
    if m:
        street = m.group(0)
        subm = re.search(r",\s*([A-Za-z][A-Za-z\s']+),", s)
        suburb = subm.group(1) if subm else ""
        loose = f"{street} {suburb}".strip()
        if loose:
            variants.add(loose)
    return [v for v in variants if v]

def _ddg_first(query: str, pattern: re.Pattern, max_results: int = 6, retries: int = 1, backoff: float = 1.8) -> str | None:
    last_err = None
    for i in range(retries + 1):
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    url = (r.get("href") or r.get("url") or "").strip()
                    if url and pattern.search(url):
                        return url.split("?")[0]
            return None
        except RatelimitException as e:
            last_err = e
            sleep = backoff ** i
            logger.warning(f"DDG ratelimit, sleep {sleep:.1f}s")
            time.sleep(sleep)
        except Exception as e:
            last_err = e
            logger.warning(f"DDG error: {e}")
            break
    if last_err:
        logger.warning(f"DDG failed: {last_err}")
    return None

def _bing_first(address: str, pattern: re.Pattern, site_host: str) -> str | None:
    # thử nhiều biến thể truy vấn để tránh case "107/131"
    for v in _normalize_address_variants(address):
        q = f'site:{site_host} "{v}"'
        url = f"https://www.bing.com/search?q={quote_plus(q)}&count=10"
        soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)  # <— cho phép render khi cần
        if not soup:
            continue
        for css in ["li.b_algo h2 a", "h2 a", "a[href]"]:
            for a in soup.select(css):
                href = a.get("href", "")
                if href and pattern.search(href):
                    logger.info(f"Bing hit for '{v}': {href}")
                    return href.split("?")[0]
    return None

def find_domain_detail(address: str) -> str | None:
    # 1) DDG
    url = _ddg_first(f'site:domain.com.au "{address}"', RE_DOMAIN_DETAIL)
    if url:
        return url
    # 2) Bing (trước)
    url = _bing_first(address, RE_DOMAIN_DETAIL, "domain.com.au")
    if url:
        return url
    # 3) Trang search Domain (cuối cùng)
    return _first_from_domain_search_page(address)

def find_rea_detail(address: str) -> str | None:
    url = _ddg_first(f'site:realestate.com.au "{address}"', RE_REA_DETAIL)
    if url:
        return url
    # 2) Bing (trước)
    url = _bing_first(address, RE_REA_DETAIL, "realestate.com.au")
    if url:
        return url
    # 3) Trang search REA (cuối cùng, dễ 429 – nên để sau cùng, và sẽ dùng Bee nếu có)
    return _first_from_rea_search_page(address)

def looks_like_detail_url(s: str) -> bool:
    """Kiểm tra chuỗi có phải URL trang chi tiết Domain/Realestate hay không."""
    return bool(RE_DOMAIN_DETAIL.search(s) or RE_REA_DETAIL.search(s))
