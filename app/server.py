"""Same-origin public demo API with bounded admission and session privacy."""

import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from app.config import (
    AVAILABLE_MODELS,
    GROQ_MODEL,
    STATIC_DIR,
    DEMO_MODE,
    MAX_REQUEST_BYTES,
    MAX_CONCURRENT_REQUESTS,
)
from app.database import get_connection, close_database, get_profile
from app.engine import process_query
from app.feedback import issue_receipt, record_feedback
from app.llm import close_client
from app.limits import RateLimiter, UsageError
from app.models import QueryRequest, QueryResponse, FeedbackRequest


class RequestBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Buffer at most MAX_REQUEST_BYTES before validation, including chunked requests.
        size, messages = 0, []
        deadline = time.monotonic() + 10
        while True:
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=max(0.001, deadline - time.monotonic())
                )
            except asyncio.TimeoutError:
                return await JSONResponse(
                    {"detail": "Request body timed out."}, status_code=408
                )(scope, receive, send)
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > MAX_REQUEST_BYTES:
                return await JSONResponse(
                    {"detail": "Request is too large."}, status_code=413
                )(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        await self.app(scope, replay, secure_send)


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        get_connection()
        try:
            yield
        finally:
            close_client()
            close_database()

    app = FastAPI(
        title="Sales Lens · AI Analytics",
        lifespan=lifespan,
        docs_url=None if DEMO_MODE else "/docs",
        redoc_url=None,
        openapi_url=None if DEMO_MODE else "/openapi.json",
    )
    app.add_middleware(RequestBoundary)
    limiter = RateLimiter()
    active = 0

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {
                "detail": "Invalid request. Enter a question (1–1000 characters) and check the supplied fields."
            },
            status_code=422,
        )

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/healthz")
    def health():
        return {"status": "ok", "dataset_rows": get_profile()["rows"]}

    @app.get("/api/models")
    def models():
        return {
            "models": AVAILABLE_MODELS,
            "default": GROQ_MODEL,
            "synthetic": True,
            "period": "January–March 2024",
        }

    @app.get("/api/history")
    def history():
        raise HTTPException(
            410,
            "History is stored only in your browser tab. No public server history is available.",
        )

    @app.post("/api/query", response_model=QueryResponse)
    async def query(body: QueryRequest, request: Request):
        nonlocal active
        if body.model is not None and body.model not in AVAILABLE_MODELS:
            raise HTTPException(422, "Choose one of the available models.")
        if DEMO_MODE and body.api_key:
            raise HTTPException(
                422, "This demo uses a server-managed key. Do not submit credentials."
            )
        try:
            limiter.check(request.client.host if request.client else "unknown")
        except UsageError as exc:
            raise HTTPException(
                exc.status_code, str(exc), headers={"Retry-After": "60"}
            ) from None
        if active >= MAX_CONCURRENT_REQUESTS:
            raise HTTPException(
                429,
                "The demo is busy. Please try again shortly.",
                headers={"Retry-After": "10"},
            )
        active += 1
        session = request.cookies.get("analytics_session", "")
        if len(session) != 48 or not all(c in "0123456789abcdef" for c in session):
            session = secrets.token_hex(24)
        try:
            response = await run_in_threadpool(
                process_query,
                body.query,
                model=body.model,
                api_key=body.api_key,
                cache_scope=session,
            )
            if response.error_code:
                status = (
                    429
                    if response.error_code in {"budget", "provider_rate_limit"}
                    else 503
                    if response.error_code
                    in {"unavailable", "provider_failure", "provider_access"}
                    else 422
                )
                return JSONResponse(
                    {
                        "detail": str(response.result).removeprefix("Error: "),
                        "error_code": response.error_code,
                    },
                    status_code=status,
                    headers={"Retry-After": "60"} if status == 429 else None,
                )
            response.feedback_id = issue_receipt(session)
            start = time.perf_counter()
            payload = response.model_dump(mode="json")
            payload["timings_ms"]["serialization"] = round(
                (time.perf_counter() - start) * 1000, 3
            )
            result = JSONResponse(payload)
            result.set_cookie(
                "analytics_session",
                session,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
            )
            return result
        except Exception:
            raise HTTPException(
                500, "The query could not be completed. Please try again."
            ) from None
        finally:
            active -= 1

    @app.post("/api/feedback")
    async def feedback(body: FeedbackRequest, request: Request):
        if not record_feedback(
            body.feedback_id,
            request.cookies.get("analytics_session", ""),
            body.feedback,
        ):
            raise HTTPException(
                404, "This feedback link has expired or belongs to another session."
            )
        return {"status": "ok", "message": "Feedback recorded. Thank you."}

    return app
