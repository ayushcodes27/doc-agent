"""
DocAgent Database Package
=========================
Exports engine, sessions, models, and repository operations.
"""

from db.session import (
    Base,
    engine,
    SessionLocal,
    init_db,
    get_db,
    get_db_context,
)
from db.models import (
    InvoiceRecord,
    LineItemRecord,
    ValidationRecord,
    AnomalyRecord,
    AuditTrailRecord,
)
from db.repository import (
    save_processed_invoice,
    get_invoice_by_id,
    get_invoice_by_thread_id,
    list_invoices,
    get_pending_reviews,
    record_human_decision,
    get_vendor_spend_history,
    get_analytics_summary,
)

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "init_db",
    "get_db",
    "get_db_context",
    "InvoiceRecord",
    "LineItemRecord",
    "ValidationRecord",
    "AnomalyRecord",
    "AuditTrailRecord",
    "save_processed_invoice",
    "get_invoice_by_id",
    "get_invoice_by_thread_id",
    "list_invoices",
    "get_pending_reviews",
    "record_human_decision",
    "get_vendor_spend_history",
    "get_analytics_summary",
]
