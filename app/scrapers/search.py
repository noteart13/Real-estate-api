# app/scrapers/search.py
import logging, re, time, random
from urllib.parse import quote_plus, urljoin
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from .utils import fetch_url
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

RE_DOMAIN_DETAIL = re.compile(r"https?://(?:www\.)?domain\.com\.au/[\w\-]+-\d{7,}(?:\?.*)?$", re.I)
RE_REA_DETAIL    = re.compile(r"https?://(?:www\.)?realestate\.com\.au/property-[a-z\-]+-[a-z]{2,3}-\d+(?:\?.*)?$", re.I)

# -------- helpers --------

def _parse_loc(address: str):
    """
    Trích suburb/state/pc từ chuỗi địa chỉ. Ví dụ:
    "808/9 South Sea Islander Way, Maroochydore QLD 4558"
      -> suburb="maroochydore", state="qld", pc="4558", suburb_q="Maroochydore"
    """
    m = re.search(r"([A-Za-z][A-Za-z\s\-']+),\s*([A-Za-z]{2,3})\s+(\d{4})", address.strip())
    if not m:
        suburb = re.sub(r"\s+", "-", address.strip()).lower()
        return suburb, "", "", address.strip()
    suburb = re.sub(r"\s+", "-", m.group(1).strip()).lower()
    state  = m.group(2).strip().lower()
    pc     = m.group(3).strip()
    return suburb, state, pc, m.group(1).strip()

def _domain_search_url(address: str) -> str:
    suburb, state, pc, _ = _parse_loc(address)
    return f"https://www.domain.com.au/sale/{suburb}-{state}-{pc}/" if state and pc else f"https://www.domain.com.au/sale/{suburb}/"

def _rea_search_url(address: str) -> str:
    """
    QUAN TRỌNG: chỉ dùng 'suburb, STATE PC' (không dùng cả street).
    """
    suburb, state, pc, suburb_q = _parse_loc(address)
    q = suburb_q if not (state and pc) else f"{suburb_q}, {state.upper()} {pc}"
    return f"https://www.realestate.com.au/buy/in-{quote_plus(q)}/list-1"

def _normalize_address_variants(address: str) -> list[str]:
    s = re.sub(r"\s+", " ", address.strip())
    # Loại 0 thừa trước unit: "0808/9 ..." -> "808/9 ..."
    s = re.sub(r"\b0+(\d+)(?=/)", r"\1", s)

    variants = {s, s.replace("/", " ")}
    # Tạo biến thể unit/number
    m = re.match(r"(\d+)[/\\-](\d+)\s+(.*)", s)
    if m:
        unit, num, rest = m.groups()
        variants.update({
            f"{unit}/{num} {rest}",
            f"Unit {unit} {num} {rest}",
            f"Apartment {unit}, {num} {rest}",
            f"{num} {rest}",  # bỏ unit
        })
    # Bỏ postcode, bỏ state
    variants.add(re.sub(r"\s+\d{4}\b", "", s))
    variants.add(re.sub(r",\s*[A-Za-z]{2,3}\s*\d{4}\b", "", s))
    return [v for v in variants if v]

def _ddg_candidates(query: str, pattern: re.Pattern, max_results: int = 8, retries: int = 3, backoff: float = 2.0) -> list[str]:
    """Trả danh sách URL từ DDG (lọc theo regex), có backoff 'mềm' để tránh 202 Ratelimit."""
    out, last_err = [], None
    for i in range(retries):
        try:
            # Thêm timeout ngắn để tránh treo
            with DDGS(timeout=15) as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    url = (r.get("href") or r.get("url") or "").strip()
                    if url and pattern.search(url):
                        out.append(url.split("?")[0])
            break
        except RatelimitException as e:
            last_err = e
            sleep = (backoff ** i) + random.uniform(0.2, 0.8)
            logger.warning(f"DDG ratelimit, sleep {sleep:.1f}s")
            time.sleep(sleep)
        except Exception as e:
            last_err, _ = e, logger.warning(f"DDG error: {e}")
            break
    if last_err and not out:
        logger.warning(f"DDG candidates failed: {last_err}")
    # dedupe, giữ thứ tự
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

