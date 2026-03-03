"""
Job Manager — In-memory progress tracker for async pipeline execution.

Tracks which stage each job is in and provides a lightweight status
endpoint for the frontend to poll. This avoids hitting Supabase on
every poll — we only read from memory.

Stages (in order):
  1. uploading    — File received, saving to memory
  2. ingesting    — Ingestion Agent parsing file
  3. mapping      — Pattern Agent + Schema Agent mapping columns
  4. awaiting_review — Paused for human review
  5. transforming — Transform Agent applying mappings
  6. validating   — Validation Agent checking quality
  7. complete     — Done, results ready
  8. failed       — Error occurred

Each stage has:
  - stage name
  - human-readable message
  - percentage (0-100) representing overall pipeline progress
"""

import time
from dataclasses import dataclass, field
from typing import Optional


# Overall progress weights for each stage (must sum to 100)
STAGE_PROGRESS = {
    "uploading":        5,
    "ingesting":        15,
    "mapping":          35,
    "awaiting_review":  40,   # Phase 1 done
    "transforming":     60,
    "validating":       80,
    "complete":         100,
    "failed":           -1,   # Special case
}


@dataclass
class JobProgress:
    """Snapshot of a job's current progress."""
    job_id: str
    stage: str = "uploading"
    message: str = "Starting pipeline..."
    progress: int = 0       # 0-100
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: Optional[str] = None
    result: Optional[dict] = None  # Populated when complete


class JobManager:
    """
    Thread-safe(ish) in-memory job progress tracker.

    Usage:
        manager = JobManager()
        manager.create("job-123")
        manager.update("job-123", "ingesting", "Parsing CSV file...")
        status = manager.get("job-123")
    """

    def __init__(self):
        self._jobs: dict[str, JobProgress] = {}

    def create(self, job_id: str) -> JobProgress:
        """Register a new job for tracking."""
        progress = JobProgress(job_id=job_id)
        self._jobs[job_id] = progress
        return progress

    def update(self, job_id: str, stage: str, message: str = ""):
        """Update a job's current stage and message."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.stage = stage
        job.message = message or f"Stage: {stage}"
        job.progress = STAGE_PROGRESS.get(stage, 0)
        job.updated_at = time.time()

    def set_error(self, job_id: str, error: str):
        """Mark a job as failed with an error message."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.stage = "failed"
        job.message = "Pipeline failed"
        job.progress = STAGE_PROGRESS["failed"]
        job.error = error
        job.updated_at = time.time()

    def set_complete(self, job_id: str, result: dict = None):
        """Mark a job as complete with optional result data."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.stage = "complete"
        job.message = "Pipeline complete"
        job.progress = 100
        job.result = result
        job.updated_at = time.time()

    def get(self, job_id: str) -> Optional[dict]:
        """Get current status as a dict (for API responses)."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        elapsed = time.time() - job.started_at

        return {
            "job_id": job.job_id,
            "stage": job.stage,
            "message": job.message,
            "progress": job.progress,
            "elapsed_seconds": round(elapsed, 1),
            "error": job.error,
            "has_result": job.result is not None,
        }

    def get_result(self, job_id: str) -> Optional[dict]:
        """Get the stored result for a completed job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return job.result

    def cleanup(self, job_id: str):
        """Remove a job from the tracker (after result has been fetched)."""
        self._jobs.pop(job_id, None)

    def cleanup_old(self, max_age_seconds: int = 3600):
        """Remove jobs older than max_age_seconds."""
        now = time.time()
        stale = [
            jid for jid, j in self._jobs.items()
            if now - j.started_at > max_age_seconds
        ]
        for jid in stale:
            del self._jobs[jid]


# ── Singleton ────────────────────────────────────────────────
# One global instance shared across the app

job_manager = JobManager()
