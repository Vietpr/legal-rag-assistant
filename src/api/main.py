from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.rag_chain import rag

# Path to frontend directory
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# load models on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load embedding model + ChromaDB + Gemini client on startup."""
    rag.init()
    yield


app = FastAPI(
    title="Legal RAG Assistant",
    description="Trợ lý pháp lý AI — Trả lời câu hỏi luật Việt Nam có trích dẫn Điều/Khoản",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# Models
class AskRequest(BaseModel):
    question: str
    version: str | None = None
    law_type: str | None = None


class AskResponse(BaseModel):
    answer: str
    citations: list[dict]
    chunks_used: int


class SearchResult(BaseModel):
    results: list[dict]
    total: int


# ─── Endpoints ───

@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serve the frontend UI at root URL."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "service": "Legal RAG Assistant"}


@app.get("/search", response_model=SearchResult)
def search(
    q: str = Query(..., description="Legal question"),
    version: str = Query(None, description="Filter: origin_law / update_law"),
    law_type: str = Query(None, description="Filter: Luật / Nghị định / Thông tư"),
):
    """Search ChromaDB only — does not call LLM."""
    results = rag.search(q, version=version, law_type=law_type)
    return SearchResult(results=results, total=len(results))


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Full RAG: search ChromaDB → Gemini → return answer with citations."""
    result = rag.ask(
        question=req.question,
        version=req.version,
        law_type=req.law_type,
    )
    return AskResponse(**result)