def _bing_first(address: str, pattern: re.Pattern, site_host: str) -> str | None:
    for v in _normalize_address_variants(address):
        q = f'site:{site_host} "{v}"'
        url = f"https://www.bing.com/search?q={quote_plus(q)}&count=10"
        soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
        if not soup: 
            continue
        for css in ["li.b_algo h2 a", "h2 a", "a[href]"]:
            for a in soup.select(css):
                href = a.get("href") or ""
                if href and pattern.search(href):
                    logger.info(f"Bing hit for '{v}': {href}")
                    return href.split("?")[0]
    return None

def _find_any_property_url_in_html(html: str, base: str, site: str) -> str | None:
    """Bắt URL từ toàn bộ HTML (kể cả script)."""
    if site == "rea":
        pats = [
            re.compile(r'https?://www\.realestate\.com\.au/property-[^"\'<\s]+', re.I),
            re.compile(r'"(\/property-[^"\'<\s]+)"', re.I),
        ]
    else:
        pats = [
            re.compile(r'https?://www\.domain\.com\.au/[\w\-]+-\d{7,}', re.I),
            re.compile(r'"(\/[\w\-]+-\d{7,})"', re.I),
        ]
    for pat in pats:
        m = pat.search(html)
        if m:
            href = m.group(1) if m.lastindex else m.group(0)
            return urljoin(base, href)
    return None

def _first_from_domain_search_page(address: str) -> str | None:
    url = _domain_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=False)
    if not soup: 
        return None
    base = "https://www.domain.com.au"
    for a in soup.select("a[href]"):
        h = a.get("href") or ""
        full = urljoin(base, h) if h.startswith("/") else h
        if RE_DOMAIN_DETAIL.search(full):
            return full.split("?")[0]
    hit = _find_any_property_url_in_html(str(soup), base, "domain")
    if hit and RE_DOMAIN_DETAIL.search(hit):
        return hit.split("?")[0]
    return None

def _first_from_rea_search_page(address: str) -> str | None:
    url = _rea_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=False)
    if not soup: 
        return None
    base = "https://www.realestate.com.au"
    for a in soup.select("a[href]"):
        h = a.get("href") or ""
        full = urljoin(base, h) if h.startswith("/") else h
        if RE_REA_DETAIL.search(full) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", full, re.I):
            return full.split("?")[0]
    hit = _find_any_property_url_in_html(str(soup), base, "rea")
    if hit and (RE_REA_DETAIL.search(hit) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", hit, re.I)):
        return hit.split("?")[0]
    return None

# -------- public API --------

def find_domain_detail(address: str) -> str | None:
    # Ưu tiên: trang search Domain -> Bing -> 1 lượt DDG nhẹ
    candidates: list[str] = []
    u = _first_from_domain_search_page(address)
    if u: candidates.append(u)
    u = _bing_first(address, RE_DOMAIN_DETAIL, "domain.com.au")
    if u: candidates.append(u)
    # chỉ hỏi DDG 1-2 biến thể để tránh rate limit
    for v in _normalize_address_variants(address)[:2]:
        candidates += _ddg_candidates(f'site:domain.com.au "{v}"', RE_DOMAIN_DETAIL, max_results=6)

    # Dedupe
    candidates = list(dict.fromkeys(candidates))
    logger.info(f"[candidates/domain] {len(candidates)} -> {candidates[:5]}{'...' if len(candidates)>5 else ''}")
    return candidates[0] if candidates else None

def find_rea_detail(address: str) -> str | None:
    candidates: list[str] = []
    u = _first_from_rea_search_page(address)
    if u: candidates.append(u)
    u = _bing_first(address, RE_REA_DETAIL, "realestate.com.au")
    if u: candidates.append(u)
    for v in _normalize_address_variants(address)[:2]:
        candidates += _ddg_candidates(f'site:realestate.com.au "{v}"', RE_REA_DETAIL, max_results=6)

    candidates = list(dict.fromkeys(candidates))
    logger.info(f"[candidates/rea] {len(candidates)} -> {candidates[:5]}{'...' if len(candidates)>5 else ''}")
    return candidates[0] if candidates else None

def looks_like_detail_url(s: str) -> bool:
    return bool(RE_DOMAIN_DETAIL.search(s) or RE_REA_DETAIL.search(s))
