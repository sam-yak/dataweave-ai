"use client";

import { useState, useEffect } from "react";
import { useTheme, ThemeToggle } from "@/components/ThemeProvider";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface SchemaInfo { id: string; name: string; description: string | null; is_custom: boolean; field_count: number; created_at: string; }

export default function SchemasPage() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [customSchemas, setCustomSchemas] = useState<SchemaInfo[]>([]);
  const [systemSchemas, setSystemSchemas] = useState<SchemaInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [duplicating, setDuplicating] = useState<string | null>(null);

  useEffect(() => { loadSchemas(); }, []);

  const loadSchemas = async () => {
    setLoading(true);
    try {
      const sysRes = await fetch(`${API_URL}/api/schemas`);
      const sysData = await sysRes.json();
      setSystemSchemas((sysData.schemas || []).filter((s: SchemaInfo) => !s.is_custom));
      const customRes = await fetch(`${API_URL}/api/schemas/custom`);
      const customData = await customRes.json();
      setCustomSchemas(customData.schemas || []);
    } catch {}
    setLoading(false);
  };

  const handleDelete = async (schemaId: string, schemaName: string) => {
    if (!confirm(`Delete "${schemaName}"? This cannot be undone.`)) return;
    setDeleting(schemaId);
    try { const res = await fetch(`${API_URL}/api/schemas/${schemaId}`, { method: "DELETE" }); if (res.ok) setCustomSchemas((prev) => prev.filter((s) => s.id !== schemaId)); else { const err = await res.json().catch(() => null); alert(err?.detail || "Failed to delete schema"); } } catch { alert("Failed to delete schema"); }
    setDeleting(null);
  };

  const handleDuplicate = async (schemaId: string) => {
    setDuplicating(schemaId);
    try { const res = await fetch(`${API_URL}/api/schemas/${schemaId}/duplicate`, { method: "POST" }); if (res.ok) await loadSchemas(); else { const err = await res.json().catch(() => null); alert(err?.detail || "Failed to duplicate schema"); } } catch { alert("Failed to duplicate schema"); }
    setDuplicating(null);
  };

  const formatDate = (dateStr: string) => { try { return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); } catch { return dateStr; } };

  return (
    <div className="min-h-screen" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-20 py-5" style={{ borderBottom: "1px solid var(--dw-border)" }}>
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ color: "var(--dw-text-primary)" }}>data<span className="text-[#E94560]">weave</span></span>
        </a>
        <div className="flex items-center gap-4">
          <a href="/upload" className="text-sm transition-colors" style={{ color: "var(--dw-text-secondary)" }}>Upload</a>
          <ThemeToggle />
          <a href="/schemas/new" className="px-4 py-2 bg-[#E94560] hover:bg-[#D63B55] rounded-lg text-white text-sm font-medium transition-colors">+ New Schema</a>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold mb-2">Schemas</h1>
        <p className="mb-10" style={{ color: "var(--dw-text-secondary)" }}>Manage your target schemas. Custom schemas can be edited and deleted.</p>

        {loading && <div className="text-center py-20" style={{ color: "var(--dw-text-muted)" }}>Loading schemas...</div>}

        {!loading && (
          <>
            <div className="mb-10">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">My Schemas <span className="font-normal" style={{ color: "var(--dw-text-muted)" }}>({customSchemas.length})</span></h2>
              </div>
              {customSchemas.length === 0 ? (
                <div className="text-center py-10 border-2 border-dashed rounded-xl" style={{ borderColor: "var(--dw-border)" }}>
                  <p className="mb-3" style={{ color: "var(--dw-text-muted)" }}>No custom schemas yet.</p>
                  <a href="/schemas/new" className="text-sm text-[#E94560] hover:text-[#FF6B6B] transition-colors">Create your first schema →</a>
                </div>
              ) : (
                <div className="space-y-3">
                  {customSchemas.map((schema) => (
                    <div key={schema.id} className="rounded-xl p-5 transition-all" style={{ border: "1px solid var(--dw-border)", background: isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.01)" }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--dw-border-strong)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--dw-border)"; }}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold truncate">{schema.name}</h3>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#E94560]/10 text-[#E94560] shrink-0">CUSTOM</span>
                          </div>
                          {schema.description && <p className="text-xs mb-2 line-clamp-1" style={{ color: "var(--dw-text-tertiary)" }}>{schema.description}</p>}
                          <div className="flex items-center gap-4 text-xs" style={{ color: "var(--dw-text-muted)" }}>
                            <span>{schema.field_count} fields</span>
                            <span>Created {formatDate(schema.created_at)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button onClick={() => handleDuplicate(schema.id)} disabled={duplicating === schema.id} className="px-3 py-1.5 rounded-lg text-xs transition-all disabled:opacity-50" style={{ background: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)", border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`, color: "var(--dw-text-secondary)" }}>{duplicating === schema.id ? "..." : "Duplicate"}</button>
                          <button onClick={() => handleDelete(schema.id, schema.name)} disabled={deleting === schema.id} className="px-3 py-1.5 bg-[#E94560]/10 hover:bg-[#E94560]/20 border border-[#E94560]/20 rounded-lg text-xs text-[#E94560] transition-all disabled:opacity-50">{deleting === schema.id ? "..." : "Delete"}</button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h2 className="text-lg font-semibold mb-4">Built-in Schemas <span className="font-normal" style={{ color: "var(--dw-text-muted)" }}>({systemSchemas.length})</span></h2>
              <div className="space-y-3">
                {systemSchemas.map((schema) => (
                  <div key={schema.id} className="rounded-xl p-5" style={{ border: "1px solid var(--dw-border)", background: isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.01)" }}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold truncate">{schema.name}</h3>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0" style={{ background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)", color: "var(--dw-text-tertiary)" }}>SYSTEM</span>
                        </div>
                        {schema.description && <p className="text-xs line-clamp-1" style={{ color: "var(--dw-text-tertiary)" }}>{schema.description}</p>}
                      </div>
                      <button onClick={() => handleDuplicate(schema.id)} disabled={duplicating === schema.id} className="px-3 py-1.5 rounded-lg text-xs transition-all disabled:opacity-50 shrink-0" style={{ background: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)", border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`, color: "var(--dw-text-secondary)" }}>{duplicating === schema.id ? "..." : "Duplicate & Edit"}</button>
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
