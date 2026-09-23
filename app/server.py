"""
FastAPI application — routes and static file serving.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import AVAILABLE_MODELS, GROQ_MODEL, STATIC_DIR
from app.engine import process_query
from app.feedback import get_recent_entries, update_user_feedback
from app.models import FeedbackRequest, HistoryEntry, QueryRequest, QueryResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Intelligent Analytics Query Engine",
        description="Natural language → SQL → DuckDB analytics",
        version="0.1.0",
    )

    # CORS — allow the frontend (same origin in production, any in dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:

    @app.get("/")
    async def serve_index():
        """Serve the chat UI."""
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_path, media_type="text/html")

    # Mount static files for any additional assets (CSS, JS, images)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.post("/api/query", response_model=QueryResponse)
    async def handle_query(request: QueryRequest):
        """
        Main endpoint: accept a natural language query, translate to SQL,
        execute against DuckDB, and return structured results.
        """
        try:
            response = process_query(request.query, model=request.model)
            return response
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Query processing failed: {str(exc)}",
            )

    @app.post("/api/feedback")
    async def handle_feedback(request: FeedbackRequest):
        """Record user feedback (thumbs up/down) on a query response."""
        updated = update_user_feedback(
            query=request.query,
            generated_sql=request.generated_sql,
            feedback=request.feedback,
        )
        if not updated:
            return {"status": "not_found", "message": "No matching entry found in log."}
        return {"status": "ok", "message": f"Feedback '{request.feedback}' recorded."}

    @app.get("/api/models")
    async def get_models():
        """Return the list of selectable models and the server default."""
        return {"models": AVAILABLE_MODELS, "default": GROQ_MODEL}

    @app.get("/api/history")
    async def get_history():
        """Return recent query history from the feedback log."""
        entries = get_recent_entries(limit=50)
        return {"entries": entries}
