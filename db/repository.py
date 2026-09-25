"""
DocAgent Database Repository
============================
Data access layer for invoice persistence, human review management,
historical vendor spend querying for anomaly detection, and analytics aggregation.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import statistics
from sqlalchemy import select, func, desc, update
from sqlalchemy.orm import Session, joinedload
from db.models import (
    InvoiceRecord,
    LineItemRecord,
    ValidationRecord,
    AnomalyRecord,
    AuditTrailRecord,
    utc_now,
)


def save_processed_invoice(
    db: Session,
    workflow_result: Dict[str, Any],
    thread_id: str,
    filename: str = "document.pdf",
) -> InvoiceRecord:
    """
    Persist or update full invoice processing state, extracted data, line items,
    compliance validations, anomalies, and audit trail records.
    """
    extracted = workflow_result.get("extracted_data") or {}
    validations = workflow_result.get("validation_results") or []
    anomalies = workflow_result.get("anomalies") or []
    audit_trail = workflow_result.get("audit_trail") or []
    
    decision = workflow_result.get("decision", "pending")
    level = workflow_result.get("approval_level", "auto")
    risk_score = float(workflow_result.get("risk_score", 0.0))
    reasoning = workflow_result.get("decision_reasoning", "")
    is_duplicate = bool(workflow_result.get("is_duplicate", False))
    
    # Check if an existing record exists for this thread_id
    existing: Optional[InvoiceRecord] = db.scalar(
        select(InvoiceRecord).where(InvoiceRecord.thread_id == thread_id)
    )

    if existing:
        invoice = existing
        invoice.filename = filename
        invoice.vendor_name = extracted.get("vendor_name")
        invoice.vendor_id = extracted.get("vendor_id")
        invoice.invoice_number = extracted.get("invoice_number")
        invoice.invoice_date = extracted.get("invoice_date")
        invoice.due_date = extracted.get("due_date")
        invoice.currency = extracted.get("currency", "INR")
        invoice.subtotal = float(extracted.get("subtotal", 0.0) or 0.0)
        invoice.tax_amount = float(extracted.get("tax_amount", 0.0) or 0.0)
        invoice.total_amount = float(extracted.get("total_amount", 0.0) or 0.0)
        invoice.payment_terms = extracted.get("payment_terms")
        invoice.confidence_score = float(extracted.get("confidence_score", 1.0) or 1.0)
        invoice.visual_amount = extracted.get("visual_amount")
        invoice.visual_discrepancy_detected = bool(extracted.get("visual_discrepancy_detected", False))
        invoice.visual_notes = extracted.get("visual_notes")
        invoice.is_duplicate = is_duplicate
        invoice.risk_score = risk_score
        invoice.decision = decision
        invoice.approval_level = level
        invoice.decision_reasoning = reasoning
        invoice.status = "pending_review" if decision == "flag_review" else "completed"
        invoice.updated_at = utc_now()
        
        # Clear old children to replace with latest run
        invoice.line_items.clear()
        invoice.validations.clear()
        invoice.anomalies.clear()
        invoice.audit_trail.clear()
    else:
        invoice = InvoiceRecord(
            thread_id=thread_id,
            filename=filename,
            vendor_name=extracted.get("vendor_name"),
            vendor_id=extracted.get("vendor_id"),
            invoice_number=extracted.get("invoice_number"),
            invoice_date=extracted.get("invoice_date"),
            due_date=extracted.get("due_date"),
            currency=extracted.get("currency", "INR"),
            subtotal=float(extracted.get("subtotal", 0.0) or 0.0),
            tax_amount=float(extracted.get("tax_amount", 0.0) or 0.0),
            total_amount=float(extracted.get("total_amount", 0.0) or 0.0),
            payment_terms=extracted.get("payment_terms"),
            confidence_score=float(extracted.get("confidence_score", 1.0) or 1.0),
            visual_amount=extracted.get("visual_amount"),
            visual_discrepancy_detected=bool(extracted.get("visual_discrepancy_detected", False)),
            visual_notes=extracted.get("visual_notes"),
            is_duplicate=is_duplicate,
            risk_score=risk_score,
            decision=decision,
            approval_level=level,
            decision_reasoning=reasoning,
            status="pending_review" if decision == "flag_review" else "completed",
        )
        db.add(invoice)

    # 1. Add Line Items
    for item in extracted.get("line_items", []):
        invoice.line_items.append(
            LineItemRecord(
                description=item.get("description", ""),
                quantity=float(item.get("quantity", 1.0) or 1.0),
                unit_price=float(item.get("unit_price", 0.0) or 0.0),
                total=float(item.get("total", 0.0) or 0.0),
            )
        )

    # 2. Add Validations
    for val in validations:
        invoice.validations.append(
            ValidationRecord(
                rule_name=val.get("rule_name", "unknown"),
                passed=bool(val.get("passed", True)),
                severity=val.get("severity", "error"),
                message=val.get("message", ""),
                field=val.get("field"),
            )
        )

    # 3. Add Anomalies
    for anom in anomalies:
        invoice.anomalies.append(
            AnomalyRecord(
                type=anom.get("type", "unknown"),
                severity=anom.get("severity", "warning"),
                score=float(anom.get("score", 0.0) or 0.0),
                message=anom.get("message", ""),
            )
        )

    # 4. Add Audit Trail Entries
    for audit in audit_trail:
        invoice.audit_trail.append(
            AuditTrailRecord(
                step=audit.get("step", "general"),
                timestamp=audit.get("timestamp", utc_now().isoformat()),
                detail=audit.get("detail", ""),
            )
        )

    db.commit()
    db.refresh(invoice)
    return invoice


def get_invoice_by_id(db: Session, invoice_id: str) -> Optional[InvoiceRecord]:
    """Retrieve an invoice with all relationships eagerly loaded by primary ID."""
    stmt = (
        select(InvoiceRecord)
        .options(
            joinedload(InvoiceRecord.line_items),
            joinedload(InvoiceRecord.validations),
            joinedload(InvoiceRecord.anomalies),
            joinedload(InvoiceRecord.audit_trail),
        )
        .where(InvoiceRecord.id == invoice_id)
    )
    return db.scalar(stmt)


def get_invoice_by_thread_id(db: Session, thread_id: str) -> Optional[InvoiceRecord]:
    """Retrieve an invoice with all relationships eagerly loaded by LangGraph thread_id."""
    stmt = (
        select(InvoiceRecord)
        .options(
            joinedload(InvoiceRecord.line_items),
            joinedload(InvoiceRecord.validations),
            joinedload(InvoiceRecord.anomalies),
            joinedload(InvoiceRecord.audit_trail),
        )
        .where(InvoiceRecord.thread_id == thread_id)
    )
    return db.scalar(stmt)


def list_invoices(
    db: Session,
    status: Optional[str] = None,
    decision: Optional[str] = None,
    vendor_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[InvoiceRecord], int]:
    """List invoices with filtering, pagination, and total count."""
    stmt = select(InvoiceRecord).order_by(desc(InvoiceRecord.created_at))
    count_stmt = select(func.count(InvoiceRecord.id))

    if status:
        stmt = stmt.where(InvoiceRecord.status == status)
        count_stmt = count_stmt.where(InvoiceRecord.status == status)
    if decision:
        stmt = stmt.where(InvoiceRecord.decision == decision)
        count_stmt = count_stmt.where(InvoiceRecord.decision == decision)
    if vendor_name:
        stmt = stmt.where(InvoiceRecord.vendor_name.ilike(f"%{vendor_name}%"))
        count_stmt = count_stmt.where(InvoiceRecord.vendor_name.ilike(f"%{vendor_name}%"))

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.limit(limit).offset(offset)).unique().all())
    return items, total


def get_pending_reviews(db: Session) -> List[InvoiceRecord]:
    """Get all invoices currently queued for human manager/director approval."""
    stmt = (
        select(InvoiceRecord)
        .options(
            joinedload(InvoiceRecord.validations),
            joinedload(InvoiceRecord.anomalies),
        )
        .where(InvoiceRecord.status == "pending_review")
        .order_by(desc(InvoiceRecord.created_at))
    )
    return list(db.scalars(stmt).unique().all())


def record_human_decision(
    db: Session,
    thread_id: str,
    human_action: str,  # "approve" or "reject"
    reasoning: str = "",
    reviewer_name: str = "Manager",
) -> Optional[InvoiceRecord]:
    """Record human reviewer decision override and log to audit trail."""
    invoice = get_invoice_by_thread_id(db, thread_id)
    if not invoice:
        return None

    now = utc_now()
    final_decision = "auto_approve" if human_action == "approve" else "reject"
    final_status = "approved_by_human" if human_action == "approve" else "rejected_by_human"

    invoice.decision = final_decision
    invoice.status = final_status
    invoice.reviewed_by = reviewer_name
    invoice.reviewed_at = now
    invoice.review_notes = reasoning
    invoice.updated_at = now

    invoice.audit_trail.append(
        AuditTrailRecord(
            step="human_review",
            timestamp=now.isoformat(),
            detail=f"Human override by {reviewer_name}: {human_action.upper()} | Notes: {reasoning or 'No notes'}",
        )
    )

    db.commit()
    db.refresh(invoice)
    return invoice


def get_vendor_spend_history(db: Session, vendor_name: str) -> List[Dict[str, Any]]:
    """
    Retrieve past invoices for a given vendor to feed real historical data
    into the statistical anomaly detection engine (z-scores and spend distribution).
    """
    if not vendor_name:
        return []
    
    stmt = (
        select(InvoiceRecord.total_amount, InvoiceRecord.invoice_date, InvoiceRecord.invoice_number)
        .where(
            func.lower(InvoiceRecord.vendor_name) == vendor_name.strip().lower(),
            InvoiceRecord.status != "rejected"
        )
        .order_by(desc(InvoiceRecord.created_at))
        .limit(50)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "vendor_name": vendor_name,
            "total_amount": float(r[0]),
            "invoice_date": r[1],
            "invoice_number": r[2],
        }
        for r in rows
    ]


def get_analytics_summary(db: Session) -> Dict[str, Any]:
    """Compute executive aggregate KPIs for the analytics dashboard."""
    total_invoices = db.scalar(select(func.count(InvoiceRecord.id))) or 0
    total_spend = db.scalar(select(func.sum(InvoiceRecord.total_amount))) or 0.0
    avg_risk = db.scalar(select(func.avg(InvoiceRecord.risk_score))) or 0.0

    # Decision breakdown
    decision_counts = dict(
        db.execute(
            select(InvoiceRecord.decision, func.count(InvoiceRecord.id))
            .group_by(InvoiceRecord.decision)
        ).all()
    )

    # Status breakdown
    status_counts = dict(
        db.execute(
            select(InvoiceRecord.status, func.count(InvoiceRecord.id))
            .group_by(InvoiceRecord.status)
        ).all()
    )

    # Top vendors by total spend
    top_vendors = [
        {"vendor": v[0], "total": float(v[1]), "count": int(v[2])}
        for v in db.execute(
            select(InvoiceRecord.vendor_name, func.sum(InvoiceRecord.total_amount), func.count(InvoiceRecord.id))
            .where(InvoiceRecord.vendor_name.isnot(None))
            .group_by(InvoiceRecord.vendor_name)
            .order_by(desc(func.sum(InvoiceRecord.total_amount)))
            .limit(5)
        ).all()
    ]

    # Top anomaly types detected
    top_anomalies = [
        {"type": a[0], "count": int(a[1])}
        for a in db.execute(
            select(AnomalyRecord.type, func.count(AnomalyRecord.id))
            .group_by(AnomalyRecord.type)
            .order_by(desc(func.count(AnomalyRecord.id)))
            .limit(5)
        ).all()
    ]

    return {
        "total_invoices": total_invoices,
        "total_spend": round(float(total_spend), 2),
        "average_risk_score": round(float(avg_risk), 2),
        "decisions": decision_counts,
        "statuses": status_counts,
        "top_vendors": top_vendors,
        "top_anomalies": top_anomalies,
    }
