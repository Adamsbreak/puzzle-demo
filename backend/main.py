from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.ai_routes import router as ai_router
from backend.ai.session_store import SESSION_CONTEXT_STORE


logging.basicConfig(
    level=getattr(logging, os.getenv("PUZZLE_AI_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


app = FastAPI(
    title="Puzzle AI Backend",
    version="0.2.0",
    description="LangGraph multi-agent orchestration backend for the V1 puzzle editor.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_router)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "puzzle-ai-backend",
        "provider": "langgraph-qwen",
        "base_url": os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model": os.getenv("LLM_MODEL") or os.getenv("DASHSCOPE_MODEL") or os.getenv("OPENAI_MODEL") or "qwen-flash",
        "api_key_present": bool(
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        ),
        "session_store": SESSION_CONTEXT_STORE.describe(),
    }
