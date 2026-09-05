import hashlib
import logging
import time
from typing import Dict, Any, Union, Optional
from config import settings
from api.models import ExtractedInvoice

logger = logging.getLogger(__name__)

# Try importing redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


class InMemoryDuplicateCache:
    """In-memory cache fallback when Redis is unavailable."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        item = self._cache.get(key)
        if not item:
            return None
        if item["expires_at"] < now:
            del self._cache[key]
            return None
        return item["value"]

    def setex(self, key: str, ttl_seconds: int, value: str):
        expires_at = time.time() + ttl_seconds
        self._cache[key] = {"value": value, "expires_at": expires_at}

    def clear(self):
        self._cache.clear()


_in_memory_cache = InMemoryDuplicateCache()
_redis_client = None


def get_redis_client():
    """Get Redis client instance or return None if unavailable."""
    global _redis_client
    if not REDIS_AVAILABLE:
        return None
    if _redis_client is None:
        try:
            client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            client.ping()
            _redis_client = client
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to in-memory duplicate cache: {e}")
            _redis_client = None
    return _redis_client


def _get_field(data: Union[ExtractedInvoice, Dict[str, Any]], field: str, default: Any = None) -> Any:
    if isinstance(data, ExtractedInvoice):
        return getattr(data, field, default)
    return data.get(field, default)


def generate_fingerprint(invoice: Union[ExtractedInvoice, Dict[str, Any]]) -> str:
    """Generate SHA-256 fingerprint for vendor + invoice number + total amount."""
    vendor_name = str(_get_field(invoice, "vendor_name", "") or "").strip().lower()
    invoice_number = str(_get_field(invoice, "invoice_number", "") or "").strip().upper()
    total_amount = f"{float(_get_field(invoice, 'total_amount', 0.0) or 0.0):.2f}"
    
    raw_key = f"{vendor_name}:{invoice_number}:{total_amount}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def check_duplicate(
    invoice: Union[ExtractedInvoice, Dict[str, Any]],
    record_if_new: bool = True,
    ttl_seconds: int = 90 * 86400,
) -> Dict[str, Any]:
    """
    Check if an invoice with identical vendor, invoice number, and total amount
    has already been processed. Returns a dict with duplicate status and fingerprint.
    """
    fingerprint = generate_fingerprint(invoice)
    cache_key = f"docagent:invoice:{fingerprint}"
    invoice_id = str(_get_field(invoice, "invoice_number", "unknown"))

    r = get_redis_client()

    if r is not None:
        try:
            existing = r.get(cache_key)
            if existing:
                return {
                    "is_duplicate": True,
                    "original_id": existing.decode("utf-8") if isinstance(existing, bytes) else str(existing),
                    "fingerprint": fingerprint,
                    "storage": "redis",
                }
            if record_if_new:
                r.setex(cache_key, ttl_seconds, invoice_id)
            return {
                "is_duplicate": False,
                "fingerprint": fingerprint,
                "storage": "redis",
            }
        except Exception as e:
            logger.warning(f"Redis error during duplicate check, falling back: {e}")

    # In-memory fallback
    existing_mem = _in_memory_cache.get(cache_key)
    if existing_mem:
        return {
            "is_duplicate": True,
            "original_id": existing_mem,
            "fingerprint": fingerprint,
            "storage": "in_memory",
        }

    if record_if_new:
        _in_memory_cache.setex(cache_key, ttl_seconds, invoice_id)

    return {
        "is_duplicate": False,
        "fingerprint": fingerprint,
        "storage": "in_memory",
    }


def register_invoice_fingerprint(
    invoice: Union[ExtractedInvoice, Dict[str, Any]],
    ttl_seconds: int = 90 * 86400,
) -> str:
    """Manually register an invoice fingerprint in cache."""
    fingerprint = generate_fingerprint(invoice)
    cache_key = f"docagent:invoice:{fingerprint}"
    invoice_id = str(_get_field(invoice, "invoice_number", "unknown"))

    r = get_redis_client()
    if r is not None:
        try:
            r.setex(cache_key, ttl_seconds, invoice_id)
            return fingerprint
        except Exception as e:
            logger.warning(f"Redis error during register, falling back: {e}")

    _in_memory_cache.setex(cache_key, ttl_seconds, invoice_id)
    return fingerprint
