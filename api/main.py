from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from agent.graph import build_workflow
from tools.pdf_parser import pdf_to_text
from db.session import init_db, get_db
from db.repository import (
    save_processed_invoice,
    get_invoice_by_id,
    get_invoice_by_thread_id,
    list_invoices,
    get_pending_reviews,
    record_human_decision,
    get_analytics_summary,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    yield


app = FastAPI(
    title="DocAgent — Agentic Invoice Processing Engine",
    description="Agentic document workflow engine with multi-modal LLM extraction, compliance rules, statistical anomaly detection, and human review.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow CORS for UI interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = build_workflow()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "doc-agent-api", "version": "1.0.0"}


@app.post("/process")
async def process_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Process an uploaded invoice file (PDF/Image/Text) through the LangGraph agent workflow
    and persist results to database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    content = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    text = ""
    
    # Try to extract text based on file type
    if file.filename.lower().endswith(".pdf"):
        try:
            text = pdf_to_text(content)
        except Exception:
            pass  # Fall back to Gemini Multimodal
    else:
        # Fallback for text/markdown files
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            pass  # Fall back to Gemini Multimodal

    try:
        config = {"configurable": {"thread_id": file.filename}}
        result = agent.invoke({
            "document_text": text,
            "document_bytes": content,
            "mime_type": mime_type,
            "document_path": file.filename,
            "validation_results": [],
            "anomalies": [],
            "extraction_error": None,
            "extraction_retries": 0,
            "audit_trail": [],
            "messages": [],
        }, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent workflow failed: {str(e)}")
    
    # Check if graph is paused/interrupted
    state_snapshot = agent.get_state(config)
    is_paused = len(state_snapshot.tasks) > 0 and any(task.interrupts for task in state_snapshot.tasks)
    
    status = "pending_review" if is_paused else "completed"
    
    # Build complete response dict
    response_data = {
        "status": status,
        "thread_id": file.filename,
        "filename": file.filename,
        "extracted_data": result.get("extracted_data"),
        "decision": result.get("decision", "flag_review" if is_paused else "unknown"),
        "approval_level": result.get("approval_level", "unknown"),
        "risk_score": result.get("risk_score", 0.0),
        "decision_reasoning": result.get("decision_reasoning", ""),
        "anomalies": result.get("anomalies", []),
        "validation_results": result.get("validation_results", []),
        "audit_trail": result.get("audit_trail", []),
        "is_duplicate": result.get("is_duplicate", False),
    }

    # Persist to database
    try:
        saved_record = save_processed_invoice(db, response_data, thread_id=file.filename, filename=file.filename)
        response_data["db_id"] = saved_record.id
    except Exception as exc:
        # Don't fail the response if DB write encounters an error, but log
        response_data["db_warning"] = str(exc)

    return response_data


class ResumeRequest(BaseModel):
    action: str  # "approve" or "reject"
    reasoning: str = ""
    reviewer_name: str = "Manager"


@app.post("/resume/{thread_id}")
def resume_invoice(
    thread_id: str,
    payload: ResumeRequest,
    db: Session = Depends(get_db),
):
    """
    Resume an interrupted LangGraph invoice workflow with human approval/rejection.
    """
    from langgraph.types import Command
    
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = agent.get_state(config)
    
    is_paused = len(state_snapshot.tasks) > 0 and any(task.interrupts for task in state_snapshot.tasks)
    if not is_paused:
        raise HTTPException(status_code=400, detail="Graph is not currently paused.")
    
    # Send the human decision back to the interrupted node
    human_input = {
        "decision": "auto_approve" if payload.action == "approve" else "reject",
        "reasoning": payload.reasoning or f"Human explicitly {payload.action}d by {payload.reviewer_name}.",
    }
    
    try:
        result = agent.invoke(Command(resume=human_input), config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume agent: {str(e)}")
        
    # Update DB record with human decision
    record_human_decision(
        db=db,
        thread_id=thread_id,
        human_action=payload.action,
        reasoning=payload.reasoning,
        reviewer_name=payload.reviewer_name,
    )

    return {
        "status": "completed",
        "thread_id": thread_id,
        "invoice": result.get("extracted_data"),
        "decision": result.get("decision", "unknown"),
        "approval_level": result.get("approval_level", "unknown"),
        "risk_score": result.get("risk_score", 0.0),
        "reasoning": result.get("decision_reasoning", ""),
        "anomalies": result.get("anomalies", []),
        "validation_results": result.get("validation_results", []),
        "audit_trail": result.get("audit_trail", []),
    }


@app.get("/invoices")
def get_invoices(
    status: Optional[str] = Query(None, description="Filter by status (completed, pending_review, etc.)"),
    decision: Optional[str] = Query(None, description="Filter by decision (auto_approve, flag_review, reject)"),
    vendor: Optional[str] = Query(None, description="Filter by vendor name substring"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List processed invoices with pagination and filtering."""
    items, total = list_invoices(db, status=status, decision=decision, vendor_name=vendor, limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": inv.id,
                "thread_id": inv.thread_id,
                "filename": inv.filename,
                "vendor_name": inv.vendor_name,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "total_amount": inv.total_amount,
                "currency": inv.currency,
                "decision": inv.decision,
                "approval_level": inv.approval_level,
                "risk_score": inv.risk_score,
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in items
        ],
    }


@app.get("/invoices/{invoice_id}")
def get_invoice_detail(invoice_id: str, db: Session = Depends(get_db)):
    """Retrieve complete invoice details including line items, validations, anomalies, and audit log."""
    inv = get_invoice_by_id(db, invoice_id)
    if not inv:
        # Fallback to check by thread_id
        inv = get_invoice_by_thread_id(db, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")

    return {
        "id": inv.id,
        "thread_id": inv.thread_id,
        "filename": inv.filename,
        "vendor_name": inv.vendor_name,
        "vendor_id": inv.vendor_id,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "currency": inv.currency,
        "subtotal": inv.subtotal,
        "tax_amount": inv.tax_amount,
        "total_amount": inv.total_amount,
        "payment_terms": inv.payment_terms,
        "confidence_score": inv.confidence_score,
        "visual_amount": inv.visual_amount,
        "visual_discrepancy_detected": inv.visual_discrepancy_detected,
        "visual_notes": inv.visual_notes,
        "is_duplicate": inv.is_duplicate,
        "risk_score": inv.risk_score,
        "decision": inv.decision,
        "approval_level": inv.approval_level,
        "decision_reasoning": inv.decision_reasoning,
        "status": inv.status,
        "reviewed_by": inv.reviewed_by,
        "reviewed_at": inv.reviewed_at.isoformat() if inv.reviewed_at else None,
        "review_notes": inv.review_notes,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "line_items": [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total": item.total,
            }
            for item in inv.line_items
        ],
        "validations": [
            {
                "rule_name": v.rule_name,
                "passed": v.passed,
                "severity": v.severity,
                "message": v.message,
                "field": v.field,
            }
            for v in inv.validations
        ],
        "anomalies": [
            {
                "type": a.type,
                "severity": a.severity,
                "score": a.score,
                "message": a.message,
            }
            for a in inv.anomalies
        ],
        "audit_trail": [
            {
                "step": aud.step,
                "timestamp": aud.timestamp,
                "detail": aud.detail,
            }
            for aud in inv.audit_trail
        ],
    }


@app.get("/reviews/pending")
def list_pending_human_reviews(db: Session = Depends(get_db)):
    """List all invoices currently requiring manager or director review."""
    pending = get_pending_reviews(db)
    return {
        "pending_count": len(pending),
        "invoices": [
            {
                "id": inv.id,
                "thread_id": inv.thread_id,
                "vendor_name": inv.vendor_name,
                "invoice_number": inv.invoice_number,
                "total_amount": inv.total_amount,
                "currency": inv.currency,
                "approval_level": inv.approval_level,
                "risk_score": inv.risk_score,
                "reasoning": inv.decision_reasoning,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "failed_rules_count": sum(1 for v in inv.validations if not v.passed),
                "anomalies_count": len(inv.anomalies),
            }
            for inv in pending
        ],
    }


@app.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """Executive spend and accuracy analytics dashboard."""
    return get_analytics_summary(db)
