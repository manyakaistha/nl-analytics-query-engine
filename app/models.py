"""
Pydantic models for API request/response schemas and internal data structures.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Incoming natural-language query from the frontend."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language analytics question")
    model: str | None = Field(None, description="Groq model id to use for this query; defaults to server config")


class QueryResponse(BaseModel):
    """Full response returned to the frontend."""
    query: str
    generated_sql: str
    generated_logic: str
    result: list[dict] | str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    attempts: int = Field(1, description="Number of generation attempts used for this request")
    cache_hit: bool = Field(False, description="Whether this answer came from the app cache")
    response_time_ms: int = Field(0, description="Server-side processing time in milliseconds")
    model: str = Field("", description="Groq model id used to generate this response")


class FeedbackRequest(BaseModel):
    """User feedback on a query response (thumbs up/down)."""
    query: str
    generated_sql: str
    feedback: str = Field(..., pattern="^(positive|negative)$")


class HistoryEntry(BaseModel):
    """A single entry from the feedback log."""
    timestamp: str
    query: str
    generated_sql: str
    status: str
    confidence_score: float


class LLMGeneratedOutput(BaseModel):
    """
    The JSON structure we instruct the LLM to produce.
    Parsed from the Groq response body.
    """
    sql: str = Field(..., description="DuckDB-compatible SQL query")
    logic: str = Field(..., description="Step-by-step logic explanation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Self-assessed confidence")
    explanation: str = Field(..., description="Human-readable answer explanation")
