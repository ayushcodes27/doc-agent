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
    workflow.add_edge("extract", "validate")
    workflow.add_edge("validate", "dedup")
    workflow.add_edge("dedup", "anomaly_check")
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
        "audit_trail": [],
        "messages": [],
    }
    config = {"configurable": {"thread_id": document_path}}
    return app.invoke(initial_state, config=config)
