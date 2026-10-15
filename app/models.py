"""
Pydantic models for API request/response schemas and internal data structures.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, field_validator


class QueryRequest(BaseModel):
    """Incoming natural-language query from the frontend."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter an analytics question")
        return value

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language analytics question",
    )
    model: str | None = Field(
        None,
        description="Groq model id to use for this query; defaults to server config",
    )
    api_key: str | None = Field(
        None,
        max_length=256,
        repr=False,
        exclude=True,
        description="Optional Groq API key for this request; overrides the server key",
    )


class QueryResponse(BaseModel):
    """Full response returned to the frontend."""

    query: str
    generated_sql: str
    generated_logic: str
    result: list[dict] | str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    attempts: int = Field(
        1, description="Number of generation attempts used for this request"
    )
    cache_hit: bool = Field(
        False, description="Whether this answer came from the app cache"
    )
    response_time_ms: int = Field(
        0, description="Server-side processing time in milliseconds"
    )
    model: str = Field("", description="Groq model id used to generate this response")
    feedback_id: str = ""
    error_code: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    dataset_version: str = ""
    row_limit: int = 200


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: str = Field(..., min_length=20, max_length=100)
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

    sql: str = Field(
        ..., min_length=1, max_length=12000, description="DuckDB-compatible SQL query"
    )
    logic: str = Field(
        ..., max_length=2000, description="Step-by-step logic explanation"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Self-assessed confidence"
    )
    explanation: str = Field(
        ..., max_length=2000, description="Human-readable answer explanation"
    )
