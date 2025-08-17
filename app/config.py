import os
import torch
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB   = int(os.getenv("REDIS_DB", 0))
    CACHE_TTL  = int(os.getenv("CACHE_TTL", 172800))  # 48h

    # HTTP / scraping
    USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; PropertyScraper/1.0)")
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))
    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 3))
    RESPECT_ROBOTS_TXT = bool(int(os.getenv("RESPECT_ROBOTS_TXT", "1")))
    CRAWL_DELAY = int(os.getenv("CRAWL_DELAY", 5))
    HTTP_PROXY  = os.getenv("HTTP_PROXY") or None
    HTTPS_PROXY = os.getenv("HTTPS_PROXY") or None
    NO_PROXY    = os.getenv("NO_PROXY", "localhost,127.0.0.1")

    # External scraping service (optional)
    SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY") or None

    # CLIP
    CLIP_MODEL  = os.getenv("CLIP_MODEL", "ViT-B/32")
    CLIP_DEVICE = os.getenv("CLIP_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")

    # GCP (cho Docker tag / k8s)
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "realestate-clip-api")
    GCP_REGION = os.getenv("GCP_REGION", "australia-southeast1")
    GCP_ARTIFACT_REGISTRY = os.getenv("GCP_ARTIFACT_REGISTRY", "property-repo")

    # Misc
    DEBUG = bool(int(os.getenv("DEBUG", "0")))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

config = Config()
