"""
API Routes — DataWeave v2
Main router with all core pipeline endpoints.

v2 changes:
  - P1: list_schemas includes is_custom flag
  - P6: Upload is async (BackgroundTasks), returns immediately
  - P6: New GET /jobs/{job_id}/status endpoint for polling
  - P6: New GET /jobs/{job_id}/result endpoint for fetching results
"""

import os
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from supabase import create_client

from core.orchestrator import Orchestrator
from core.job_manager import job_manager

router = APIRouter()

supabase = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", "")
)


# ── Health ───────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


# ── Schemas ──────────────────────────────────────────────────

@router.get("/schemas")
async def list_schemas():
    """List all available target schemas (system + custom)."""
    result = (
        supabase.table("target_schemas")
        .select("id, name, description, is_custom")
        .order("is_custom")             # System schemas first, then custom
        .order("created_at", desc=True)
        .execute()
    )
    return {"schemas": result.data}


# ── Upload (v2: Async) ──────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_schema_id: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    v2: Async upload — returns immediately with a job_id.
    The pipeline runs in the background. Poll GET /api/jobs/{job_id}/status
    to track progress.
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_extensions = {".csv", ".xlsx", ".xls", ".json", ".tsv"}
    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    # Create job record in DB first (so frontend can poll immediately)
    job_result = supabase.table("jobs").insert({
        "status": "uploaded",
        "original_filename": file.filename,
        "file_type": ext.lstrip("."),
        "file_size_bytes": len(file_bytes),
        "target_schema_id": target_schema_id,
    }).execute()

    job_id = job_result.data[0]["id"]

    # Register in job manager for progress polling
    job_manager.create(job_id)
    job_manager.update(job_id, "uploading", "File received, starting pipeline...")

    # Store references for the background task
    filename = file.filename

    # Run pipeline in background
    def run_pipeline_background():
        try:
            orchestrator = Orchestrator()
            result = orchestrator.start_pipeline_async(
                file_bytes, filename, target_schema_id, job_id
            )
            # Store result in job manager so status/result endpoints can return it
            job_manager.set_complete(job_id, result)
        except Exception as e:
            job_manager.set_error(job_id, str(e))

    background_tasks.add_task(run_pipeline_background)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Pipeline started. Poll GET /api/jobs/{job_id}/status for progress.",
    }


# ── Job Status (v2: New) ────────────────────────────────────

@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str):
    """
    Poll this endpoint to get the current pipeline stage for a job.
    Returns stage name, progress percentage, and human-readable message.
    """
    # First check in-memory job manager (fast, no DB hit)
    status = job_manager.get(job_id)
    if status:
        return status

    # Fallback: check database (for jobs that started before server restart)
    result = supabase.table("jobs").select("id, status, error_message").eq("id", job_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    job = result.data[0]
    return {
        "job_id": job["id"],
        "stage": job["status"],
        "message": job.get("error_message") or f"Status: {job['status']}",
        "progress": 100 if job["status"] == "complete" else -1,
        "elapsed_seconds": None,
        "error": job.get("error_message"),
        "has_result": job["status"] in ("complete", "awaiting_review"),
    }


# ── Job Result (v2: New) ────────────────────────────────────

@router.get("/jobs/{job_id}/result")
async def job_result(job_id: str):
    """
    Fetch the full pipeline result for a completed job.
    Only available after the job reaches 'awaiting_review' or 'complete' stage.
    """
    result = job_manager.get_result(job_id)
    if result:
        return result

    # If not in memory, the result may have been lost (server restart)
    raise HTTPException(
        status_code=404,
        detail="Result not found. The job may still be processing, or the server "
               "may have restarted. Check /api/jobs/{job_id}/status first."
    )


# ── Mapping Review ──────────────────────────────────────────

@router.put("/jobs/{job_id}/mappings/{mapping_id}")
async def update_mapping(job_id: str, mapping_id: str, body: dict):
    """
    Update a single mapping's status and/or target field.
    Body can include: status, target_field, transform_type
    """
    update_data = {}
    if "status" in body:
        if body["status"] not in ("approved", "rejected", "corrected"):
            raise HTTPException(status_code=400, detail="Invalid status")
        update_data["status"] = body["status"]
    if "target_field" in body:
        update_data["target_field"] = body["target_field"]
        if "status" not in update_data:
            update_data["status"] = "corrected"
    if "transform_type" in body:
        update_data["transform_type"] = body["transform_type"]

    if not update_data:
        raise HTTPException(status_code=400, detail="Nothing to update")

    result = supabase.table("mappings").update(update_data).eq("id", mapping_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return {"mapping": result.data[0]}


@router.post("/jobs/{job_id}/approve")
async def approve_all_mappings(job_id: str):
    """Approve all proposed mappings with confidence >= threshold."""
    # Get all proposed mappings for this job
    mappings = (
        supabase.table("mappings")
        .select("*")
        .eq("job_id", job_id)
        .eq("status", "proposed")
        .execute()
    )

    approved = 0
    for m in mappings.data:
        if m["confidence"] >= 70:
            supabase.table("mappings").update(
                {"status": "approved"}
            ).eq("id", m["id"]).execute()
            approved += 1

    return {"approved": approved, "total": len(mappings.data)}


# ── Complete Pipeline (Phase 2) ─────────────────────────────

@router.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str):
    """
    Run Phase 2 of the pipeline: Transform → Validate → Export.
    Call this after the user has reviewed and approved mappings.
    """
    try:
        orchestrator = Orchestrator()
        result = orchestrator.complete_pipeline(job_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Export ───────────────────────────────────────────────────

@router.get("/jobs/{job_id}/export")
async def export_csv(job_id: str):
    """Download the transformed data as CSV."""
    orchestrator = Orchestrator()
    csv_data = orchestrator._exports.get(job_id)

    if not csv_data:
        raise HTTPException(
            status_code=404,
            detail="Export not found. Run the complete pipeline first, "
                   "or the server may have restarted."
        )

    import io
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dataweave_{job_id[:8]}.csv"}
    )


# ── Events / Logs ───────────────────────────────────────────

@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str):
    """Get all event logs for a job (for debugging / audit trail)."""
    result = (
        supabase.table("events")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at")
        .execute()
    )
    return {"events": result.data}


# ── Job Details ─────────────────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job details including status, metadata, and mappings."""
    job = supabase.table("jobs").select("*").eq("id", job_id).execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")

    mappings = (
        supabase.table("mappings")
        .select("*")
        .eq("job_id", job_id)
        .execute()
    )

    return {
        "job": job.data[0],
        "mappings": mappings.data,
    }
