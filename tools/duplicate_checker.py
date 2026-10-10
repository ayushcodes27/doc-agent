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
_last_redis_check = 0.0
_REDIS_RETRY_INTERVAL = 30.0  # seconds cooldown before retrying Redis connection


def get_redis_client():
    """Get Redis client instance or return None if unavailable (with retry cooldown)."""
    global _redis_client, _last_redis_check
    if not REDIS_AVAILABLE:
        return None
    if _redis_client is not None:
        return _redis_client
    
    now = time.time()
    if now - _last_redis_check < _REDIS_RETRY_INTERVAL:
        return None
        
    _last_redis_check = now
    try:
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
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
            if record_if_new:
                was_new = r.set(cache_key, invoice_id, nx=True, ex=ttl_seconds)
                if not was_new:
                    existing = r.get(cache_key)
                    return {
                        "is_duplicate": True,
                        "original_id": existing.decode("utf-8") if isinstance(existing, bytes) and existing else str(existing) if existing else "unknown",
                        "fingerprint": fingerprint,
                        "storage": "redis",
                    }
                return {
                    "is_duplicate": False,
                    "fingerprint": fingerprint,
                    "storage": "redis",
                }
            else:
                existing = r.get(cache_key)
                if existing:
                    return {
                        "is_duplicate": True,
                        "original_id": existing.decode("utf-8") if isinstance(existing, bytes) else str(existing),
                        "fingerprint": fingerprint,
                        "storage": "redis",
                    }
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


def check_file_hash_gate(
    file_bytes: bytes,
    db: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Smart Pre-LLM File Hash Gate.
    Computes SHA-256(file_bytes) and checks for prior processing:
      - Active/Approved prior record -> Block duplicate file upload.
      - Previously failed/rejected/appealed -> Allow reprocessing (linked via supersedes_id).
    """
    if not file_bytes:
        return {"is_blocked": False, "file_hash": "", "is_reprocess": False}

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        from db.session import get_db_context
        from db.models import InvoiceRecord
        from sqlalchemy import select, desc

        def _query(session):
            stmt = (
                select(InvoiceRecord)
                .where(InvoiceRecord.file_hash == file_hash)
                .order_by(desc(InvoiceRecord.created_at))
            )
            return session.scalars(stmt).first()

        if db is not None:
            prior = _query(db)
        else:
            with get_db_context() as session:
                prior = _query(session)

        if prior:
            prior_status = (prior.status or "").lower()
            prior_decision = (prior.decision or "").lower()

            # Active / Completed / Approved -> Block duplicate
            is_active_or_approved = (
                prior_status in ["completed", "approved_by_human", "pending_review"]
                or prior_decision in ["auto_approve", "flag_review"]
            ) and prior_status not in ["rejected", "rejected_by_human", "failed_extraction"]

            if is_active_or_approved:
                return {
                    "is_blocked": True,
                    "file_hash": file_hash,
                    "prior_case_id": prior.id,
                    "prior_status": prior.status,
                    "reason": f"Identical file already processed as case #{prior.id} (Status: {prior.status}).",
                }
            else:
                # Prior attempt was rejected, failed extraction, or appealed -> Allow reprocessing!
                return {
                    "is_blocked": False,
                    "file_hash": file_hash,
                    "is_reprocess": True,
                    "supersedes_id": prior.id,
                    "reason": f"Reprocessing previously {prior.status} case #{prior.id}.",
                }

    except Exception as e:
        logger.debug(f"File hash gate database check skipped: {e}")

    return {
        "is_blocked": False,
        "file_hash": file_hash,
        "is_reprocess": False,
    }


def check_near_duplicate(
    invoice: Union[ExtractedInvoice, Dict[str, Any]],
    db: Optional[Any] = None,
    exclude_case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Checks for near-duplicate invoices:
    Same vendor and amount, but invoice number differs slightly (e.g. typos, re-bills).
    Excludes the invoice's own case ID to prevent self-matching.
    """
    vendor_name = str(_get_field(invoice, "vendor_name", "") or "").strip().lower()
    inv_num = str(_get_field(invoice, "invoice_number", "") or "").strip().upper()
    amount = float(_get_field(invoice, "total_amount", 0.0) or 0.0)

    if not vendor_name or amount <= 0:
        return {"is_near_duplicate": False}

    try:
        from db.session import get_db_context
        from db.models import InvoiceRecord
        from sqlalchemy import select, func

        def _search(session):
            stmt = (
                select(InvoiceRecord)
                .where(
                    func.lower(InvoiceRecord.vendor_name) == vendor_name,
                    func.abs(InvoiceRecord.total_amount - amount) <= 0.05,
                    InvoiceRecord.status != "rejected"
                )
            )
            if exclude_case_id:
                stmt = stmt.where(InvoiceRecord.id != exclude_case_id)
            return session.scalars(stmt).all()

        records = _search(db) if db is not None else []
        if db is None:
            with get_db_context() as session:
                records = _search(session)

        for rec in records:
            prior_num = (rec.invoice_number or "").strip().upper()
            if prior_num == inv_num:
                # Exact match
                return {
                    "is_near_duplicate": False,
                    "is_exact_duplicate": True,
                    "original_id": rec.id,
                    "prior_invoice_number": prior_num,
                }
            # Levenshtein distance check on invoice number (differing by 1-2 characters)
            if len(prior_num) >= 3 and len(inv_num) >= 3:
                # Simple distance: count differences
                diff_chars = sum(1 for a, b in zip(prior_num, inv_num) if a != b) + abs(len(prior_num) - len(inv_num))
                if diff_chars <= 2:
                    return {
                        "is_near_duplicate": True,
                        "original_id": rec.id,
                        "prior_invoice_number": prior_num,
                        "reason": f"Near-duplicate detected: same vendor & amount, but invoice number '{inv_num}' closely resembles '{prior_num}' on case #{rec.id} (distance: {diff_chars}).",
                    }
    except Exception as e:
        logger.debug(f"Near-duplicate check skipped: {e}")

    return {"is_near_duplicate": False}


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
