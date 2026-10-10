from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.state import AgentState
from agent.nodes import (
    check_file_hash_node,
    prepare_source_node,
    extract_data,
    handle_extraction_failed,
    verify_reader_b_node,
    compare_and_verify_node,
    legibility_gate_node,
    validate_compliance,
    check_duplicates,
    detect_anomalies,
    calculate_risk,
    make_decision,
    generate_report,
)


def route_after_hash_gate(state: AgentState) -> str:
    """Route directly to report if identical active file hash is already processed."""
    if state.get("is_hash_blocked"):
        return "report"
    return "prepare_source"


def route_after_extract(state: AgentState) -> str:
    """Route back to extract if extraction failed (up to 2 retries); route to extraction_failed if persistent."""
    error = state.get("extraction_error")
    data = state.get("extracted_data")
    retries = state.get("extraction_retries", 0)

    if (error or not data) and retries < 2:
        return "extract"
    elif error or not data:
        return "extraction_failed"
    return "verify_b"


def route_after_dedup(state: AgentState) -> str:
    """Short-circuit to risk_score if duplicate detected."""
    if state.get("is_duplicate"):
        return "risk_score"
    return "anomaly_check"


def build_workflow():
    """
    Constructs and compiles the enterprise LangGraph StateGraph workflow
    with pre-LLM hash gating, dual-reader verification, and human-in-the-loop safeguards.
    """
    workflow = StateGraph(AgentState)

    # 1. Register workflow nodes
    workflow.add_node("file_hash_gate", check_file_hash_node)
    workflow.add_node("prepare_source", prepare_source_node)
    workflow.add_node("extract", extract_data)
    workflow.add_node("extraction_failed", handle_extraction_failed)
    workflow.add_node("verify_b", verify_reader_b_node)
    workflow.add_node("compare_verify", compare_and_verify_node)
    workflow.add_node("legibility_gate", legibility_gate_node)
    workflow.add_node("validate", validate_compliance)
    workflow.add_node("dedup", check_duplicates)
    workflow.add_node("anomaly_check", detect_anomalies)
    workflow.add_node("risk_score", calculate_risk)
    workflow.add_node("decide", make_decision)
    workflow.add_node("report", generate_report)

    # 2. Define execution flow & sequence
    workflow.set_entry_point("file_hash_gate")

    # Hash gate branch
    workflow.add_conditional_edges("file_hash_gate", route_after_hash_gate)
    workflow.add_edge("prepare_source", "extract")

    # Extraction loop / failure branch
    workflow.add_conditional_edges("extract", route_after_extract)
    workflow.add_edge("extraction_failed", "report")

    # Dual-reader verifier & legibility gate pipeline
    workflow.add_edge("verify_b", "compare_verify")
    workflow.add_edge("compare_verify", "legibility_gate")
    workflow.add_edge("legibility_gate", "validate")
    workflow.add_edge("validate", "dedup")

    # Early-exit branch for duplicates
    workflow.add_conditional_edges("dedup", route_after_dedup)

    workflow.add_edge("anomaly_check", "risk_score")
    workflow.add_edge("risk_score", "decide")
    workflow.add_edge("decide", "report")
    workflow.add_edge("report", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


def run_docagent(
    document_text: str = "",
    document_path: str = "document.pdf",
    document_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper to run an invoice document through the compiled LangGraph workflow.
    """
    app = build_workflow()
    initial_state = {
        "document_text": document_text,
        "document_path": document_path,
        "document_bytes": document_bytes,
        "mime_type": mime_type or ("application/pdf" if document_path.endswith(".pdf") else None),
        "file_hash": None,
        "is_hash_blocked": False,
        "supersedes_id": None,
        "tampering_detected": False,
        "tampering_reasons": [],
        "text_quality_score": 1.0,
        "extracted_data": None,
        "reader_b_data": None,
        "reader_disagreements": [],
        "verification_level": "full" if (not document_text and not document_bytes) else "none",
        "extraction_confidence": 0.0,
        "validation_results": [],
        "anomalies": [],
        "is_duplicate": False,
        "is_near_duplicate": False,
        "risk_score": 0.0,
        "decision": "pending",
        "decision_reasoning": "",
        "approval_level": "auto",
        "human_verified": False,
        "reentry_count": 0,
        "extraction_retries": 0,
        "extraction_error": None,
        "audit_trail": [],
        "messages": [],
    }
    config = {"configurable": {"thread_id": document_path}}
    result = app.invoke(initial_state, config=config)
    state_snapshot = app.get_state(config)

    is_paused = len(state_snapshot.tasks) > 0 and any(task.interrupts for task in state_snapshot.tasks)
    if is_paused:
        interrupt_val = state_snapshot.tasks[0].interrupts[0].value
        final_dict = dict(state_snapshot.values)
        final_dict["decision"] = interrupt_val.get("decision", "flag_review")
        final_dict["approval_level"] = interrupt_val.get("approval_level", "auto")
        final_dict["decision_reasoning"] = interrupt_val.get("reasoning", "")
        return final_dict

    return dict(state_snapshot.values) if state_snapshot and state_snapshot.values else result
