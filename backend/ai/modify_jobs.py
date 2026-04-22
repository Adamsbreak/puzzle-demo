from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any


class InMemoryModifyJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def create_job(self) -> dict[str, Any]:
        now = time.time()
        job_id = "job-" + uuid.uuid4().hex[:12]
        record = {
            "jobId": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "Modify job queued.",
            "attempt": 0,
            "attempts": [],
            "result": None,
            "createdAt": now,
            "updatedAt": now,
        }
        with self._lock:
            self._jobs[job_id] = record
        return copy.deepcopy(record)

    def update_job(self, job_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            self._jobs[job_id].update(updates)
            self._jobs[job_id]["updatedAt"] = time.time()
            return copy.deepcopy(self._jobs[job_id])

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job is not None else None


MODIFY_JOB_STORE = InMemoryModifyJobStore()
