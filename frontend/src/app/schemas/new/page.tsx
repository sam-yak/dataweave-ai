"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

// ── Types ───────────────────────────────────────────────────

interface FieldDef {
  id: string; // client-side temp ID
  name: string;
  type: string;
  required: boolean;
  unique: boolean;
  format: string;
  description: string;
  default_value: string;
}

const FIELD_TYPES = [
  { value: "string", label: "String", icon: "Aa" },
  { value: "integer", label: "Integer", icon: "#" },
  { value: "float", label: "Float", icon: "#." },
  { value: "date", label: "Date", icon: "📅" },
  { value: "boolean", label: "Boolean", icon: "⊘" },
  { value: "email", label: "Email", icon: "@" },
];

const FORMAT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  string: [
    { value: "", label: "None" },
    { value: "email", label: "Email" },
    { value: "phone", label: "Phone" },
    { value: "url", label: "URL" },
    { value: "zipcode", label: "Zip Code" },
  ],
  email: [
    { value: "", label: "None" },
    { value: "email", label: "Email" },
  ],
  date: [
    { value: "", label: "None" },
    { value: "iso8601", label: "ISO 8601" },
  ],
  integer: [],
  float: [],
  boolean: [],
};

// ── Helpers ─────────────────────────────────────────────────

let fieldCounter = 0;
function makeFieldId(): string {
  return `field_${Date.now()}_${++fieldCounter}`;
}

function toSnakeCase(str: string): string {
  return str
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .replace(/[\s\-]+/g, "_")
    .replace(/[^a-zA-Z0-9_]/g, "")
    .toLowerCase()
    .replace(/^_+|_+$/g, "");
}

function createEmptyField(): FieldDef {
  return {
    id: makeFieldId(),
    name: "",
    type: "string",
    required: false,
    unique: false,
    format: "",
    description: "",
    default_value: "",
  };
}

// ── Common field presets ────────────────────────────────────

const PRESETS: { label: string; fields: Omit<FieldDef, "id">[] }[] = [
  {
    label: "Contact Info",
    fields: [
      { name: "first_name", type: "string", required: true, unique: false, format: "", description: "Contact first name", default_value: "" },
      { name: "last_name", type: "string", required: true, unique: false, format: "", description: "Contact last name", default_value: "" },
      { name: "email", type: "string", required: true, unique: true, format: "email", description: "Email address", default_value: "" },
      { name: "phone", type: "string", required: false, unique: false, format: "phone", description: "Phone number", default_value: "" },
    ],
  },
  {
    label: "Company Info",
    fields: [
      { name: "company", type: "string", required: false, unique: false, format: "", description: "Company name", default_value: "" },
      { name: "job_title", type: "string", required: false, unique: false, format: "", description: "Job title or role", default_value: "" },
      { name: "website", type: "string", required: false, unique: false, format: "url", description: "Company website", default_value: "" },
    ],
  },
  {
    label: "Address",
    fields: [
      { name: "address", type: "string", required: false, unique: false, format: "", description: "Street address", default_value: "" },
      { name: "city", type: "string", required: false, unique: false, format: "", description: "City", default_value: "" },
      { name: "state", type: "string", required: false, unique: false, format: "", description: "State or province", default_value: "" },
      { name: "zip_code", type: "string", required: false, unique: false, format: "zipcode", description: "Postal / ZIP code", default_value: "" },
      { name: "country", type: "string", required: false, unique: false, format: "", description: "Country", default_value: "" },
    ],
  },
  {
    label: "Metadata",
    fields: [
      { name: "source", type: "string", required: false, unique: false, format: "", description: "Lead source or channel", default_value: "" },
      { name: "notes", type: "string", required: false, unique: false, format: "", description: "Free-text notes", default_value: "" },
      { name: "created_at", type: "date", required: false, unique: false, format: "iso8601", description: "Record creation date", default_value: "" },
    ],
  },
];

// ── Component ───────────────────────────────────────────────

