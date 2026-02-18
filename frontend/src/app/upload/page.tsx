"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface Schema {
  id: string;
  name: string;
  description: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [schemas, setSchemas] = useState<Schema[]>([]);
  const [selectedSchema, setSelectedSchema] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  // Fetch available schemas on mount
  useEffect(() => {
    fetch(`${API_URL}/api/schemas`)
      .then((res) => res.json())
      .then((data) => {
        setSchemas(data.schemas || []);
        if (data.schemas?.length > 0) {
          setSelectedSchema(data.schemas[0].id);
        }
      })
      .catch(() => setError("Could not connect to the API. Please try again later."));
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

      setProgress("Running AI pipeline...");

      const res = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Upload failed (${res.status})`);
      }

      const data = await res.json();

      // Store the result in sessionStorage for the review page
      sessionStorage.setItem("pipeline_result", JSON.stringify(data));
      router.push(`/review/${data.job_id}`);
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

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-20 py-5 border-b border-white/[0.05]">
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
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-10">
          <h1 className="text-3xl font-bold mb-2">Upload your data</h1>
          <p className="text-white/40">
            Drop a file and select your target schema. Our AI agents will handle the rest.
          </p>
        </div>

        {/* Schema selector */}
        <div className="mb-8">
          <label className="block text-sm font-medium text-white/60 mb-2">
            Target Schema
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {schemas.map((schema) => (
              <button
                key={schema.id}
                onClick={() => setSelectedSchema(schema.id)}
                className={`p-4 rounded-xl border text-left transition-all duration-200 ${
                  selectedSchema === schema.id
                    ? "border-[#E94560] bg-[#E94560]/10"
                    : "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15]"
                }`}
              >
                <div className="text-sm font-semibold text-white mb-1">{schema.name}</div>
                <div className="text-xs text-white/35 line-clamp-2">{schema.description}</div>
              </button>
            ))}
          </div>
          {schemas.length === 0 && !error && (
            <div className="text-sm text-white/30 mt-2">Loading schemas...</div>
          )}
        </div>

        {/* Drop zone */}
        <div className="mb-8">
          <label className="block text-sm font-medium text-white/60 mb-2">
            Data File
          </label>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200 ${
              dragging
                ? "border-[#E94560] bg-[#E94560]/5"
                : file
                ? "border-[#4ADE80]/30 bg-[#4ADE80]/5"
                : "border-white/[0.1] hover:border-white/[0.2] bg-white/[0.02]"
            }`}
          >
            {file ? (
              <div>
                <div className="text-3xl mb-3">📄</div>
                <p className="text-white font-medium">{file.name}</p>
                <p className="text-white/35 text-sm mt-1">{formatSize(file.size)}</p>
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
                <p className="text-white/50 mb-1">
                  Drag and drop your file here
                </p>
                <p className="text-white/25 text-sm mb-4">
                  CSV, Excel, JSON, or TSV — up to 10MB
                </p>
                <label className="inline-block px-5 py-2 bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.1] rounded-lg text-sm text-white/60 cursor-pointer transition-all">
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
          <div className="mb-6 p-4 bg-[#E94560]/10 border border-[#E94560]/20 rounded-xl">
            <p className="text-sm text-[#E94560]">{error}</p>
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
          <div className="mt-8 bg-[#12121A] border border-white/[0.06] rounded-xl p-5">
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
