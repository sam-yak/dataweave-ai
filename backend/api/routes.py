"""
API Routes — FastAPI endpoints for DataWeave AI
Full pipeline with Orchestrator + all 5 agents
"""

import os
import re
import math
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, EmailStr
from supabase import create_client
from core.orchestrator import Orchestrator
from core.job_manager import job_manager

router = APIRouter()

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", "")
)

# Initialize orchestrator (contains all agents)
orchestrator = Orchestrator()

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


# ── JSON Sanitizer ───────────────────────────────────────────

def sanitize_for_json(obj):
    """Recursively replace NaN/Infinity with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


# ── Waitlist Endpoint ─────────────────────────────────────────

class WaitlistRequest(BaseModel):
    email: str


@router.post("/waitlist")
async def join_waitlist(request: WaitlistRequest):
    """Add an email to the waitlist."""
    email = request.email.strip().lower()

    # Basic email validation
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    # Check if already on waitlist
    existing = supabase.table("waitlist").select("id").eq("email", email).execute()
    if existing.data:
        return {"status": "already_registered", "message": "You're already on the list!"}

    # Insert
    supabase.table("waitlist").insert({"email": email}).execute()
    return {"status": "success", "message": "You're on the list!"}


@router.get("/waitlist/count")
async def waitlist_count():
    """Get the current waitlist count."""
    result = supabase.table("waitlist").select("id", count="exact").execute()
    return {"count": result.count}


# ── Schema Endpoints ─────────────────────────────────────────

@router.get("/schemas")
async def list_schemas():
    """List all available target schemas (system + custom)."""
    result = (supabase.table("target_schemas")
              .select("id, name, description, is_custom")
              .order("is_custom")  # System schemas first, then custom
              .order("created_at", desc=True)
              .execute()
    )
    return {"schemas": result.data}

@router.get("/schemas/{schema_id}")
async def get_schema(schema_id: str):
    """Get a specific target schema with its field definitions."""
    result = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    return {"schema": result.data[0]}


# ── Pipeline Endpoints ───────────────────────────────────────

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
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    allowed_extensions = {".csv", ".xlsx", ".xls", ".json", ".tsv"}
    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}"
        )

    # Create job record in DB first (so frontend can reference immediately)
    job_result = supabase.table("jobs").insert({
        "status": "uploaded",
        "original_filename": file.filename,
        "file_type": ext.lstrip("."),
        "file_size_bytes": len(file_bytes),
        "target_schema_id": target_schema_id,
    }).execute()

    job_id = job_result.data[0]["id"]

    # Register in job manager for in-memory progress polling
    job_manager.create(job_id)
    job_manager.update(job_id, "uploading", "File received, starting pipeline...")

    # Store filename for background closure
    filename = file.filename

    def run_pipeline_background():
        try:
            result = orchestrator.start_pipeline_async(
                file_bytes, filename, target_schema_id, job_id
            )
            job_manager.set_complete(job_id, sanitize_for_json(result))
        except Exception as e:
            job_manager.set_error(job_id, str(e))

    background_tasks.add_task(run_pipeline_background)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Pipeline started. Poll GET /api/jobs/{job_id}/status for progress.",
    }


# ── Job Status Polling (v2) ─────────────────────────────────

@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str):
    """
    Poll this endpoint for real-time pipeline progress.
    Returns stage name, progress %, and human-readable message.
    """
    # Check in-memory job manager first (fast, no DB hit)
    status = job_manager.get(job_id)
    if status:
        return status

    # Fallback: check database (for jobs from before a server restart)
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


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: str):
    """
    Fetch the full pipeline result for a completed job.
    Available after job reaches 'awaiting_review' or 'complete'.
    """
    result = job_manager.get_result(job_id)
    if result:
        return sanitize_for_json(result)

    raise HTTPException(
        status_code=404,
        detail="Result not found. The job may still be processing, or the server "
               "may have restarted. Check /api/jobs/{job_id}/status first."
    )


# ── Complete Pipeline (Phase 2) ──────────────────────────────

@router.post("/jobs/{job_id}/complete")
async def complete_pipeline(job_id: str):
    """
    Phase 2: Transform → Validate → Export.
    Call this after reviewing and approving mappings.
    Unreviewed high-confidence mappings are auto-approved.
    Unreviewed low-confidence mappings are auto-rejected.
    """
    try:
        result = orchestrator.complete_pipeline(job_id)
        return sanitize_for_json(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@router.post("/jobs/{job_id}/export/csv")
async def export_csv(job_id: str):
    """Download the transformed data as a clean CSV file."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Job is not complete yet. Run /complete first.")

    csv_data = orchestrator._exports.get(job_id)
    if not csv_data:
        raise HTTPException(
            status_code=410,
            detail="Export data expired (server may have restarted). Re-upload the file and run the pipeline again."
        )

    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=clean_{job['original_filename']}"}
    )


