"use client";

import { useState, useEffect } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface SchemaInfo {
  id: string;
  name: string;
  description: string | null;
  is_custom: boolean;
  field_count: number;
  created_at: string;
}

export default function SchemasPage() {
  const [customSchemas, setCustomSchemas] = useState<SchemaInfo[]>([]);
  const [systemSchemas, setSystemSchemas] = useState<SchemaInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [duplicating, setDuplicating] = useState<string | null>(null);

  useEffect(() => {
    loadSchemas();
  }, []);

  const loadSchemas = async () => {
    setLoading(true);
    try {
      // Fetch system schemas
      const sysRes = await fetch(`${API_URL}/api/schemas`);
      const sysData = await sysRes.json();
      const system = (sysData.schemas || []).filter((s: SchemaInfo) => !s.is_custom);
      setSystemSchemas(system);

      // Fetch custom schemas
      const customRes = await fetch(`${API_URL}/api/schemas/custom`);
      const customData = await customRes.json();
      setCustomSchemas(customData.schemas || []);
    } catch {
      // Silently fail — schemas will just be empty
    }
    setLoading(false);
  };

  const handleDelete = async (schemaId: string, schemaName: string) => {
    if (!confirm(`Delete "${schemaName}"? This cannot be undone.`)) return;
    setDeleting(schemaId);
    try {
      const res = await fetch(`${API_URL}/api/schemas/${schemaId}`, { method: "DELETE" });
      if (res.ok) {
        setCustomSchemas((prev) => prev.filter((s) => s.id !== schemaId));
      } else {
        const err = await res.json().catch(() => null);
        alert(err?.detail || "Failed to delete schema");
      }
    } catch {
      alert("Failed to delete schema");
    }
    setDeleting(null);
  };

  const handleDuplicate = async (schemaId: string) => {
    setDuplicating(schemaId);
    try {
      const res = await fetch(`${API_URL}/api/schemas/${schemaId}/duplicate`, {
        method: "POST",
      });
      if (res.ok) {
        await loadSchemas();
      } else {
        const err = await res.json().catch(() => null);
        alert(err?.detail || "Failed to duplicate schema");
      }
    } catch {
      alert("Failed to duplicate schema");
    }
    setDuplicating(null);
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
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
        <div className="flex items-center gap-4">
          <a href="/upload" className="text-sm text-white/40 hover:text-white/60 transition-colors">
            Upload
          </a>
          <a
            href="/schemas/new"
            className="px-4 py-2 bg-[#E94560] hover:bg-[#D63B55] rounded-lg text-white text-sm font-medium transition-colors"
          >
            + New Schema
          </a>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold mb-2">Schemas</h1>
        <p className="text-white/40 mb-10">
          Manage your target schemas. Custom schemas can be edited and deleted.
        </p>

        {loading && (
          <div className="text-center py-20 text-white/25">Loading schemas...</div>
        )}

        {/* Custom Schemas */}
        {!loading && (
          <>
            <div className="mb-10">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">
                  My Schemas{" "}
                  <span className="text-white/25 font-normal">({customSchemas.length})</span>
                </h2>
              </div>

              {customSchemas.length === 0 ? (
                <div className="text-center py-10 border border-dashed border-white/[0.08] rounded-xl">
                  <p className="text-white/25 mb-3">No custom schemas yet.</p>
                  <a
                    href="/schemas/new"
                    className="text-sm text-[#E94560] hover:text-[#FF6B6B] transition-colors"
                  >
                    Create your first schema →
                  </a>
                </div>
              ) : (
                <div className="space-y-3">
                  {customSchemas.map((schema) => (
                    <div
                      key={schema.id}
                      className="border border-white/[0.06] bg-white/[0.02] rounded-xl p-5 hover:border-white/[0.1] transition-all"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-white font-semibold truncate">{schema.name}</h3>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#E94560]/10 text-[#E94560] shrink-0">
                              CUSTOM
                            </span>
                          </div>
                          {schema.description && (
                            <p className="text-xs text-white/35 mb-2 line-clamp-1">{schema.description}</p>
                          )}
                          <div className="flex items-center gap-4 text-xs text-white/25">
                            <span>{schema.field_count} fields</span>
                            <span>Created {formatDate(schema.created_at)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() => handleDuplicate(schema.id)}
                            disabled={duplicating === schema.id}
                            className="px-3 py-1.5 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] rounded-lg text-xs text-white/40 hover:text-white/60 transition-all disabled:opacity-50"
                          >
                            {duplicating === schema.id ? "..." : "Duplicate"}
                          </button>
                          <button
                            onClick={() => handleDelete(schema.id, schema.name)}
                            disabled={deleting === schema.id}
                            className="px-3 py-1.5 bg-[#E94560]/10 hover:bg-[#E94560]/20 border border-[#E94560]/20 rounded-lg text-xs text-[#E94560] transition-all disabled:opacity-50"
                          >
                            {deleting === schema.id ? "..." : "Delete"}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* System Schemas */}
            <div>
              <h2 className="text-lg font-semibold mb-4">
                Built-in Schemas{" "}
                <span className="text-white/25 font-normal">({systemSchemas.length})</span>
              </h2>
              <div className="space-y-3">
                {systemSchemas.map((schema) => (
                  <div
                    key={schema.id}
                    className="border border-white/[0.06] bg-white/[0.02] rounded-xl p-5"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-white font-semibold truncate">{schema.name}</h3>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-white/30 shrink-0">
                            SYSTEM
                          </span>
                        </div>
                        {schema.description && (
                          <p className="text-xs text-white/35 line-clamp-1">{schema.description}</p>
                        )}
                      </div>
                      <button
                        onClick={() => handleDuplicate(schema.id)}
                        disabled={duplicating === schema.id}
                        className="px-3 py-1.5 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] rounded-lg text-xs text-white/40 hover:text-white/60 transition-all disabled:opacity-50 shrink-0"
                      >
                        {duplicating === schema.id ? "..." : "Duplicate & Edit"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
