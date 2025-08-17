
import redis
import json
import hashlib
import logging
from app.config import config  # Thay đổi cách import ở đây
import zlib

logger = logging.getLogger(__name__)
# (tùy chọn) cấu hình logging nếu bạn chưa cấu hình chỗ khác
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
# Sử dụng config object để lấy các giá trị
redis_client = redis.Redis(
    host=config.REDIS_HOST, 
    port=config.REDIS_PORT, 
    db=config.REDIS_DB
)

def get_cache_key(address: str) -> str:
    return f"prop:{hashlib.sha256(address.encode()).hexdigest()}"

def get_from_cache(address: str):
    key = get_cache_key(address)
    cached = redis_client.get(key)
    if cached:
        try:
            # Giải nén dữ liệu
            decompressed = zlib.decompress(cached)
            return json.loads(decompressed)
        except Exception as e:
            logger.error(f"Error decompressing cache: {str(e)}")
            return None
    return None

def set_to_cache(address: str, data, ttl=config.CACHE_TTL):
    key = get_cache_key(address)
    # Nén dữ liệu trước khi lưu
    compressed = zlib.compress(json.dumps(data).encode())
    redis_client.setex(key, ttl, compressed)