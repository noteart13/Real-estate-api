# app/cache.py
import json, hashlib, zlib, logging
import redis
from app.config import config

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
    socket_timeout=5,
    socket_keepalive=True,
)

def _key(address: str) -> str:
    return f"prop:{hashlib.sha256(address.encode('utf-8')).hexdigest()}"

def get_from_cache(address: str):
    try:
        raw = redis_client.get(_key(address))
        if not raw:
            return None
        data = zlib.decompress(raw)
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.warning(f"cache get error: {e}")
        return None

def set_to_cache(address: str, data, ttl: int | None = None):
    try:
        payload = zlib.compress(json.dumps(data).encode("utf-8"))
        redis_client.setex(_key(address), ttl or config.CACHE_TTL, payload)
    except Exception as e:
        logger.warning(f"cache set error: {e}")
