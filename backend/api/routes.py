"""
API Routes — FastAPI endpoints for DataWeave AI
Updated with mapping endpoint (Pattern Agent + Schema Agent)
"""

import os
import re
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from supabase import create_client
from agents.ingestion import IngestionAgent
from agents.schema import SchemaAgent

router = APIRouter()

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", "")
)

# Initialize agents
ingestion_agent = IngestionAgent()
schema_agent = SchemaAgent()

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


# ── Schema Endpoints ─────────────────────────────────────────

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


# ── Upload + Ingest + Map (Full Pipeline So Far) ────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_schema_id: str = Form(...)
):
    """
    Upload a file for processing.
    Runs: Ingestion Agent → Pattern Agent → Schema Agent (LLM)
    Returns job with mapping proposals ready for human review.
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

    # ── Stage 1: Ingestion Agent ──
    try:
        _log_event(job_id, "orchestrator", "job_created", f"Job created for {file.filename}")
        _log_event(job_id, "ingestion", "started", "Ingestion Agent starting...")
        _update_job_status(job_id, "ingesting")

        df, metadata = ingestion_agent.process(file_bytes, file.filename)

        # Update job with metadata
        supabase.table("jobs").update({
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
            f"Parsed {metadata['row_count']} rows, {metadata['column_count']} columns"
        )

    except ValueError as e:
        _update_job_status(job_id, "failed", str(e))
        _log_event(job_id, "ingestion", "failed", f"Ingestion failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _update_job_status(job_id, "failed", str(e))
        _log_event(job_id, "ingestion", "failed", f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    # ── Stage 2: Schema Agent (Pattern lookup + LLM mapping) ──
    try:
        _log_event(job_id, "schema", "started", "Schema Agent starting — checking patterns and calling AI...")
        _update_job_status(job_id, "mapping")

        mappings = schema_agent.process(job_id, target_schema_id)

        _update_job_status(job_id, "awaiting_review")

        # Summarize results
        pattern_count = sum(1 for m in mappings if m["agent_source"] == "pattern")
        llm_count = sum(1 for m in mappings if m["agent_source"] == "schema")
        mapped_count = sum(1 for m in mappings if m["target_field"] is not None)
        high_confidence = sum(1 for m in mappings if m["confidence"] >= 85)
        medium_confidence = sum(1 for m in mappings if 50 <= m["confidence"] < 85)
        low_confidence = sum(1 for m in mappings if 0 < m["confidence"] < 50)

        return {
            "job_id": job_id,
            "status": "awaiting_review",
            "metadata": metadata,
            "mapping_summary": {
                "total_columns": len(mappings),
                "mapped": mapped_count,
                "unmapped": len(mappings) - mapped_count,
                "by_agent": {
                    "pattern_agent": pattern_count,
                    "schema_agent_llm": llm_count,
                },
                "by_confidence": {
                    "high (85+)": high_confidence,
                    "medium (50-84)": medium_confidence,
                    "low (<50)": low_confidence,
                },
            },
            "mappings": [
                {
                    "source_name": m["source_name"],
                    "target_field": m["target_field"],
                    "confidence": m["confidence"],
                    "agent_source": m["agent_source"],
                    "reasoning": m.get("reasoning", ""),
                    "transform_type": m.get("transform_type"),
                }
                for m in mappings
            ],
        }

    except Exception as e:
        _update_job_status(job_id, "failed", str(e))
        _log_event(job_id, "schema", "failed", f"Mapping failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Mapping failed: {str(e)}")


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


# ── Mapping Review Endpoints ─────────────────────────────────

@router.post("/jobs/{job_id}/mappings/{mapping_id}/approve")
async def approve_mapping(job_id: str, mapping_id: str):
    """Approve a proposed mapping. Teaches the Pattern Agent."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Update mapping status
    supabase.table("mappings").update({
        "status": "approved"
    }).eq("id", mapping_id).execute()

    # Teach the Pattern Agent
    job = _get_job(job_id)
    if job and mapping["target_field"]:
        schema_agent.pattern_agent.record_approval(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            target_field=mapping["target_field"],
            transform_type=mapping.get("transform_type"),
        )

    _log_event(
        job_id, "hitl", "mapping_approved",
        f"Approved: '{mapping['source_name']}' → '{mapping['target_field']}'"
    )

    return {"status": "approved", "mapping_id": mapping_id}


@router.post("/jobs/{job_id}/mappings/{mapping_id}/reject")
async def reject_mapping(job_id: str, mapping_id: str):
    """Reject a proposed mapping. Teaches the Pattern Agent."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    supabase.table("mappings").update({
        "status": "rejected"
    }).eq("id", mapping_id).execute()

    # Teach the Pattern Agent
    job = _get_job(job_id)
    if job and mapping["target_field"]:
        schema_agent.pattern_agent.record_rejection(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            target_field=mapping["target_field"],
        )

    _log_event(
        job_id, "hitl", "mapping_rejected",
        f"Rejected: '{mapping['source_name']}' → '{mapping['target_field']}'"
    )

    return {"status": "rejected", "mapping_id": mapping_id}


@router.post("/jobs/{job_id}/mappings/{mapping_id}/correct")
async def correct_mapping(job_id: str, mapping_id: str, correct_target: str = Form(...)):
    """Correct a mapping to a different target field. Most valuable learning signal."""
    mapping = _get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_target = mapping["target_field"]

    # Update mapping with correction
    supabase.table("mappings").update({
        "target_field": correct_target,
        "status": "corrected",
        "agent_source": "manual",
    }).eq("id", mapping_id).execute()

    # Teach the Pattern Agent (this is the gold — corrections are the best signal)
    job = _get_job(job_id)
    if job:
        schema_agent.pattern_agent.record_correction(
            target_schema_id=job["target_schema_id"],
            source_name=mapping["source_name"],
            wrong_target=old_target,
            correct_target=correct_target,
        )

    _log_event(
        job_id, "hitl", "mapping_corrected",
        f"Corrected: '{mapping['source_name']}' → '{old_target}' changed to '{correct_target}'"
    )

    return {"status": "corrected", "mapping_id": mapping_id, "new_target": correct_target}


# ── Pattern Stats Endpoint ───────────────────────────────────

@router.get("/stats/patterns")
async def get_pattern_stats():
    """Get pattern learning statistics — great for LinkedIn posts."""
    stats = schema_agent.pattern_agent.get_stats()
    llm_stats = schema_agent.llm_router.get_stats()
    return {
        "patterns": stats,
        "llm": llm_stats,
    }


# ── Helper Functions ─────────────────────────────────────────

def _normalize_column_name(name: str) -> str:
    """Normalize a column name for pattern matching."""
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    name = re.sub(r'[^a-zA-Z0-9]', '', name)
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


def _get_mapping(mapping_id: str) -> dict:
    """Fetch a mapping by ID."""
    result = supabase.table("mappings").select("*").eq("id", mapping_id).execute()
    return result.data[0] if result.data else None


def _get_job(job_id: str) -> dict:
    """Fetch a job by ID."""
    result = supabase.table("jobs").select("*").eq("id", job_id).execute()
    return result.data[0] if result.data else None
