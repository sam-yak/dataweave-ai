"""
Schema Builder API Routes — v2 Custom Target Schemas
CRUD endpoints for user-created schemas + field management.

Add to existing routes by importing in routes.py:
    from api.schema_routes import schema_builder_router
    # Then in routes.py or main.py:
    app.include_router(schema_builder_router, prefix="/api")
"""

import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from supabase import create_client

schema_builder_router = APIRouter(tags=["Schema Builder"])

supabase = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", "")
)


# ── Pydantic Models ──────────────────────────────────────────

class FieldDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=100,
                      description="Field name (snake_case recommended)")
    type: str = Field(default="string",
                      description="Data type: string, integer, float, date, boolean, email")
    required: bool = False
    unique: bool = False
    format: Optional[str] = Field(default=None,
                                   description="Format validation: email, phone, url, zipcode, iso8601")
    description: Optional[str] = None
    display_order: int = 0
    default_value: Optional[str] = None


class CreateSchemaRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    fields: list[FieldDefinition] = Field(..., min_length=1, max_length=50)


class UpdateSchemaRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddFieldRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = "string"
    required: bool = False
    unique: bool = False
    format: Optional[str] = None
    description: Optional[str] = None
    display_order: int = 0
    default_value: Optional[str] = None


class UpdateFieldRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    required: Optional[bool] = None
    unique: Optional[bool] = None
    format: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None
    default_value: Optional[str] = None


class ReorderFieldsRequest(BaseModel):
    """List of field IDs in desired order."""
    field_ids: list[str]


# ── Validation Helpers ────────────────────────────────────────

VALID_TYPES = {"string", "integer", "float", "date", "boolean", "email"}
VALID_FORMATS = {"email", "phone", "url", "zipcode", "iso8601", None}

# Format-type compatibility: which formats are valid for which types
FORMAT_TYPE_MAP = {
    "email": {"string", "email"},
    "phone": {"string"},
    "url": {"string"},
    "zipcode": {"string"},
    "iso8601": {"date", "string"},
}


def _validate_field(field: dict):
    """Validate a single field definition."""
    if field.get("type") and field["type"] not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type '{field['type']}'. Must be one of: {', '.join(VALID_TYPES)}"
        )

    fmt = field.get("format")
    if fmt and fmt not in VALID_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{fmt}'. Must be one of: {', '.join(str(f) for f in VALID_FORMATS if f)}"
        )

    if fmt and field.get("type"):
        allowed_types = FORMAT_TYPE_MAP.get(fmt, set())
        if field["type"] not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Format '{fmt}' is not compatible with type '{field['type']}'. "
                       f"Allowed types for {fmt}: {', '.join(allowed_types)}"
            )

    # Sanitize field name: lowercase, replace spaces with underscores
    name = field.get("name", "")
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Field name cannot be empty")

    return True


def _normalize_field_name(name: str) -> str:
    """Normalize field name to snake_case."""
    import re
    # Convert camelCase to snake_case
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
    # Replace spaces and hyphens with underscores
    name = re.sub(r'[\s\-]+', '_', name)
    # Remove non-alphanumeric (except underscore)
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    # Lowercase
    return name.lower().strip('_')


# ── Schema CRUD ──────────────────────────────────────────────

@schema_builder_router.post("/schemas/custom")
async def create_custom_schema(request: CreateSchemaRequest):
    """
    Create a new custom target schema with field definitions.

    This is the main endpoint for the Schema Builder UI.
    Creates the schema + all fields in one request.
    The sync_schema_json trigger automatically builds schema_json.
    """
    # Validate all fields
    for field in request.fields:
        _validate_field(field.model_dump())

    # Normalize field names and check for duplicates
    seen_names = set()
    normalized_fields = []
    for i, field in enumerate(request.fields):
        normalized_name = _normalize_field_name(field.name)
        if not normalized_name:
            raise HTTPException(
                status_code=400,
                detail=f"Field name '{field.name}' normalizes to empty string"
            )
        if normalized_name in seen_names:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate field name after normalization: '{normalized_name}'"
            )
        seen_names.add(normalized_name)
        normalized_fields.append({
            **field.model_dump(),
            "name": normalized_name,
            "display_order": i,
        })

    # Must have at least one field
    if not normalized_fields:
        raise HTTPException(status_code=400, detail="Schema must have at least one field")

    # Build initial schema_json for the insert
    # (the trigger will also sync, but we need it for the initial insert)
    schema_json = {
        "fields": [
            {
                "name": f["name"],
                "type": f["type"],
                "required": f["required"],
                "unique": f["unique"],
                "format": f["format"],
                "description": f["description"],
                "default": f["default_value"],
            }
            for f in normalized_fields
        ]
    }

    try:
        # Create the schema
        schema_result = supabase.table("target_schemas").insert({
            "name": request.name.strip(),
            "description": request.description.strip() if request.description else None,
            "schema_json": json.dumps(schema_json),
            "is_custom": True,
        }).execute()

        schema = schema_result.data[0]
        schema_id = schema["id"]

        # Create all fields
        field_records = []
        for f in normalized_fields:
            field_result = supabase.table("schema_fields").insert({
                "schema_id": schema_id,
                "name": f["name"],
                "type": f["type"],
                "required": f["required"],
                "unique_field": f["unique"],
                "format": f["format"],
                "description": f["description"],
                "display_order": f["display_order"],
                "default_value": f["default_value"],
            }).execute()
            field_records.append(field_result.data[0])

        return {
            "schema": schema,
            "fields": field_records,
            "field_count": len(field_records),
        }

    except Exception as e:
        # Clean up on failure
        if 'schema_id' in dir():
            supabase.table("target_schemas").delete().eq("id", schema_id).execute()
        raise HTTPException(status_code=500, detail=f"Failed to create schema: {str(e)}")


