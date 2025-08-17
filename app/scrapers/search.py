# app/scrapers/search.py
import logging, re, time
from urllib.parse import quote_plus, urljoin
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException
from bs4 import BeautifulSoup
from .utils import fetch_url

logger = logging.getLogger(__name__)

RE_DOMAIN_DETAIL = re.compile(r"https?://(?:www\.)?domain\.com\.au/[\w\-]+-\d{7,}(?:\?.*)?$", re.I)
RE_REA_DETAIL    = re.compile(r"https?://(?:www\.)?realestate\.com\.au/property-[a-z\-]+-[a-z]{2,3}-\d+(?:\?.*)?$", re.I)

# -------- helpers --------

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
    s = address.strip()
    variants = {s, s.replace("/", " "), re.sub(r"(\d+)/(\d+)", r"\1 \2", s), re.sub(r"\b\d+/\d+\s*", "", s), re.sub(r"\s+\d{4}\b", "", s)}
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
            last_err = e; sleep = backoff ** i
            logger.warning(f"DDG ratelimit, sleep {sleep:.1f}s"); time.sleep(sleep)
        except Exception as e:
            last_err = e; logger.warning(f"DDG error: {e}"); break
    if last_err: logger.warning(f"DDG failed: {last_err}")
    return None

def _bing_first(address: str, pattern: re.Pattern, site_host: str) -> str | None:
    for v in _normalize_address_variants(address):
        q = f'site:{site_host} "{v}"'
        url = f"https://www.bing.com/search?q={quote_plus(q)}&count=10"
        soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
        if not soup: continue
        for css in ["li.b_algo h2 a", "h2 a", "a[href]"]:
            for a in soup.select(css):
                href = a.get("href") or ""
                full = href
                if full and pattern.search(full):
                    logger.info(f"Bing hit for '{v}': {full}")
                    return full.split("?")[0]
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
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup: return None
    base = "https://www.domain.com.au"
    # 1) Anchor
    for a in soup.select("a[href]"):
        full = urljoin(base, a["href"]) if a["href"].startswith("/") else a["href"]
        if RE_DOMAIN_DETAIL.search(full): return full.split("?")[0]
    # 2) Quét toàn HTML
    hit = _find_any_property_url_in_html(str(soup), base, "domain")
    if hit and RE_DOMAIN_DETAIL.search(hit): return hit.split("?")[0]
    return None

def _first_from_rea_search_page(address: str) -> str | None:
    url = _rea_search_url(address)
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=True)
    if not soup: return None
    base = "https://www.realestate.com.au"
    # 1) Anchor
    for a in soup.select("a[href]"):
        full = urljoin(base, a["href"]) if a["href"].startswith("/") else a["href"]
        if RE_REA_DETAIL.search(full) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", full, re.I):
            return full.split("?")[0]
    # 2) Quét toàn HTML
    hit = _find_any_property_url_in_html(str(soup), base, "rea")
    if hit and (RE_REA_DETAIL.search(hit) or re.search(r"/property-[a-z\-]+-[a-z]{2,3}-\d+", hit, re.I)):
        return hit.split("?")[0]
    return None

# -------- public API --------

def find_domain_detail(address: str) -> str | None:
    url = _ddg_first(f'site:domain.com.au "{address}"', RE_DOMAIN_DETAIL) or \
          _bing_first(address, RE_DOMAIN_DETAIL, "domain.com.au") or \
          _first_from_domain_search_page(address)
    return url

def find_rea_detail(address: str) -> str | None:
    url = _ddg_first(f'site:realestate.com.au "{address}"', RE_REA_DETAIL) or \
          _bing_first(address, RE_REA_DETAIL, "realestate.com.au") or \
          _first_from_rea_search_page(address)
    return url

def looks_like_detail_url(s: str) -> bool:
    return bool(RE_DOMAIN_DETAIL.search(s) or RE_REA_DETAIL.search(s))
