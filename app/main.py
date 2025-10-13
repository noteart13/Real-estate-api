# app/main.py
import logging, re, asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import SearchResponse, SearchRequest, Property
from app.scrapers.domain import scrape_domain
from app.scrapers.realestate import scrape_realestate
from app.scrapers.search import find_domain_detail, find_rea_detail, looks_like_detail_url
from app.embeddings.clip_embedder import load_model, get_embedding
from app.scrapers.utils import address_similarity
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.on_event("startup")
async def startup_event():
    load_model()

_MAX_IMAGES_DEFAULT = 12

# Similarity thresholds
_STRICT_MATCH_THRESHOLD = 0.72  # strong match required to be considered "exact"
_NEAR_MATCH_THRESHOLD = 0.50    # acceptable near match when no strict match exists

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

def _create_mock_property(address: str) -> Dict[str, Any]:
    """Create a mock property for testing when scraping fails"""
    return {
        "source": "mock",
        "url": None,  # no real URL in mock mode to avoid broken links
        "address": address,
        "price": "Contact agent",
        "bedrooms": 3,
        "bathrooms": 2,
        "parking": 1,
        "property_type": "House",
        "description": f"Beautiful property located at {address}. This is a mock listing created for testing purposes when the real estate websites are not accessible.",
        "features": ["Air conditioning", "Built in wardrobes", "Internal Laundry", "Secure Parking"],
        "image_urls": [
            "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800",
            "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=800",
            "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800"
        ],
        "floorplan_url": None,
        "agent_name": "Mock Agent",
        "agent_phone": "+61 400 000 000",
        "inspection_times": ["Saturday 2:00pm - 2:30pm", "Sunday 10:00am - 10:30am"],
        "image_embeddings": [],
    }

async def _discover_and_scrape(address_or_url: str, include_embeddings: bool, max_images: int) -> List[Dict[str, Any]]:
    # Nếu là URL (kể cả project/search page), thử scrape trực tiếp theo host
    if re.match(r"^https?://", address_or_url.strip(), re.I):
        src = "domain" if "domain.com.au" in address_or_url else ("realestate" if "realestate.com.au" in address_or_url else "")
        if src:
            one = await _scrape_one(address_or_url, src, include_embeddings, max_images)
            return [one] if one else []

    # Địa chỉ -> tìm detail URL cho 2 site
    try:
        dom_url, rea_url = await asyncio.gather(
            asyncio.get_running_loop().run_in_executor(None, find_domain_detail, address_or_url),
            asyncio.get_running_loop().run_in_executor(None, find_rea_detail, address_or_url),
        )
        tasks = []
        if dom_url: tasks.append(_scrape_one(dom_url, "domain", include_embeddings, max_images))
        if rea_url: tasks.append(_scrape_one(rea_url, "realestate", include_embeddings, max_images))
        
        if not tasks:
            logger.warning(f"No URLs found for address: {address_or_url}")
            # Return mock data for testing
            mock_prop = _create_mock_property(address_or_url)
            if include_embeddings:
                mock_prop["image_embeddings"] = await _embed_images(mock_prop.get("image_urls", []), max_images)
            return [mock_prop]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Scraping failed for task {i}: {result}")
            elif result:
                valid_results.append(result)
        
        if not valid_results:
            logger.warning(f"All scraping attempts failed for address: {address_or_url}")
            # Return mock data for testing
            mock_prop = _create_mock_property(address_or_url)
            if include_embeddings:
                mock_prop["image_embeddings"] = await _embed_images(mock_prop.get("image_urls", []), max_images)
            return [mock_prop]

        # Filter by address similarity to avoid wrong properties
        try:
            sims = [
                (
                    address_similarity(address_or_url, (r.get("address") or "")),
                    r,
                )
                for r in valid_results
            ]
            sims.sort(key=lambda x: x[0], reverse=True)
            best_sim = sims[0][0] if sims else 0.0

            # Two-tier strategy:
            # 1) If any strict matches exist, return ALL strict matches (both sources if available)
            strict_matches = [r for s, r in sims if s >= _STRICT_MATCH_THRESHOLD]
            if strict_matches:
                return strict_matches

            # 2) Else, return all near matches if present
            near_matches = [r for s, r in sims if s >= _NEAR_MATCH_THRESHOLD]
            if near_matches:
                return near_matches

            logger.warning(
                f"No sufficiently similar address match (best_sim={best_sim:.2f}, "
                f"strict>={_STRICT_MATCH_THRESHOLD}, near>={_NEAR_MATCH_THRESHOLD}) for '{address_or_url}'"
            )
        except Exception:
            pass

        # Fallback to mock when similarity is too low
        mock_prop = _create_mock_property(address_or_url)
        if include_embeddings:
            mock_prop["image_embeddings"] = await _embed_images(mock_prop.get("image_urls", []), max_images)
        return [mock_prop]
    except Exception as e:
        logger.error(f"Error in _discover_and_scrape: {e}")
        # Return mock data for testing
        mock_prop = _create_mock_property(address_or_url)
        if include_embeddings:
            mock_prop["image_embeddings"] = await _embed_images(mock_prop.get("image_urls", []), max_images)
        return [mock_prop]

@app.post("/search", response_model=SearchResponse)
async def search_property(
    address: Optional[str] = Query(None, description="Full address or direct listing URL (query)"),
    body: Optional[SearchRequest] = Body(None, description="You can also send JSON body")
):
    try:
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

        # Validate input
        if not addr or len(addr) < 5:
            raise HTTPException(status_code=400, detail="Address must be at least 5 characters long")
        
        if max_images < 1 or max_images > 50:
            raise HTTPException(status_code=400, detail="max_images must be between 1 and 50")

        # Cache theo địa chỉ (có thể mở rộng key theo include_embeddings/max_images nếu cần)
        cached = get_from_cache(addr)
        if cached is not None and include_embeddings:   # chỉ trả cache khi có embed sẵn
            return {"properties": [Property(**_normalize_payload(p)) for p in cached]}

        props = await _discover_and_scrape(addr, include_embeddings, max_images)
        if props and include_embeddings:
            set_to_cache(addr, props)
        return {"properties": [Property(**p) for p in props]}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Search failed for address '{addr}': {e}", exc_info=True)
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

@app.get("/debug/cache")
def debug_cache():
    """Get cache statistics and health"""
    from app.cache import cache_stats
    stats = cache_stats()
    return {
        "status": "ok" if stats else "error",
        "stats": stats,
        "cache_ttl": config.CACHE_TTL
    }
