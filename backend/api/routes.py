"""
API Routes — FastAPI endpoints for DataWeave AI
"""

import os
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from supabase import create_client
from agents.ingestion import IngestionAgent

router = APIRouter()

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", "")
)

# Initialize agents
ingestion_agent = IngestionAgent()

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.get("/schemas")
async def list_schemas():
    """List all available target schemas."""
    result = supabase.table("target_schemas").select("id, name, description").execute()
    return {"schemas": result.data}


@router.get("/schemas/{schema_id}")
async def get_schema(schema_id: str):
    """Get a specific target schema with its fields."""
    result = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    return {"schema": result.data[0]}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_schema_id: str = Form(...)
):
    """
    Upload a file for processing.
    Creates a job and runs the Ingestion Agent.
    """
    # Validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Validate target schema exists
    schema_result = supabase.table("target_schemas").select("id").eq("id", target_schema_id).execute()
    if not schema_result.data:
        raise HTTPException(status_code=404, detail="Target schema not found")

    # Create job record
    job_result = supabase.table("jobs").insert({
        "status": "uploaded",
        "original_filename": file.filename,
        "file_type": file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "unknown",
        "file_size_bytes": len(file_bytes),
        "target_schema_id": target_schema_id,
    }).execute()

    job = job_result.data[0]
    job_id = job["id"]

    # Log event
    _log_event(job_id, "orchestrator", "job_created", f"Job created for {file.filename}")

    # Run Ingestion Agent
    try:
        _log_event(job_id, "ingestion", "started", "Ingestion Agent starting...")
        _update_job_status(job_id, "ingesting")

        df, metadata = ingestion_agent.process(file_bytes, file.filename)

        # Update job with metadata
        supabase.table("jobs").update({
            "status": "profiling",
            "row_count": metadata["row_count"],
            "column_count": metadata["column_count"],
            "metadata": metadata,
        }).eq("id", job_id).execute()

        # Store column information
        for col_info in metadata["columns"]:
            normalized = _normalize_column_name(col_info["name"])
            supabase.table("columns").insert({
                "job_id": job_id,
                "source_name": col_info["name"],
                "normalized_name": normalized,
                "detected_type": col_info["detected_type"],
                "sample_values": col_info["sample_values"],
                "null_count": col_info["null_count"],
                "total_count": col_info["total_count"],
                "unique_count": col_info["unique_count"],
                "profile_data": col_info,
            }).execute()

        _log_event(
            job_id, "ingestion", "completed",
            f"Successfully parsed {metadata['row_count']} rows, {metadata['column_count']} columns"
        )

        return {
            "job_id": job_id,
            "status": "profiling",
            "metadata": metadata,
        }

    except ValueError as e:
        _update_job_status(job_id, "failed", str(e))
        _log_event(job_id, "ingestion", "failed", f"Ingestion failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        _update_job_status(job_id, "failed", str(e))
        _log_event(job_id, "ingestion", "failed", f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


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


# ── Helper Functions ─────────────────────────────────────────

def _normalize_column_name(name: str) -> str:
    """Normalize a column name for pattern matching.
    'First Name', 'first_name', 'firstName', 'FIRST_NAME' → 'firstname'
    """
    import re
    # Convert camelCase to spaces: firstName → first Name
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Remove all non-alphanumeric characters
    name = re.sub(r'[^a-zA-Z0-9]', '', name)
    # Lowercase
    return name.lower()


def _update_job_status(job_id: str, status: str, error_message: str = None):
    """Update job status in database."""
    update_data = {"status": status}
    if error_message:
        update_data["error_message"] = error_message
    supabase.table("jobs").update(update_data).eq("id", job_id).execute()


def _log_event(job_id: str, agent: str, event_type: str, message: str, metadata: dict = None):
    """Log an agent event."""
    supabase.table("events").insert({
        "job_id": job_id,
        "agent": agent,
        "event_type": event_type,
        "message": message,
        "metadata": metadata or {},
    }).execute()
