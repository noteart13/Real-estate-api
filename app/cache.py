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
    """Get data from Redis cache with improved error handling"""
    try:
        raw = redis_client.get(_key(address))
        if not raw:
            return None
        data = zlib.decompress(raw)
        return json.loads(data.decode("utf-8"))
    except redis.RedisError as e:
        logger.warning(f"Redis connection error during cache get: {e}")
        return None
    except (zlib.error, json.JSONDecodeError) as e:
        logger.warning(f"Cache data corruption for key {_key(address)}: {e}")
        # Try to delete corrupted cache entry
        try:
            redis_client.delete(_key(address))
        except Exception:
            pass
        return None
    except Exception as e:
        logger.warning(f"Unexpected cache get error: {e}")
        return None

def set_to_cache(address: str, data, ttl: int | None = None):
    """Set data to Redis cache with improved error handling"""
    try:
        # Validate data before caching
        if not data:
            logger.warning("Attempted to cache empty data")
            return
        
        payload = zlib.compress(json.dumps(data).encode("utf-8"))
        redis_client.setex(_key(address), ttl or config.CACHE_TTL, payload)
        logger.debug(f"Cached data for address: {address[:50]}...")
    except redis.RedisError as e:
        logger.warning(f"Redis connection error during cache set: {e}")
    except (TypeError, ValueError) as e:
        logger.warning(f"Data serialization error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected cache set error: {e}")

def clear_cache(address: str) -> bool:
    """Clear cache entry for specific address"""
    try:
        result = redis_client.delete(_key(address))
        return bool(result)
    except Exception as e:
        logger.warning(f"Cache clear error: {e}")
        return False

def cache_stats() -> dict:
    """Get cache statistics"""
    try:
        info = redis_client.info()
        return {
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }
    except Exception as e:
        logger.warning(f"Cache stats error: {e}")
        return {}
