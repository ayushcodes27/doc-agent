from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
        result = agent.invoke({
            "document_text": text,
            "document_bytes": content,
            "mime_type": mime_type,
            "document_path": file.filename,
            "validation_results": [],
            "anomalies": [],
            "audit_trail": [],
            "messages": [],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent workflow failed: {str(e)}")
    
    # Safely extract data from the final state
    return {
        "invoice": result.get("extracted_data"),
        "decision": result.get("decision", "unknown"),
        "approval_level": result.get("approval_level", "unknown"),
        "risk_score": result.get("risk_score", 0.0),
        "reasoning": result.get("decision_reasoning", ""),
        "anomalies": result.get("anomalies", []),
        "validation_results": result.get("validation_results", []),
        "audit_trail": result.get("audit_trail", []),
    }
