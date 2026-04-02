from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.ai_routes import router as ai_router


app = FastAPI(
    title="Puzzle AI Backend",
    version="0.1.0",
    description="Minimal AI orchestration layer for the V1 puzzle editor.",
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
    }