@schema_builder_router.get("/schemas/custom")
async def list_custom_schemas():
    """List all custom schemas created by users."""
    result = (
        supabase.table("target_schemas")
        .select("id, name, description, is_custom, created_at, updated_at")
        .eq("is_custom", True)
        .order("created_at", desc=True)
        .execute()
    )

    # For each schema, fetch field count
    schemas = []
    for s in result.data:
        fields_result = (
            supabase.table("schema_fields")
            .select("id", count="exact")
            .eq("schema_id", s["id"])
            .execute()
        )
        schemas.append({
            **s,
            "field_count": fields_result.count or 0,
        })

    return {"schemas": schemas}


@schema_builder_router.get("/schemas/{schema_id}/fields")
async def get_schema_fields(schema_id: str):
    """Get all field definitions for a schema."""
    # Verify schema exists
    schema_result = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema_result.data:
        raise HTTPException(status_code=404, detail="Schema not found")

    fields_result = (
        supabase.table("schema_fields")
        .select("*")
        .eq("schema_id", schema_id)
        .order("display_order")
        .execute()
    )

    return {
        "schema": schema_result.data[0],
        "fields": fields_result.data,
    }


@schema_builder_router.put("/schemas/{schema_id}")
async def update_schema(schema_id: str, request: UpdateSchemaRequest):
    """Update schema name/description. Only works for custom schemas."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot edit system schemas")

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name.strip()
    if request.description is not None:
        update_data["description"] = request.description.strip()

    if not update_data:
        raise HTTPException(status_code=400, detail="Nothing to update")

    result = supabase.table("target_schemas").update(update_data).eq("id", schema_id).execute()
    return {"schema": result.data[0]}


@schema_builder_router.delete("/schemas/{schema_id}")
async def delete_schema(schema_id: str):
    """Delete a custom schema and all its fields. Cannot delete system schemas."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot delete system schemas")

    # Check if any jobs are using this schema
    jobs = (
        supabase.table("jobs")
        .select("id", count="exact")
        .eq("target_schema_id", schema_id)
        .execute()
    )
    if jobs.count and jobs.count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {jobs.count} job(s) are using this schema. "
                   "Delete those jobs first or archive the schema instead."
        )

    # Delete fields first (CASCADE should handle this, but be explicit)
    supabase.table("schema_fields").delete().eq("schema_id", schema_id).execute()
    supabase.table("patterns").delete().eq("target_schema_id", schema_id).execute()
    supabase.table("target_schemas").delete().eq("id", schema_id).execute()

    return {"deleted": True, "schema_id": schema_id}


# ── Field CRUD ───────────────────────────────────────────────

