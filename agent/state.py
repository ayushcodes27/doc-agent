from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State schema for the DocAgent invoice processing workflow.
    """
    # Input document
    document_text: str
    document_path: str
    document_bytes: Optional[bytes]
    mime_type: Optional[str]

    # Extracted data
    extracted_data: Optional[Dict[str, Any]]
    extraction_confidence: float

    # Compliance & Fraud Checks
    validation_results: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    is_duplicate: bool

    # Decision Engine Outputs
    risk_score: float          # 0.0 to 1.0 aggregate risk score
    decision: str              # "auto_approve" | "flag_review" | "reject"
    decision_reasoning: str    # Detailed reasoning explanation
    approval_level: str        # "auto" | "manager" | "director" | "cfo"

    # Audit & Chat Messages
    audit_trail: List[Dict[str, Any]]
    messages: Annotated[List[Any], add_messages]
