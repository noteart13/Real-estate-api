# app/main.py
import logging, re, asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, Body
from app.schemas import SearchResponse, SearchRequest, Property
from app.scrapers.domain import scrape_domain
from app.scrapers.realestate import scrape_realestate
from app.scrapers.search import find_domain_detail, find_rea_detail, looks_like_detail_url
from app.embeddings.clip_embedder import load_model, get_embedding
from app.cache import get_from_cache, set_to_cache
from app.config import config
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
app = FastAPI(title="Realestate-CLIP API")

@app.on_event("startup")
async def startup_event():
    load_model()

_MAX_IMAGES_DEFAULT = 12

def _to_int(x) -> Optional[int]:
    if x is None: return None
    if isinstance(x, (int, float)): return int(x)
    s = str(x)
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else None

def _normalize_payload(p: Dict[str, Any]) -> Dict[str, Any]:
    """Map dict từ scraper về schema Property (đúng field & kiểu)."""
    src = p.get("source") or ""
    source = "domain" if "domain" in src else ("realestate" if "realestate" in src else src)
    return {
        "source": source,
        "url": p.get("url"),
        "address": p.get("address"),
        "price": p.get("price"),
        "bedrooms": _to_int(p.get("bedrooms")),
        "bathrooms": _to_int(p.get("bathrooms")),
        "parking": _to_int(p.get("parking") or p.get("car_spaces")),
        "property_type": p.get("property_type"),
        "description": p.get("description"),
        "features": p.get("features") or [],
        "image_urls": p.get("image_urls") or [],
        "floorplan_url": p.get("floorplan_url") or p.get("floorplan"),
        "agent_name": p.get("agent_name"),
        "agent_phone": p.get("agent_phone"),
        "inspection_times": p.get("inspection_times") or [],
        "image_embeddings": p.get("image_embeddings") or [],
    }

async def _embed_images(urls: List[str], max_images: int) -> List[List[float]]:
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, get_embedding, u) for u in urls[:max_images]]
    embs = await asyncio.gather(*tasks)
    return [e for e in embs if e]

async def _scrape_one(url: str, source: str, include_embeddings: bool, max_images: int) -> Dict[str, Any] | None:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, scrape_domain if source=="domain" else scrape_realestate, url)
    if not data:
        return None
    if include_embeddings:
        data["image_embeddings"] = await _embed_images(data.get("image_urls", []), max_images)
    return _normalize_payload(data)

async def _discover_and_scrape(address_or_url: str, include_embeddings: bool, max_images: int) -> List[Dict[str, Any]]:
    # URL chi tiết -> dùng ngay
    if looks_like_detail_url(address_or_url):
        src = "domain" if "domain.com.au" in address_or_url else "realestate"
        one = await _scrape_one(address_or_url, src, include_embeddings, max_images)
        return [one] if one else []

    # Địa chỉ -> tìm detail URL cho 2 site
    dom_url, rea_url = await asyncio.gather(
        asyncio.get_running_loop().run_in_executor(None, find_domain_detail, address_or_url),
        asyncio.get_running_loop().run_in_executor(None, find_rea_detail, address_or_url),
    )
    tasks = []
    if dom_url: tasks.append(_scrape_one(dom_url, "domain", include_embeddings, max_images))
    if rea_url: tasks.append(_scrape_one(rea_url, "realestate", include_embeddings, max_images))
    if not tasks:
        return []
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]

@app.post("/search", response_model=SearchResponse)
async def search_property(
    address: Optional[str] = Query(None, description="Full address or direct listing URL (query)"),
    body: Optional[SearchRequest] = Body(None, description="You can also send JSON body")
):
    # Hợp nhất nguồn input
    if body and body.address:
        addr = body.address.strip()
        include_embeddings = body.include_embeddings
        max_images = body.max_images or _MAX_IMAGES_DEFAULT
    elif address:
        addr = address.strip()
        include_embeddings = True
        max_images = _MAX_IMAGES_DEFAULT
    else:
        raise HTTPException(status_code=400, detail="Address is required")

    # Cache theo địa chỉ (có thể mở rộng key theo include_embeddings/max_images nếu cần)
    cached = get_from_cache(addr)
    if cached is not None and include_embeddings:   # chỉ trả cache khi có embed sẵn
        return {"properties": [Property(**_normalize_payload(p)) for p in cached]}

    try:
        props = await _discover_and_scrape(addr, include_embeddings, max_images)
        if props and include_embeddings:
            set_to_cache(addr, props)
        return {"properties": [Property(**p) for p in props]}
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        return {"properties": []}

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Realestate-CLIP API. Use /docs, /healthz, /debug/config, POST /search"
    }

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/debug/config")
def debug_config():
    from app.config import config as cfg
    return {
        "redis": {"host": cfg.REDIS_HOST, "port": cfg.REDIS_PORT, "db": cfg.REDIS_DB},
        "clip": {"model": cfg.CLIP_MODEL, "device": cfg.CLIP_DEVICE},
        "http": {"timeout": cfg.REQUEST_TIMEOUT, "ua": cfg.USER_AGENT[:60]},
    }
