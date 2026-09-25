"""
DocAgent Database ORM Models
============================
SQLAlchemy 2.0 schema for persistent invoice tracking, line items,
compliance validation results, anomaly records, and immutable audit logs.
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional
from sqlalchemy import (
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return str(uuid.uuid4())


class InvoiceRecord(Base):
    """Primary record for processed invoice documents and orchestration state."""
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="unknown.pdf")
    
    # Core Extraction Fields
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    vendor_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    invoice_date: Mapped[Optional[str]] = mapped_column(String(50))
    due_date: Mapped[Optional[str]] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100))
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Visual & Tampering Discrepancy
    visual_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    visual_discrepancy_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    visual_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Deduplication & Risk
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Decision & Routing
    decision: Mapped[str] = mapped_column(String(50), default="pending", index=True)  # auto_approve, flag_review, reject
    approval_level: Mapped[str] = mapped_column(String(50), default="auto")          # auto, manager, director
    decision_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", index=True) # completed, pending_review, approved_by_human, rejected_by_human
    
    # Human Review Overrides
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    line_items: Mapped[List["LineItemRecord"]] = relationship(
        "LineItemRecord", back_populates="invoice", cascade="all, delete-orphan"
    )
    validations: Mapped[List["ValidationRecord"]] = relationship(
        "ValidationRecord", back_populates="invoice", cascade="all, delete-orphan"
    )
    anomalies: Mapped[List["AnomalyRecord"]] = relationship(
        "AnomalyRecord", back_populates="invoice", cascade="all, delete-orphan"
    )
    audit_trail: Mapped[List["AuditTrailRecord"]] = relationship(
        "AuditTrailRecord", back_populates="invoice", cascade="all, delete-orphan", order_by="AuditTrailRecord.id"
    )

    __table_args__ = (
        Index("ix_invoices_vendor_total", "vendor_name", "total_amount"),
    )


class LineItemRecord(Base):
    """Itemized line items belonging to an invoice."""
    __tablename__ = "invoice_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    
    description: Mapped[str] = mapped_column(String(500), default="")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)

    invoice: Mapped["InvoiceRecord"] = relationship("InvoiceRecord", back_populates="line_items")


class ValidationRecord(Base):
    """Individual compliance rule evaluation outcome."""
    __tablename__ = "invoice_validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    
    rule_name: Mapped[str] = mapped_column(String(100), index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[str] = mapped_column(String(20), default="error")  # error, warning, info
    message: Mapped[str] = mapped_column(Text, default="")
    field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    invoice: Mapped["InvoiceRecord"] = relationship("InvoiceRecord", back_populates="validations")


class AnomalyRecord(Base):
    """Statistical and heuristic anomaly detection flags."""
    __tablename__ = "invoice_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    
    type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")

    invoice: Mapped["InvoiceRecord"] = relationship("InvoiceRecord", back_populates="anomalies")


class AuditTrailRecord(Base):
    """Immutable timestamped execution steps and human intervention history."""
    __tablename__ = "invoice_audit_trail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    
    step: Mapped[str] = mapped_column(String(100), index=True)
    timestamp: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")

    invoice: Mapped["InvoiceRecord"] = relationship("InvoiceRecord", back_populates="audit_trail")
