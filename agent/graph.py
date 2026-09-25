from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.state import AgentState
from agent.nodes import (
    extract_data,
    validate_compliance,
    check_duplicates,
    detect_anomalies,
    calculate_risk,
    make_decision,
    generate_report,
)


def route_after_extract(state: AgentState) -> str:
    """Route back to extract if extraction failed, up to 2 retries."""
    error = state.get("extraction_error")
    retries = state.get("extraction_retries", 0)
    if error and retries < 2:
        return "extract"
    return "validate"


def route_after_dedup(state: AgentState) -> str:
    """Short-circuit to risk_score if duplicate detected."""
    if state.get("is_duplicate"):
        return "risk_score"
    return "anomaly_check"


def build_workflow():
    """
    Constructs and compiles the LangGraph StateGraph workflow for DocAgent invoice processing.
    """
    workflow = StateGraph(AgentState)

    # 1. Register workflow nodes
    workflow.add_node("extract", extract_data)
    workflow.add_node("validate", validate_compliance)
    workflow.add_node("dedup", check_duplicates)
    workflow.add_node("anomaly_check", detect_anomalies)
    workflow.add_node("risk_score", calculate_risk)
    workflow.add_node("decide", make_decision)
    workflow.add_node("report", generate_report)

    # 2. Define execution flow & sequence
    workflow.set_entry_point("extract")
    
    # Extraction loop (self-correction)
    workflow.add_conditional_edges("extract", route_after_extract)
    
    workflow.add_edge("validate", "dedup")
    
    # Early-exit branch
    workflow.add_conditional_edges("dedup", route_after_dedup)
    
    workflow.add_edge("anomaly_check", "risk_score")
    workflow.add_edge("risk_score", "decide")
    workflow.add_edge("decide", "report")
    workflow.add_edge("report", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


def run_docagent(document_text: str, document_path: str = "document.pdf") -> Dict[str, Any]:
    """
    Convenience wrapper to run an invoice document through the compiled LangGraph workflow.
    """
    app = build_workflow()
    initial_state = {
        "document_text": document_text,
        "document_path": document_path,
        "extracted_data": None,
        "extraction_confidence": 0.0,
        "validation_results": [],
        "anomalies": [],
        "is_duplicate": False,
        "risk_score": 0.0,
        "decision": "pending",
        "decision_reasoning": "",
        "approval_level": "auto",
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
