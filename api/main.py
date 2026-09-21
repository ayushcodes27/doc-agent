from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent.graph import build_workflow
from tools.pdf_parser import pdf_to_text

app = FastAPI(title="DocAgent — Agentic Invoice Processor")

# Allow CORS for UI interaction if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = build_workflow()

@app.post("/process")
async def process_invoice(file: UploadFile = File(...)):
    """
    Process an uploaded invoice file (PDF/Image/Text) through the LangGraph agent workflow.
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
            pass # Fall back to Gemini Multimodal
    else:
        # Fallback for text files
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            pass # Fall back to Gemini Multimodal

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
    
    # Safely extract data from the final state
    return {
        "status": status,
        "thread_id": file.filename,
        "invoice": result.get("extracted_data"),
        "decision": result.get("decision", "flag_review" if is_paused else "unknown"),
        "approval_level": result.get("approval_level", "unknown"),
        "risk_score": result.get("risk_score", 0.0),
        "reasoning": result.get("decision_reasoning", ""),
        "anomalies": result.get("anomalies", []),
        "validation_results": result.get("validation_results", []),
        "audit_trail": result.get("audit_trail", []),
    }

class ResumeRequest(BaseModel):
    action: str  # "approve" or "reject"
    reasoning: str = ""

@app.post("/resume/{thread_id}")
def resume_invoice(thread_id: str, payload: ResumeRequest):
    """
    Resume an interrupted graph with human input.
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
        "reasoning": payload.reasoning or f"Human explicitly {payload.action}d."
    }
    
    try:
        result = agent.invoke(Command(resume=human_input), config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume agent: {str(e)}")
        
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
