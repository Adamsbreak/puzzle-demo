from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ai.orchestrator import LevelAgentOrchestrator
from backend.ai.schemas import LevelAgentRequest, LevelAgentResponse


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/level-agent", response_model=LevelAgentResponse)
def level_agent(request: LevelAgentRequest) -> LevelAgentResponse:
    try:
        orchestrator = LevelAgentOrchestrator()
        return orchestrator.run(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=f"AI agent failed: {error}") from error
