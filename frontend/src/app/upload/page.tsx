"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useTheme, ThemeToggle } from "@/components/ThemeProvider";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface Schema {
  id: string;
  name: string;
  description: string;
  is_custom?: boolean;
}

export default function UploadPage() {
  const router = useRouter();
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [schemas, setSchemas] = useState<Schema[]>([]);
  const [customSchemas, setCustomSchemas] = useState<Schema[]>([]);
  const [selectedSchema, setSelectedSchema] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [schemaTab, setSchemaTab] = useState<"system" | "custom">("system");

  // Fetch available schemas on mount
  useEffect(() => {
    fetch(`${API_URL}/api/schemas`)
      .then((res) => res.json())
      .then((data) => {
        const all = data.schemas || [];
        const system = all.filter((s: Schema) => !s.is_custom);
        const custom = all.filter((s: Schema) => s.is_custom);
        setSchemas(system);
        setCustomSchemas(custom);
        if (system.length > 0) {
          setSelectedSchema(system[0].id);
        }
      })
      .catch(() => setError("Could not connect to the API. Please try again later."));

    fetch(`${API_URL}/api/schemas/custom`)
      .then((res) => res.json())
      .then((data) => {
        if (data.schemas?.length > 0) {
          setCustomSchemas(data.schemas);
        }
      })
      .catch(() => {});
  }, []);

  // Drag and drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setError("");
    const dropped = e.dataTransfer.files[0];
    if (dropped) validateAndSetFile(dropped);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError("");
    const selected = e.target.files?.[0];
    if (selected) validateAndSetFile(selected);
  };

  const validateAndSetFile = (f: File) => {
    const validTypes = [".csv", ".xlsx", ".xls", ".json", ".tsv"];
    const ext = f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
    if (!validTypes.includes(ext)) {
      setError("Unsupported file type. Please upload CSV, Excel, JSON, or TSV.");
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError("File exceeds 10MB limit.");
      return;
    }
    setFile(f);
  };

  const handleUpload = async () => {
    if (!file || !selectedSchema) return;

    setUploading(true);
    setError("");
    setProgress("Uploading file...");

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("target_schema_id", selectedSchema);

      const res = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Upload failed (${res.status})`);
      }

      const data = await res.json();

      if (data.status === "processing") {
        router.push(`/processing/${data.job_id}`);
      } else {
        sessionStorage.setItem("pipeline_result", JSON.stringify(data));
        router.push(`/review/${data.job_id}`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Upload failed. Please try again.";
      setError(message);
      setUploading(false);
      setProgress("");
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const activeSchemas = schemaTab === "system" ? schemas : customSchemas;

  return (
    <div className="min-h-screen" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-20 py-5" style={{ borderBottom: "1px solid var(--dw-border)" }}>
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ color: "var(--dw-text-primary)" }}>
            data<span className="text-[#E94560]">weave</span>
          </span>
        </a>
        <ThemeToggle />
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-10">
          <h1 className="text-3xl font-bold mb-2">Upload your data</h1>
          <p style={{ color: "var(--dw-text-secondary)" }}>
            Drop a file and select your target schema. Our AI agents will handle the rest.
          </p>
        </div>

        {/* Schema selector */}
        <div className="mb-8">
          <label className="block text-sm font-medium mb-2" style={{ color: "var(--dw-text-secondary)" }}>
            Target Schema
          </label>

          {/* Schema type tabs */}
          <div
            className="flex items-center gap-1 mb-3 p-1 rounded-lg w-fit"
            style={{ background: "var(--dw-bg-card)", border: "1px solid var(--dw-border)" }}
          >
            <button
              onClick={() => setSchemaTab("system")}
              className="px-4 py-1.5 rounded-md text-xs font-medium transition-all"
              style={{
                background: schemaTab === "system" ? (isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)") : "transparent",
                color: schemaTab === "system" ? "var(--dw-text-primary)" : "var(--dw-text-tertiary)",
              }}
            >
              Built-in
            </button>
            <button
              onClick={() => setSchemaTab("custom")}
              className="px-4 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5"
              style={{
                background: schemaTab === "custom" ? (isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)") : "transparent",
                color: schemaTab === "custom" ? "var(--dw-text-primary)" : "var(--dw-text-tertiary)",
              }}
            >
              My Schemas
              {customSchemas.length > 0 && (
                <span className="text-[10px] bg-[#E94560]/20 text-[#E94560] px-1.5 py-0.5 rounded-full">
                  {customSchemas.length}
                </span>
              )}
            </button>
          </div>

          {/* Schema cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {activeSchemas.map((schema) => (
              <button
                key={schema.id}
                onClick={() => setSelectedSchema(schema.id)}
                className="p-4 rounded-xl text-left transition-all duration-200"
                style={{
                  border: selectedSchema === schema.id
                    ? "1px solid #E94560"
                    : "1px solid var(--dw-border)",
                  background: selectedSchema === schema.id
                    ? "rgba(233,69,96,0.1)"
                    : "var(--dw-bg-card)",
                }}
                onMouseEnter={(e) => {
                  if (selectedSchema !== schema.id) e.currentTarget.style.borderColor = "var(--dw-border-strong)";
                }}
                onMouseLeave={(e) => {
                  if (selectedSchema !== schema.id) e.currentTarget.style.borderColor = "var(--dw-border)";
                }}
              >
                <div className="text-sm font-semibold mb-1" style={{ color: "var(--dw-text-primary)" }}>{schema.name}</div>
                <div className="text-xs line-clamp-2" style={{ color: "var(--dw-text-tertiary)" }}>{schema.description}</div>
              </button>
            ))}

            {/* "Create New" card (only in My Schemas tab) */}
            {schemaTab === "custom" && (
              <a
                href="/schemas/new"
                className="p-4 rounded-xl border-2 border-dashed text-center transition-all duration-200 flex flex-col items-center justify-center gap-1"
                style={{
                  borderColor: "var(--dw-border)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "rgba(233,69,96,0.3)";
                  e.currentTarget.style.background = "rgba(233,69,96,0.05)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--dw-border)";
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <div className="text-xl" style={{ color: "var(--dw-text-muted)" }}>+</div>
                <div className="text-xs" style={{ color: "var(--dw-text-tertiary)" }}>Create New</div>
              </a>
            )}
          </div>

          {/* Empty state for custom schemas */}
          {schemaTab === "custom" && customSchemas.length === 0 && (
            <div className="mt-3 text-center py-4">
              <p className="text-xs mb-2" style={{ color: "var(--dw-text-muted)" }}>No custom schemas yet.</p>
              <a
                href="/schemas/new"
                className="text-xs text-[#E94560] hover:text-[#FF6B6B] transition-colors"
              >
                Create your first schema →
              </a>
            </div>
          )}

          {schemaTab === "system" && schemas.length === 0 && !error && (
            <div className="text-sm mt-2" style={{ color: "var(--dw-text-tertiary)" }}>Loading schemas...</div>
          )}
        </div>

        {/* Drop zone */}
        <div className="mb-8">
          <label className="block text-sm font-medium mb-2" style={{ color: "var(--dw-text-secondary)" }}>
            Data File
          </label>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className="relative border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200"
            style={{
              borderColor: dragging
                ? "#E94560"
                : file
                ? "rgba(74,222,128,0.3)"
                : "var(--dw-border-input)",
              background: dragging
                ? "rgba(233,69,96,0.05)"
                : file
                ? "rgba(74,222,128,0.05)"
                : isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.01)",
            }}
          >
            {file ? (
              <div>
                <div className="text-3xl mb-3">📄</div>
                <p className="font-medium" style={{ color: "var(--dw-text-primary)" }}>{file.name}</p>
                <p className="text-sm mt-1" style={{ color: "var(--dw-text-tertiary)" }}>{formatSize(file.size)}</p>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                  className="mt-3 text-xs text-[#E94560] hover:text-[#FF6B6B] transition-colors"
                >
                  Remove file
                </button>
              </div>
            ) : (
              <div>
                <div className="text-4xl mb-3 opacity-40">↑</div>
                <p className="mb-1" style={{ color: "var(--dw-text-secondary)" }}>
                  Drag and drop your file here
                </p>
                <p className="text-sm mb-4" style={{ color: "var(--dw-text-muted)" }}>
                  CSV, Excel, JSON, or TSV — up to 10MB
                </p>
                <label
                  className="inline-block px-5 py-2 rounded-lg text-sm cursor-pointer transition-all"
                  style={{
                    background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)",
                    border: `1px solid ${isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)"}`,
                    color: "var(--dw-text-secondary)",
                  }}
                >
                  Browse files
                  <input
                    type="file"
                    accept=".csv,.xlsx,.xls,.json,.tsv"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </label>
              </div>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 rounded-xl" style={{ background: "var(--dw-error-light)", border: "1px solid var(--dw-error-border)" }}>
            <p className="text-sm" style={{ color: "var(--dw-error)" }}>{error}</p>
          </div>
        )}

        {/* Upload button */}
        <button
          onClick={handleUpload}
          disabled={!file || !selectedSchema || uploading}
          className="w-full py-3.5 bg-[#E94560] hover:bg-[#D63B55] disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-white font-semibold transition-all duration-200"
        >
          {uploading ? (
            <span className="flex items-center justify-center gap-3">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {progress}
            </span>
          ) : (
            "Upload & Map Columns"
          )}
        </button>

        {/* Pipeline info */}
        {uploading && (
          <div
            className="mt-8 rounded-xl p-5"
            style={{
              background: isDark ? "#12121A" : "#1E1E2E",
              border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.12)"}`,
            }}
          >
            <div className="space-y-3 font-mono text-sm">
              <div className="flex items-center gap-2 text-white/40">
                <span className="text-[#4ADE80]">✓</span> Ingestion Agent: parsing file...
              </div>
              <div className="flex items-center gap-2 text-white/40">
                <svg className="animate-spin h-3.5 w-3.5 text-[#FBBF24]" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Pattern Agent + Schema Agent: mapping columns...
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
