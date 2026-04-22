from __future__ import annotations

import json
import threading

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.ai.modify_jobs import MODIFY_JOB_STORE
from backend.ai.orchestrator import LevelAgentOrchestrator
from backend.ai.session_store import SESSION_CONTEXT_STORE
from backend.ai.schemas import (
    LevelAgentRequest,
    LevelAgentResponse,
    ModifyJobStartRequest,
    ModifyJobStatusResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionSummary,
)


router = APIRouter(prefix="/api/ai", tags=["ai"])
_ORCHESTRATOR: LevelAgentOrchestrator | None = None


def _get_orchestrator() -> LevelAgentOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = LevelAgentOrchestrator()
    return _ORCHESTRATOR


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(user_id: str = Query(default="local-user")) -> list[SessionSummary]:
    sessions = SESSION_CONTEXT_STORE.list_sessions(user_id)
    return [SessionSummary.model_validate({**item, "userId": item["user_id"], "sessionId": item["session_id"]}) for item in sessions]


@router.post("/sessions", response_model=SessionDetail)
def create_session(request: SessionCreateRequest) -> SessionDetail:
    detail = SESSION_CONTEXT_STORE.create_session(
        user_id=request.user_id,
        initial_level=request.level,
        title=request.title,
        session_id=request.session_id,
    )
    return SessionDetail.model_validate(
        {
            **detail,
            "userId": detail["user_id"],
            "sessionId": detail["session_id"],
            "messageCount": detail["message_count"],
            "workingLevel": detail.get("working_level"),
            "analysisSummary": detail.get("analysis_summary", {}),
            "lastIntent": detail.get("last_intent", {}),
        }
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, user_id: str = Query(default="local-user")) -> SessionDetail:
    detail = SESSION_CONTEXT_STORE.get_session(user_id=user_id, session_id=session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionDetail.model_validate(
        {
            **detail,
            "userId": detail["user_id"],
            "sessionId": detail["session_id"],
            "messageCount": detail["message_count"],
            "workingLevel": detail.get("working_level"),
            "analysisSummary": detail.get("analysis_summary", {}),
            "lastIntent": detail.get("last_intent", {}),
        }
    )


@router.post("/level-agent", response_model=LevelAgentResponse)
def level_agent(request: LevelAgentRequest) -> LevelAgentResponse:
    try:
        return _get_orchestrator().run(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail=f"AI agent failed: {error}") from error


@router.post("/level-agent/stream")
def level_agent_stream(request: LevelAgentRequest) -> StreamingResponse:
    def event_stream():
        try:
            for event in _get_orchestrator().run_stream(request):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except ValueError as error:
            payload = {"type": "error", "message": str(error)}
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        except RuntimeError as error:
            payload = {"type": "error", "message": str(error)}
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        except Exception as error:  # pragma: no cover - defensive boundary
            payload = {"type": "error", "message": f"AI agent failed: {error}"}
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/modify-jobs", response_model=ModifyJobStatusResponse)
def start_modify_job(request: ModifyJobStartRequest) -> ModifyJobStatusResponse:
    job = MODIFY_JOB_STORE.create_job()
    job_id = str(job["jobId"])
    payload = request.model_dump(mode="python", by_alias=True)

    def worker() -> None:
        try:
            MODIFY_JOB_STORE.update_job(
                job_id,
                status="running",
                stage="start",
                message="Modify job started.",
            )

            request_obj = LevelAgentRequest.model_validate(payload)
            result = _get_orchestrator().run_modify_job(
                request_obj,
                intent=request.intent,
                progress_callback=lambda event: MODIFY_JOB_STORE.update_job(
                    job_id,
                    status="running",
                    stage=event.get("stage", ""),
                    message=event.get("message", ""),
                    attempt=int(event.get("attempt", 0) or 0),
                ),
            )
            final_status = "completed" if result.get("updatedLevel") else "rejected"
            MODIFY_JOB_STORE.update_job(
                job_id,
                status=final_status,
                stage="complete" if final_status == "completed" else "rejected",
                message=result.get("message", ""),
                attempts=(result.get("modifyAgentOutput", {}) or {}).get("attempts", []),
                result=result,
            )
        except Exception as error:  # pragma: no cover - defensive boundary
            MODIFY_JOB_STORE.update_job(
                job_id,
                status="failed",
                stage="failed",
                message=f"Modify job failed: {error}",
            )

    threading.Thread(target=worker, daemon=True).start()
    return ModifyJobStatusResponse.model_validate(MODIFY_JOB_STORE.get_job(job_id))


@router.get("/modify-jobs/{job_id}", response_model=ModifyJobStatusResponse)
def get_modify_job(job_id: str) -> ModifyJobStatusResponse:
    job = MODIFY_JOB_STORE.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Modify job not found.")
    return ModifyJobStatusResponse.model_validate(job)
