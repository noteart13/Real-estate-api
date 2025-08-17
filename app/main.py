# app/main.py
import logging, re, asyncio
from fastapi import FastAPI, HTTPException, Query
from app.schemas import SearchResponse
from app.scrapers.domain import scrape_domain
from app.scrapers.realestate import scrape_realestate
from app.scrapers.search import find_domain_detail, find_rea_detail, looks_like_detail_url
from app.embeddings.clip_embedder import load_model, get_embedding
from app.cache import get_from_cache, set_to_cache
from app.config import config
import sys, logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Realestate-CLIP API")


@app.get(
    "/debug/config",
    include_in_schema=True,
    tags=["debug"],
    summary="Show loaded config (masked)"
)
def debug_config():
    masked = (config.SCRAPINGBEE_API_KEY[:6] + "***") if config.SCRAPINGBEE_API_KEY else "(none)"
    return {
        "SCRAPINGBEE_API_KEY": masked,
        "RESPECT_ROBOTS_TXT": config.RESPECT_ROBOTS_TXT,
        "CRAWL_DELAY": config.CRAWL_DELAY,
    }
@app.on_event("startup")
async def startup_event():
    load_model()
    masked = f"{config.SCRAPINGBEE_API_KEY[:6]}***" if config.SCRAPINGBEE_API_KEY else "(none)"
    logger.info(f"SCRAPINGBEE_API_KEY: {masked}; RESPECT_ROBOTS_TXT={config.RESPECT_ROBOTS_TXT}; CRAWL_DELAY={config.CRAWL_DELAY}")

    # Liệt kê toàn bộ routes để kiểm chứng
    for r in app.routes:
        methods = getattr(r, "methods", None)
        logger.info(f"Route loaded: {r.path}  methods={methods}")

_MAX_IMAGES = 12  # tránh embed quá nhiều ảnh/lượt

async def _embed_images(urls: list[str]) -> list[list[float]]:
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, get_embedding, u) for u in urls[:_MAX_IMAGES]]
    embs = await asyncio.gather(*tasks)
    return [e for e in embs if e]

async def _scrape_one(url: str, source: str) -> dict | None:
    loop = asyncio.get_running_loop()
    if source == "domain":
        data = await loop.run_in_executor(None, scrape_domain, url)
    else:
        data = await loop.run_in_executor(None, scrape_realestate, url)

    if not data:
        return None
    # embeddings
    data["image_embeddings"] = await _embed_images(data.get("image_urls", []))
    return data

async def _discover_and_scrape(address_or_url: str) -> list[dict]:
    # Nếu người dùng đưa thẳng URL chi tiết → dùng luôn
    if looks_like_detail_url(address_or_url):
        src = "domain" if "domain.com.au" in address_or_url else "realestate"
        one = await _scrape_one(address_or_url, src)
        return [one] if one else []

    # Ngược lại: coi là địa chỉ → tìm URL chi tiết trên 2 site
    dom_url, rea_url = await asyncio.gather(
        asyncio.get_running_loop().run_in_executor(None, find_domain_detail, address_or_url),
        asyncio.get_running_loop().run_in_executor(None, find_rea_detail, address_or_url),
    )

    tasks = []
    if dom_url: tasks.append(_scrape_one(dom_url, "domain"))
    if rea_url: tasks.append(_scrape_one(rea_url, "realestate"))
    # trong _discover_and_scrape sau khi dom_url, rea_url:
    if not dom_url and not rea_url:
        logger.info(f"No detail URL found via search pages for: {address_or_url}")

    if not tasks:
        return []
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]

@app.post("/search", response_model=SearchResponse)
async def search_property(address: str = Query(..., description="Full address or direct listing URL")):
    address = address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address is required")

    cached = get_from_cache(address)
    if cached is not None:
        return {"properties": cached}

    try:
        properties = await _discover_and_scrape(address)
        if properties:
            set_to_cache(address, properties)
        return {"properties": properties}
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        return {"properties": []}
