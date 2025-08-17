# app/scrapers/search.py
import logging, re
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

RE_DOMAIN_DETAIL = re.compile(r"https?://(?:www\.)?domain\.com\.au/[^/\s]+(?:/[^/\s]+)*/\d{7,}(?:\?.*)?$", re.I)
RE_REA_DETAIL    = re.compile(r"https?://(?:www\.)?realestate\.com\.au/(?:property|[^/\s]+)-[a-z\-]+-\d+(?:\?.*)?$", re.I)

def find_domain_detail(address: str) -> str | None:
    q = f'site:domain.com.au "{address}"'
    with DDGS() as ddgs:
        for r in ddgs.text(q, max_results=10):
            url = r.get("href") or r.get("url")
            if url and RE_DOMAIN_DETAIL.search(url):
                return url
    return None

def find_rea_detail(address: str) -> str | None:
    q = f'site:realestate.com.au "{address}"'
    with DDGS() as ddgs:
        for r in ddgs.text(q, max_results=10):
            url = r.get("href") or r.get("url")
            if url and RE_REA_DETAIL.search(url):
                return url
    return None

def looks_like_detail_url(s: str) -> bool:
    return bool(RE_DOMAIN_DETAIL.search(s) or RE_REA_DETAIL.search(s))
