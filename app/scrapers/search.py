# app/scrapers/search.py
import logging, re, time
from urllib.parse import quote_plus, urljoin
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException

# dùng các helper đã thêm ở utils.py
from .utils import fetch_url, extract_page_address, address_similarity

logger = logging.getLogger(__name__)

RE_DOMAIN_DETAIL = re.compile(r"https?://(?:www\.)?domain\.com\.au/[\w\-]+-\d{7,}(?:\?.*)?$", re.I)
RE_REA_DETAIL    = re.compile(r"https?://(?:www\.)?realestate\.com\.au/property-[a-z\-]+-[a-z]{2,3}-\d+(?:\?.*)?$", re.I)

# ------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------

def _parse_loc(address: str):
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
    suburb, state, pc, suburb_q = _parse_loc(address)
    q = suburb_q if not (state and pc) else f"{suburb_q}, {state.upper()} {pc}"
    return f"https://www.realestate.com.au/buy/in-{quote_plus(q)}/list-1"

def _normalize_address_variants(address: str) -> list[str]:
    s = re.sub(r"\s+", " ", address.strip())
    # Bỏ 0 thừa trong phần unit: "0808/9 ..." -> "808/9 ..."
    s = re.sub(r"\b0+(\d+)(?=/)", r"\1", s)

    variants = {s}

    # Biến thể có/không có unit
    m = re.match(r"(\d+)[/\\-](\d+)\s+(.*)", s)  # unit/number
    if m:
        unit, num, rest = m.groups()
        variants.update({
            f"{unit}/{num} {rest}",
            f"Unit {unit} {num} {rest}",
            f"Apartment {unit}, {num} {rest}",
            f"{num} {rest}",  # bỏ unit
        })

    # Bỏ postcode / state
    variants.add(re.sub(r"\s+\d{4}\b", "", s))
    variants.add(re.sub(r",\s*[A-Za-z]{2,3}\s*\d{4}\b", "", s))

    # Đổi "/" -> " "
    variants.add(s.replace("/", " "))

    return [v for v in variants if v]

# --- DDG: lấy N ứng viên (thay vì 1) -------------------------------------

def _ddg_candidates(query: str, pattern: re.Pattern, max_results: int = 10,
                    retries: int = 1, backoff: float = 1.8) -> list[str]:
    urls, last_err = [], None
    for i in range(retries + 1):
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    url = (r.get("href") or r.get("url") or "").strip()
                    if url and pattern.search(url):
                        u = url.split("?")[0]
                        if u not in urls:
                            urls.append(u)
            return urls
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
    return urls

# --- Bing: lấy 1 ứng viên đầu tiên ---------------------------------------

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
                full = href
                if full and pattern.search(full):
                    logger.info(f"Bing hit for '{v}': {full}")
                    return full.split("?")[0]
    return None

# --- Bắt URL từ toàn HTML (kể cả trong script) ---------------------------

def _find_any_property_url_in_html(html: str, base: str, site: str) -> str | None:
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
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup:
        return None
    base = "https://www.domain.com.au"
    # 1) anchor trực tiếp
    for a in soup.select("a[href]"):
        full = urljoin(base, a["href"]) if a["href"].startswith("/") else a["href"]
        if RE_DOMAIN_DETAIL.search(full):
            return full.split("?")[0]
    # 2) quét toàn HTML
    hit = _find_any_property_url_in_html(str(soup), base, "domain")
    if hit and RE_DOMAIN_DETAIL.search(hit):
        return hit.split("?")[0]
    return None

def _first_from_rea_search_page(address: str) -> str | None:
    url = _rea_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup:
        return None
    base = "https://www.realestate.com.au"
    # 1) anchor trực tiếp
    for a in soup.select("a[href]"):
        full = urljoin(base, a["href"]) if a["href"].startswith("/") else a["href"]
        if RE_REA_DETAIL.search(full) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", full, re.I):
            return full.split("?")[0]
    # 2) quét toàn HTML
    hit = _find_any_property_url_in_html(str(soup), base, "rea")
    if hit and (RE_REA_DETAIL.search(hit) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", hit, re.I)):
        return hit.split("?")[0]
    return None

# ------------------------------------------------------------------------
# chọn ứng viên tốt nhất bằng fuzzy-match địa chỉ
# ------------------------------------------------------------------------

MATCH_THRESHOLD = 0.62  # có thể chỉnh 0.6–0.7

def _pick_best_by_address(candidates: list[str], user_address: str) -> str | None:
    if not candidates:
        return None
    best_url, best_score = None, 0.0
    user_variants = _normalize_address_variants(user_address)

    for url in candidates:
        soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
        page_addr = extract_page_address(soup) if soup else None
        score = max((address_similarity(page_addr, v) for v in user_variants), default=0.0)
        logger.info(f"[match] {url} -> '{page_addr}' score={score:.2f}")
        if score > best_score:
            best_url, best_score = url, score

    if best_url and best_score < MATCH_THRESHOLD:
        logger.warning(f"[match] best candidate below threshold ({best_score:.2f} < {MATCH_THRESHOLD}) -> using fallback")
    return best_url

# ------------------------------------------------------------------------
# public API
# ------------------------------------------------------------------------

def find_domain_detail(address: str) -> str | None:
    candidates: list[str] = []
    # 1) DDG cho nhiều biến thể địa chỉ
    for v in _normalize_address_variants(address):
        candidates += _ddg_candidates(f'site:domain.com.au "{v}"', RE_DOMAIN_DETAIL, max_results=10)
    # 2) Bing
    u = _bing_first(address, RE_DOMAIN_DETAIL, "domain.com.au")
    if u:
        candidates.append(u)
    # 3) Trang search của Domain
    u = _first_from_domain_search_page(address)
    if u:
        candidates.append(u)

    # Dedupe giữ nguyên thứ tự
    candidates = list(dict.fromkeys(candidates))
    logger.info(f"[candidates/domain] {len(candidates)} -> {candidates[:5]}{'...' if len(candidates)>5 else ''}")

    return _pick_best_by_address(candidates, address)

def find_rea_detail(address: str) -> str | None:
    candidates: list[str] = []
    for v in _normalize_address_variants(address):
        candidates += _ddg_candidates(f'site:realestate.com.au "{v}"', RE_REA_DETAIL, max_results=10)
    u = _bing_first(address, RE_REA_DETAIL, "realestate.com.au")
    if u:
        candidates.append(u)
    u = _first_from_rea_search_page(address)
    if u:
        candidates.append(u)

    candidates = list(dict.fromkeys(candidates))
    logger.info(f"[candidates/rea] {len(candidates)} -> {candidates[:5]}{'...' if len(candidates)>5 else ''}")

    return _pick_best_by_address(candidates, address)

def looks_like_detail_url(s: str) -> bool:
    return bool(RE_DOMAIN_DETAIL.search(s) or RE_REA_DETAIL.search(s))