@schema_builder_router.post("/schemas/{schema_id}/fields")
async def add_field(schema_id: str, request: AddFieldRequest):
    """Add a new field to a custom schema."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot modify system schemas")

    field_data = request.model_dump()
    _validate_field(field_data)

    normalized_name = _normalize_field_name(request.name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Field name normalizes to empty string")

    # Check for existing field with same name
    existing = (
        supabase.table("schema_fields")
        .select("id")
        .eq("schema_id", schema_id)
        .eq("name", normalized_name)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail=f"Field '{normalized_name}' already exists")

    # Get current max display_order
    max_order = (
        supabase.table("schema_fields")
        .select("display_order")
        .eq("schema_id", schema_id)
        .order("display_order", desc=True)
        .limit(1)
        .execute()
    )
    next_order = (max_order.data[0]["display_order"] + 1) if max_order.data else 0

    result = supabase.table("schema_fields").insert({
        "schema_id": schema_id,
        "name": normalized_name,
        "type": request.type,
        "required": request.required,
        "unique_field": request.unique,
        "format": request.format,
        "description": request.description,
        "display_order": next_order,
        "default_value": request.default_value,
    }).execute()

    return {"field": result.data[0]}


@schema_builder_router.put("/schemas/{schema_id}/fields/{field_id}")
async def update_field(schema_id: str, field_id: str, request: UpdateFieldRequest):
    """Update an existing field in a custom schema."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot modify system schemas")

    field = supabase.table("schema_fields").select("*").eq("id", field_id).execute()
    if not field.data:
        raise HTTPException(status_code=404, detail="Field not found")

    update_data = {}
    if request.name is not None:
        normalized = _normalize_field_name(request.name)
        if not normalized:
            raise HTTPException(status_code=400, detail="Field name normalizes to empty string")
        update_data["name"] = normalized
    if request.type is not None:
        update_data["type"] = request.type
    if request.required is not None:
        update_data["required"] = request.required
    if request.unique is not None:
        update_data["unique_field"] = request.unique
    if request.format is not None:
        update_data["format"] = request.format if request.format != "" else None
    if request.description is not None:
        update_data["description"] = request.description
    if request.display_order is not None:
        update_data["display_order"] = request.display_order
    if request.default_value is not None:
        update_data["default_value"] = request.default_value

    if not update_data:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Validate the merged field
    merged = {**field.data[0], **update_data}
    _validate_field({"name": merged.get("name"), "type": merged.get("type"), "format": merged.get("format")})

    result = supabase.table("schema_fields").update(update_data).eq("id", field_id).execute()
    return {"field": result.data[0]}


@schema_builder_router.delete("/schemas/{schema_id}/fields/{field_id}")
async def delete_field(schema_id: str, field_id: str):
    """Remove a field from a custom schema."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot modify system schemas")

    # Ensure at least one field remains
    field_count = (
        supabase.table("schema_fields")
        .select("id", count="exact")
        .eq("schema_id", schema_id)
        .execute()
    )
    if field_count.count and field_count.count <= 1:
        raise HTTPException(status_code=400, detail="Schema must have at least one field")

    supabase.table("schema_fields").delete().eq("id", field_id).execute()
    return {"deleted": True, "field_id": field_id}


@schema_builder_router.put("/schemas/{schema_id}/fields/reorder")
async def reorder_fields(schema_id: str, request: ReorderFieldsRequest):
    """Reorder fields by providing a list of field IDs in desired order."""
    schema = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not schema.data:
        raise HTTPException(status_code=404, detail="Schema not found")
    if not schema.data[0].get("is_custom"):
        raise HTTPException(status_code=403, detail="Cannot modify system schemas")

    for i, field_id in enumerate(request.field_ids):
        supabase.table("schema_fields").update(
            {"display_order": i}
        ).eq("id", field_id).eq("schema_id", schema_id).execute()

    return {"reordered": True, "count": len(request.field_ids)}


# ── Duplicate Schema ─────────────────────────────────────────

@schema_builder_router.post("/schemas/{schema_id}/duplicate")
async def duplicate_schema(schema_id: str):
    """
    Duplicate any schema (system or custom) as a new custom schema.
    Useful for users who want to start from a system schema and modify it.
    """
    source = supabase.table("target_schemas").select("*").eq("id", schema_id).execute()
    if not source.data:
        raise HTTPException(status_code=404, detail="Schema not found")

    source_schema = source.data[0]
    new_name = f"{source_schema['name']} (Copy)"

    # Create new schema
    new_schema = supabase.table("target_schemas").insert({
        "name": new_name,
        "description": source_schema.get("description"),
        "schema_json": source_schema["schema_json"],
        "is_custom": True,
    }).execute()

    new_schema_id = new_schema.data[0]["id"]

    # Copy fields if they exist in schema_fields table
    source_fields = (
        supabase.table("schema_fields")
        .select("*")
        .eq("schema_id", schema_id)
        .order("display_order")
        .execute()
    )

    if source_fields.data:
        # Has normalized fields — copy them
        for f in source_fields.data:
            supabase.table("schema_fields").insert({
                "schema_id": new_schema_id,
                "name": f["name"],
                "type": f["type"],
                "required": f["required"],
                "unique_field": f["unique_field"],
                "format": f["format"],
                "description": f["description"],
                "display_order": f["display_order"],
                "default_value": f["default_value"],
            }).execute()
    else:
        # System schema — parse schema_json and create fields
        schema_json = source_schema["schema_json"]
        if isinstance(schema_json, str):
            schema_json = json.loads(schema_json)

        for i, field in enumerate(schema_json.get("fields", [])):
            supabase.table("schema_fields").insert({
                "schema_id": new_schema_id,
                "name": field["name"],
                "type": field.get("type", "string"),
                "required": field.get("required", False),
                "unique_field": field.get("unique", False),
                "format": field.get("format"),
                "description": field.get("description"),
                "display_order": i,
                "default_value": field.get("default"),
            }).execute()

    return {
        "schema": new_schema.data[0],
        "source_schema_id": schema_id,
        "message": f"Duplicated as '{new_name}'. You can now edit it freely.",
    }