export default function SchemaBuilderPage() {
  const router = useRouter();

  const [schemaName, setSchemaName] = useState("");
  const [schemaDescription, setSchemaDescription] = useState("");
  const [fields, setFields] = useState<FieldDef[]>([createEmptyField()]);
  const [expandedField, setExpandedField] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // ── Field CRUD ──

  const addField = useCallback(() => {
    const newField = createEmptyField();
    setFields((prev) => [...prev, newField]);
    setExpandedField(newField.id);
  }, []);

  const removeField = useCallback(
    (fieldId: string) => {
      if (fields.length <= 1) return;
      setFields((prev) => prev.filter((f) => f.id !== fieldId));
      if (expandedField === fieldId) setExpandedField(null);
    },
    [fields.length, expandedField]
  );

  const updateField = useCallback(
    (fieldId: string, updates: Partial<FieldDef>) => {
      setFields((prev) =>
        prev.map((f) => {
          if (f.id !== fieldId) return f;
          const updated = { ...f, ...updates };
          // Auto-normalize name to snake_case as user types
          if (updates.name !== undefined) {
            updated.name = updates.name; // Keep raw input for editing
          }
          // Clear format if type doesn't support it
          if (updates.type !== undefined) {
            const formats = FORMAT_OPTIONS[updates.type] || [];
            if (formats.length === 0 || !formats.find((fo) => fo.value === f.format)) {
              updated.format = "";
            }
          }
          return updated;
        })
      );
    },
    []
  );

  const addPreset = useCallback(
    (presetFields: Omit<FieldDef, "id">[]) => {
      const existingNames = new Set(fields.map((f) => toSnakeCase(f.name)));
      const newFields = presetFields
        .filter((pf) => !existingNames.has(pf.name))
        .map((pf) => ({ ...pf, id: makeFieldId() }));

      if (newFields.length === 0) {
        setError("All fields from this preset already exist in your schema.");
        setTimeout(() => setError(""), 3000);
        return;
      }

      // If the only field is an empty one, replace it
      if (fields.length === 1 && !fields[0].name.trim()) {
        setFields(newFields);
      } else {
        setFields((prev) => [...prev, ...newFields]);
      }
    },
    [fields]
  );

  // ── Drag & Drop Reorder ──

  const handleDragStart = (index: number) => {
    setDragIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    setDragOverIndex(index);
  };

  const handleDrop = (index: number) => {
    if (dragIndex === null || dragIndex === index) {
      setDragIndex(null);
      setDragOverIndex(null);
      return;
    }
    setFields((prev) => {
      const updated = [...prev];
      const [moved] = updated.splice(dragIndex, 1);
      updated.splice(index, 0, moved);
      return updated;
    });
    setDragIndex(null);
    setDragOverIndex(null);
  };

  // ── Save ──

  const handleSave = async () => {
    setError("");
    setSuccess("");

    // Validation
    if (!schemaName.trim()) {
      setError("Schema name is required.");
      return;
    }

    const validFields = fields.filter((f) => f.name.trim());
    if (validFields.length === 0) {
      setError("Add at least one field with a name.");
      return;
    }

    // Check for duplicate names
    const names = validFields.map((f) => toSnakeCase(f.name));
    const dupes = names.filter((n, i) => names.indexOf(n) !== i);
    if (dupes.length > 0) {
      setError(`Duplicate field name: "${dupes[0]}". Each field must have a unique name.`);
      return;
    }

    setSaving(true);

    try {
      const payload = {
        name: schemaName.trim(),
        description: schemaDescription.trim() || null,
        fields: validFields.map((f, i) => ({
          name: toSnakeCase(f.name) || f.name.trim(),
          type: f.type,
          required: f.required,
          unique: f.unique,
          format: f.format || null,
          description: f.description.trim() || null,
          display_order: i,
          default_value: f.default_value.trim() || null,
        })),
      };

      const res = await fetch(`${API_URL}/api/schemas/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Failed to create schema (${res.status})`);
      }

      const data = await res.json();
      setSuccess(`Schema "${data.schema.name}" created with ${data.field_count} fields!`);

      // Redirect to upload after brief delay
      setTimeout(() => router.push("/upload"), 1500);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to save schema.";
      setError(message);
    }

    setSaving(false);
  };

  // ── Render ──

  const typeIcon = (type: string) =>
    FIELD_TYPES.find((t) => t.value === type)?.icon || "?";

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-white">
      {/* Grain */}
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-[0.03]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
      <div className="fixed top-0 right-1/4 w-[400px] h-[400px] bg-[#0F3460]/8 rounded-full blur-[150px] pointer-events-none" />

      {/* Nav */}
      <nav className="relative z-40 flex items-center justify-between px-6 md:px-12 lg:px-20 py-5 border-b border-white/[0.05]">
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </div>
          <span className="text-lg font-bold tracking-tight">
            data<span className="text-[#E94560]">weave</span>
          </span>
        </a>
        <a
          href="/upload"
          className="text-sm text-white/40 hover:text-white/60 transition-colors"
        >
          ← Back to Upload
        </a>
      </nav>

      <div className="relative z-10 max-w-3xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/[0.05] border border-white/[0.08] rounded-full text-xs text-white/50 mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-[#E94560]" />
            v2 Feature
          </div>
          <h1 className="text-3xl font-bold mb-2">Schema Builder</h1>
          <p className="text-white/40">
            Define the target format for your data. Your uploaded files will be mapped, transformed, and validated against this schema.
          </p>
        </div>

        {/* Schema Name + Description */}
        <div className="mb-8 space-y-4">
          <div>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Schema Name <span className="text-[#E94560]">*</span>
            </label>
            <input
              type="text"
              value={schemaName}
              onChange={(e) => setSchemaName(e.target.value)}
              placeholder="e.g. My CRM Contacts, E-commerce Orders, Patient Records"
              className="w-full px-4 py-3 bg-white/[0.04] border border-white/[0.08] rounded-xl text-white placeholder:text-white/20 focus:outline-none focus:border-[#E94560]/50 transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Description <span className="text-white/25">(optional)</span>
            </label>
            <input
              type="text"
              value={schemaDescription}
              onChange={(e) => setSchemaDescription(e.target.value)}
              placeholder="Brief description of what this schema is for"
              className="w-full px-4 py-3 bg-white/[0.04] border border-white/[0.08] rounded-xl text-white placeholder:text-white/20 focus:outline-none focus:border-[#E94560]/50 transition-colors"
            />
          </div>
        </div>

        {/* Quick-add presets */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-white/60 mb-3">
            Quick Add Field Groups
          </label>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => addPreset(preset.fields)}
                className="px-3.5 py-2 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] hover:border-white/[0.15] rounded-lg text-xs text-white/60 hover:text-white/80 transition-all"
              >
                + {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Fields List */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm font-medium text-white/60">
              Fields <span className="text-white/25">({fields.filter((f) => f.name.trim()).length})</span>
            </label>
            <span className="text-xs text-white/25">Drag to reorder</span>
          </div>

          <div className="space-y-2">
            {fields.map((field, index) => {
              const isExpanded = expandedField === field.id;
              const normalizedName = toSnakeCase(field.name);
              const isDragOver = dragOverIndex === index && dragIndex !== index;

              return (
                <div
                  key={field.id}
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDrop={() => handleDrop(index)}
                  onDragEnd={() => {
                    setDragIndex(null);
                    setDragOverIndex(null);
                  }}
                  className={`border rounded-xl transition-all duration-200 ${
                    isDragOver
                      ? "border-[#E94560]/50 bg-[#E94560]/5"
                      : isExpanded
                      ? "border-white/[0.12] bg-white/[0.04]"
                      : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1]"
                  } ${dragIndex === index ? "opacity-50" : ""}`}
                >
                  {/* Collapsed row */}
                  <div
                    className="flex items-center gap-3 px-4 py-3 cursor-pointer"
                    onClick={() => setExpandedField(isExpanded ? null : field.id)}
                  >
                    {/* Drag handle */}
                    <div className="text-white/15 hover:text-white/30 cursor-grab active:cursor-grabbing shrink-0">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <circle cx="9" cy="6" r="1.5" />
                        <circle cx="15" cy="6" r="1.5" />
                        <circle cx="9" cy="12" r="1.5" />
                        <circle cx="15" cy="12" r="1.5" />
                        <circle cx="9" cy="18" r="1.5" />
                        <circle cx="15" cy="18" r="1.5" />
                      </svg>
                    </div>

                    {/* Type badge */}
                    <div className="w-8 h-8 rounded-lg bg-white/[0.06] flex items-center justify-center text-xs font-mono text-white/50 shrink-0">
                      {typeIcon(field.type)}
                    </div>

                    {/* Name */}
                    <div className="flex-1 min-w-0">
                      {field.name.trim() ? (
                        <span className="text-sm font-mono text-white">
                          {normalizedName || field.name}
                        </span>
                      ) : (
                        <span className="text-sm text-white/20 italic">unnamed field</span>
                      )}
                    </div>

                    {/* Tags */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {field.required && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#E94560]/10 text-[#E94560]">
                          REQ
                        </span>
                      )}
                      {field.unique && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#FBBF24]/10 text-[#FBBF24]">
                          UNQ
                        </span>
                      )}
                      {field.format && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#0F3460]/30 text-[#60A5FA]">
                          {field.format}
                        </span>
                      )}
                    </div>

                    {/* Expand arrow */}
                    <div
                      className={`text-white/20 transition-transform duration-200 shrink-0 ${
                        isExpanded ? "rotate-180" : ""
                      }`}
                    >
                      ▾
                    </div>

                    {/* Delete */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeField(field.id);
                      }}
                      disabled={fields.length <= 1}
                      className="text-white/15 hover:text-[#E94560] transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
                      title="Remove field"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 6L6 18M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  {/* Expanded editor */}
                  {isExpanded && (
                    <div className="px-4 pb-4 pt-1 border-t border-white/[0.05] space-y-4">
                      {/* Row 1: Name + Type */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-white/40 mb-1.5">
                            Field Name <span className="text-[#E94560]">*</span>
                          </label>
                          <input
                            type="text"
                            value={field.name}
                            onChange={(e) => updateField(field.id, { name: e.target.value })}
                            placeholder="e.g. first_name, email, created_at"
                            className="w-full px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-sm text-white font-mono placeholder:text-white/15 focus:outline-none focus:border-[#E94560]/40"
                          />
                          {field.name.trim() && normalizedName !== field.name.trim() && (
                            <p className="text-[10px] text-white/25 mt-1 font-mono">
                              → {normalizedName}
                            </p>
                          )}
                        </div>
                        <div>
                          <label className="block text-xs text-white/40 mb-1.5">Type</label>
                          <select
                            value={field.type}
                            onChange={(e) => updateField(field.id, { type: e.target.value })}
                            className="w-full px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-sm text-white focus:outline-none focus:border-[#E94560]/40 appearance-none cursor-pointer"
                            style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%23666\' stroke-width=\'2\'%3E%3Cpath d=\'M6 9l6 6 6-6\'/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center' }}
                          >
                            {FIELD_TYPES.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.icon} {t.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Row 2: Flags + Format */}
                      <div className="flex items-center gap-6">
                        <label className="flex items-center gap-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={field.required}
                            onChange={(e) => updateField(field.id, { required: e.target.checked })}
                            className="w-4 h-4 rounded border-white/20 bg-white/5 accent-[#E94560]"
                          />
                          <span className="text-xs text-white/50 group-hover:text-white/70">Required</span>
                        </label>

                        <label className="flex items-center gap-2 cursor-pointer group">
                          <input
                            type="checkbox"
                            checked={field.unique}
                            onChange={(e) => updateField(field.id, { unique: e.target.checked })}
                            className="w-4 h-4 rounded border-white/20 bg-white/5 accent-[#FBBF24]"
                          />
                          <span className="text-xs text-white/50 group-hover:text-white/70">Unique</span>
                        </label>

                        {(FORMAT_OPTIONS[field.type] || []).length > 0 && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-white/40">Format:</span>
                            <select
                              value={field.format}
                              onChange={(e) => updateField(field.id, { format: e.target.value })}
                              className="px-2 py-1 bg-white/[0.04] border border-white/[0.08] rounded-md text-xs text-white focus:outline-none focus:border-[#E94560]/40 appearance-none cursor-pointer"
                              style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'10\' height=\'10\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%23666\' stroke-width=\'2\'%3E%3Cpath d=\'M6 9l6 6 6-6\'/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', paddingRight: '24px' }}
                            >
                              {(FORMAT_OPTIONS[field.type] || []).map((fo) => (
                                <option key={fo.value} value={fo.value}>
                                  {fo.label}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}
                      </div>

                      {/* Row 3: Description */}
                      <div>
                        <label className="block text-xs text-white/40 mb-1.5">
                          Description <span className="text-white/20">(helps AI map columns)</span>
                        </label>
                        <input
                          type="text"
                          value={field.description}
                          onChange={(e) => updateField(field.id, { description: e.target.value })}
                          placeholder="e.g. Customer's primary email address"
                          className="w-full px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-xs text-white/70 placeholder:text-white/15 focus:outline-none focus:border-[#E94560]/40"
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Add field button */}
        <button
          onClick={addField}
          className="w-full py-3 border-2 border-dashed border-white/[0.08] hover:border-white/[0.15] rounded-xl text-sm text-white/30 hover:text-white/50 transition-all mb-10"
        >
          + Add Field
        </button>

        {/* Preview */}
        {fields.some((f) => f.name.trim()) && (
          <div className="mb-10">
            <label className="block text-sm font-medium text-white/60 mb-3">
              Schema Preview
            </label>
            <div className="bg-[#12121A] border border-white/[0.06] rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/[0.06]">
                <div className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
                <span className="ml-2 text-xs text-white/25 font-mono">
                  {schemaName || "untitled"}.schema
                </span>
              </div>
              <div className="p-4 font-mono text-xs space-y-1">
                <p className="text-white/30">{"{"}</p>
                <p className="text-white/30 pl-3">
                  {'"fields"'}: [
                </p>
                {fields
                  .filter((f) => f.name.trim())
                  .map((f, i, arr) => {
                    const n = toSnakeCase(f.name);
                    const parts = [`"name": "${n}"`, `"type": "${f.type}"`];
                    if (f.required) parts.push(`"required": true`);
                    if (f.unique) parts.push(`"unique": true`);
                    if (f.format) parts.push(`"format": "${f.format}"`);
                    return (
                      <p key={f.id} className="pl-6 text-white/50">
                        {"{ "}
                        <span className="text-[#4ADE80]">{parts.join(", ")}</span>
                        {" }"}
                        {i < arr.length - 1 ? "," : ""}
                      </p>
                    );
                  })}
                <p className="text-white/30 pl-3">]</p>
                <p className="text-white/30">{"}"}</p>
              </div>
            </div>
          </div>
        )}

        {/* Error / Success */}
        {error && (
          <div className="mb-6 p-4 bg-[#E94560]/10 border border-[#E94560]/20 rounded-xl">
            <p className="text-sm text-[#E94560]">{error}</p>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-[#4ADE80]/10 border border-[#4ADE80]/20 rounded-xl">
            <p className="text-sm text-[#4ADE80]">{success}</p>
          </div>
        )}

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving || !schemaName.trim() || !fields.some((f) => f.name.trim())}
          className="w-full py-3.5 bg-[#E94560] hover:bg-[#D63B55] disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-white font-semibold transition-all duration-200 hover:shadow-[0_0_40px_rgba(233,69,96,0.2)]"
        >
          {saving ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Creating Schema...
            </span>
          ) : (
            "Create Schema & Go to Upload →"
          )}
        </button>
      </div>
    </div>
  );
}
