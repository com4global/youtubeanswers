import json
import os
import time
import uuid


_JOB_STORE: dict[str, dict] = {}


def create_job() -> str:
    job_id = uuid.uuid4().hex
    _JOB_STORE[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "result": None,
        "logs": []
    }
    return job_id


def update_job(job_id: str, *, status: str | None = None, progress: int | None = None,
               message: str | None = None, result: dict | None = None,
               log: str | None = None):
    job = _JOB_STORE.get(job_id)
    if not job:
        return

    if status is not None:
        job["status"] = status
    if progress is not None:
        job["progress"] = max(0, min(100, progress))
    if message is not None:
        job["message"] = message
    if result is not None:
        job["result"] = result
    if log is not None:
        job["logs"].append(log)
    job["updated_at"] = int(time.time())


def get_job(job_id: str) -> dict | None:
    return _JOB_STORE.get(job_id)


def persist_result(job_id: str, result: dict):
    data_dir = os.path.join("data", "courses")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, f"{job_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
