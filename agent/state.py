from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State schema for the DocAgent enterprise invoice processing workflow.
    """
    # Input document & source files
    document_text: str
    document_path: str
    document_bytes: Optional[bytes]
    mime_type: Optional[str]

    # Pre-LLM Hash Gate & Lineage
    file_hash: Optional[str]
    is_hash_blocked: bool
    supersedes_id: Optional[str]

    # Text Prep & Concrete Tampering Inspection
    tampering_detected: bool
    tampering_reasons: List[str]
    text_quality_score: float
    verifier_text: Optional[str]                    # Complete text including RapidOCR fallback for Reader B
    used_ocr_fallback: bool                         # True if RapidOCR fallback was used on scanned pages

    # Extraction & Dual-Reader State
    extraction_retries: int
    extraction_error: Optional[str]
    extracted_data: Optional[Dict[str, Any]]        # Primary Reader (Gemini Vision)
    reader_b_data: Optional[Dict[str, Any]]         # Secondary Reader (GitHub Models Text)
    reader_disagreements: List[str]                 # Disputed fields between Reader A & B
    verification_level: str                         # "full" | "partial" | "none"
    extraction_confidence: float

    # Compliance, Deduplication & Anomaly Checks
    validation_results: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    is_duplicate: bool
    is_near_duplicate: bool

    # Decision Engine Outputs
    risk_score: float                               # 0.0 to 1.0 aggregate risk score
    decision: str                                   # "auto_approve" | "flag_review" | "reject"
    decision_reasoning: str                         # Detailed reasoning explanation
    approval_level: str                             # "auto" | "manager" | "director"

    # Human-in-the-Loop & Audit Lineage
    human_verified: bool
    reentry_count: int                              # Max 2 correction loops allowed
    audit_trail: List[Dict[str, Any]]
    messages: Annotated[List[Any], add_messages]
