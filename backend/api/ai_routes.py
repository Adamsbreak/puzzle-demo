from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ai.orchestrator import LevelAgentOrchestrator
from backend.ai.rag_service import PuzzleRAGService
from backend.ai.schemas import (
    LevelAgentRequest,
    LevelAgentResponse,
    RagEvalRequest,
    RagEvalResponse,
    RagSearchRequest,
    RagSearchResponse,
)


router = APIRouter(prefix="/api/ai", tags=["ai"])
rag_service = PuzzleRAGService()


@router.post("/level-agent", response_model=LevelAgentResponse)
def level_agent(request: LevelAgentRequest) -> LevelAgentResponse:
    try:
        orchestrator = LevelAgentOrchestrator(rag_service=rag_service)
        return orchestrator.run(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=f"AI agent failed: {error}") from error


@router.post("/rag/search", response_model=RagSearchResponse)
def rag_search(request: RagSearchRequest) -> RagSearchResponse:
    try:
        payload = rag_service.search(
            request.query,
            top_k=request.top_k,
            include_rules=request.include_rules,
            include_cases=request.include_cases,
            build_context=request.build_context,
        )
        return RagSearchResponse(**payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=f"RAG search failed: {error}") from error


@router.post("/rag/evaluate", response_model=RagEvalResponse)
def rag_evaluate(request: RagEvalRequest) -> RagEvalResponse:
    try:
        result = rag_service.evaluate(
            dataset_path=request.dataset_path,
            top_k_values=request.top_k_values,
            include_rules=request.include_rules,
            include_cases=request.include_cases,
        )
        overall = result.get("overall", {})
        summary = (
            f"Top-1 hit rate {overall.get('hit_rate@1', 0)}, "
            f"Top-3 hit rate {overall.get('hit_rate@3', 0)}, "
            f"MRR {overall.get('mrr', 0)}."
        )
        return RagEvalResponse(result=result, summary=summary)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=f"RAG evaluation failed: {error}") from error
