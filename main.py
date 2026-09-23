"""
Entry point — starts the FastAPI server via uvicorn.

Usage:
    uv run python main.py
"""

import uvicorn

from app.server import create_app

app = create_app()

if __name__ == "__main__":
    print("\n Starting Intelligent Analytics Query Engine...")
    print("   http://localhost:8000\n")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
