# main.py
import logging
import re
import requests
from fastapi import FastAPI, HTTPException
from app.schemas import SearchResponse
from app.scrapers.domain import scrape_domain
from app.scrapers.realestate import scrape_realestate
from app.embeddings.clip_embedder import load_model, get_embedding
from app.cache import get_from_cache, set_to_cache
from urllib.parse import quote
import asyncio
app = FastAPI()
logger = logging.getLogger(__name__)
# Load CLIP model on startup
@app.on_event("startup")
async def startup_event():
    load_model()



def generate_search_urls(address: str) -> dict:
    # Chuẩn hóa địa chỉ - chỉ giữ chữ cái, số và khoảng trắng
    cleaned_address = re.sub(r'[^\w\s]', '', address).strip()
    
    # Tạo slug an toàn cho URL
    slug = re.sub(r'\s+', '-', cleaned_address).lower()
    
    return {
        "domain": f"https://www.domain.com.au/sale/{slug}-qld-4067/",
        "realestate": f"https://www.realestate.com.au/buy/in-{slug},+qld+4067"
    }
async def scrape_properties(address: str) -> list:
    urls = generate_search_urls(address)
    # We'll scrape both sites concurrently
    loop = asyncio.get_running_loop()
    domain_data = await loop.run_in_executor(None, scrape_domain, urls['domain'])
    realestate_data = await loop.run_in_executor(None, scrape_realestate, urls['realestate'])
    
    results = []
    if domain_data:
        results.append(domain_data)
    if realestate_data:
        results.append(realestate_data)
    
    # Generate embeddings for images
    for prop in results:
        embeddings = []
        for img_url in prop['image_urls']:
            embedding = await loop.run_in_executor(None, get_embedding, img_url)
            if embedding:
                embeddings.append(embedding)
        prop['image_embeddings'] = embeddings
    
    return results
@app.post("/search", response_model=SearchResponse)
async def search_property(address: str):
    if not address:
        raise HTTPException(status_code=400, detail="Address is required")
    
    # Check cache
    cached = get_from_cache(address)
    if cached is not None:
        return {"properties": cached}
    
    try:
        # Scrape data - khởi tạo biến properties ở đây
        properties = await scrape_properties(address)
        
        # Cache the result
        if properties:  # Chỉ lưu cache nếu có dữ liệu
            set_to_cache(address, properties)
        
        return {"properties": properties}
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return {"properties": []}  # Trả về danh sách rỗng khi có lỗi