# ── Job Endpoints ────────────────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status and details."""
    result = supabase.table("jobs").select("*").eq("id", job_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": result.data[0]}


@router.get("/jobs/{job_id}/columns")
async def get_job_columns(job_id: str):
    """Get all columns detected for a job."""
    result = supabase.table("columns").select("*").eq("job_id", job_id).execute()
    return {"columns": result.data}


@router.get("/jobs/{job_id}/mappings")
async def get_job_mappings(job_id: str):
    """Get all mapping proposals for a job."""
    result = (
        supabase.table("mappings")
        .select("*")
        .eq("job_id", job_id)
        .order("confidence", desc=True)
        .execute()
    )
    return {"mappings": result.data}


@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str):
    """Get the agent activity log for a job."""
    result = (
        supabase.table("events")
        .select("*")
        .eq("job_id", job_id)
        .order("created_at", desc=False)
        .execute()
    )
    return {"events": result.data}


# ── Mapping Review Endpoints (HITL) ──────────────────────────

@router.post("/jobs/{job_id}/mappings/{mapping_id}/approve")
async def approve_mapping(job_id: str, mapping_id: str):
    """Approve a proposed mapping. Teaches the Pattern Agent."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    supabase.table("mappings").update({"status": "approved"}).eq("id", mapping_id).execute()

    job = _get_job(job_id)
    if job and mapping["target_field"]:
        orchestrator.schema_agent.pattern_agent.record_approval(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            target_field=mapping["target_field"],
            transform_type=mapping.get("transform_type"),
        )

    _log_event(job_id, "review", "mapping_approved",
              f"Approved: '{mapping['source_name']}' → '{mapping['target_field']}'")

    return {"status": "approved", "mapping_id": mapping_id}


@router.post("/jobs/{job_id}/mappings/{mapping_id}/reject")
async def reject_mapping(job_id: str, mapping_id: str):
    """Reject a proposed mapping. Teaches the Pattern Agent."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    supabase.table("mappings").update({"status": "rejected"}).eq("id", mapping_id).execute()

    job = _get_job(job_id)
    if job and mapping["target_field"]:
        orchestrator.schema_agent.pattern_agent.record_rejection(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            target_field=mapping["target_field"],
        )

    _log_event(job_id, "review", "mapping_rejected",
              f"Rejected: '{mapping['source_name']}' → '{mapping['target_field']}'")

    return {"status": "rejected", "mapping_id": mapping_id}


@router.post("/jobs/{job_id}/mappings/{mapping_id}/correct")
async def correct_mapping(job_id: str, mapping_id: str, correct_target: str = Form(...)):
    """Correct a mapping to a different target field."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_target = mapping["target_field"]

    supabase.table("mappings").update({
        "target_field": correct_target,
        "status": "corrected",
        "agent_source": "manual",
    }).eq("id", mapping_id).execute()

    job = _get_job(job_id)
    if job:
        orchestrator.schema_agent.pattern_agent.record_correction(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            wrong_target=old_target,
            correct_target=correct_target,
        )

    _log_event(job_id, "review", "mapping_corrected",
              f"Corrected: '{mapping['source_name']}' from '{old_target}' to '{correct_target}'")

    return {"status": "corrected", "mapping_id": mapping_id, "new_target": correct_target}


@router.post("/jobs/{job_id}/mappings/approve-all")
async def approve_all_mappings(job_id: str, min_confidence: float = 85):
    """Bulk approve all mappings above a confidence threshold."""
    mappings = (
        supabase.table("mappings")
        .select("*")
        .eq("job_id", job_id)
        .eq("status", "proposed")
        .gte("confidence", min_confidence)
        .execute()
    )

    approved_count = 0
    for mapping in mappings.data:
        supabase.table("mappings").update({"status": "approved"}).eq("id", mapping["id"]).execute()

        job = _get_job(job_id)
        if job and mapping["target_field"]:
            orchestrator.schema_agent.pattern_agent.record_approval(
                target_schema_id=job["target_schema_id"],
                source_name=mapping["source_name"],
                target_field=mapping["target_field"],
                transform_type=mapping.get("transform_type"),
            )
        approved_count += 1

    _log_event(job_id, "review", "bulk_approved",
              f"Bulk approved {approved_count} mappings with confidence >= {min_confidence}%")

    return {"approved_count": approved_count, "min_confidence": min_confidence}


# ── Stats Endpoint ───────────────────────────────────────────

@router.get("/stats/patterns")
async def get_pattern_stats():
    """Get pattern learning statistics and LLM usage metrics."""
    stats = orchestrator.schema_agent.pattern_agent.get_stats()
    llm_stats = orchestrator.schema_agent.llm_router.get_stats()
    return {"patterns": stats, "llm": llm_stats}


# ── Helper Functions ─────────────────────────────────────────

def _get_job(job_id: str) -> dict:
    result = supabase.table("jobs").select("*").eq("id", job_id).execute()
    return result.data[0] if result.data else None


def _get_mapping(mapping_id: str) -> dict:
    result = supabase.table("mappings").select("*").eq("id", mapping_id).execute()
    return result.data[0] if result.data else None


def _log_event(job_id: str, agent: str, event_type: str, message: str):
    supabase.table("events").insert({
        "job_id": job_id,
        "agent": agent,
        "event_type": event_type,
        "message": message,
        "metadata": {},
    }).execute()
