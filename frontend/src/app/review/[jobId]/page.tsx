"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useTheme, ThemeToggle } from "@/components/ThemeProvider";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface Mapping {
  id: string;
  source_name: string;
  target_field: string | null;
  confidence: number;
  agent_source: string;
  reasoning: string;
  transform_type: string | null;
  status: string;
}

interface PipelineResult {
  job_id: string;
  status: string;
  metadata: { row_count: number; column_count: number; file_type: string };
  mapping_summary: { total_columns: number; mapped: number; unmapped: number; pattern_agent_resolved: number; llm_resolved: number };
  mappings: Mapping[];
}

export default function ReviewPage() {
  const router = useRouter();
  const params = useParams();
  const jobId = params.jobId as string;
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [result, setResult] = useState<PipelineResult | null>(null);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("pipeline_result");
    if (stored) {
      const data = JSON.parse(stored) as PipelineResult;
      setResult(data);
      setMappings(data.mappings);
      return;
    }
    fetch(`${API_URL}/api/jobs/${jobId}/mappings`)
      .then((res) => res.json())
      .then((data) => { if (data.mappings) setMappings(data.mappings); })
      .catch(() => setError("Could not load mappings."));
  }, [jobId]);

  const confidenceColor = (c: number) => { if (c >= 90) return "#4ADE80"; if (c >= 75) return "#FBBF24"; return "#E94560"; };
  const confidenceLabel = (c: number) => { if (c >= 90) return "High"; if (c >= 75) return "Medium"; return "Low"; };

  const handleApprove = async (mappingId: string) => {
    setActionLoading(mappingId);
    try { await fetch(`${API_URL}/api/jobs/${jobId}/mappings/${mappingId}/approve`, { method: "POST" }); setMappings((prev) => prev.map((m) => (m.id === mappingId ? { ...m, status: "approved" } : m))); } catch { setError("Failed to approve mapping."); }
    setActionLoading(null);
  };

  const handleReject = async (mappingId: string) => {
    setActionLoading(mappingId);
    try { await fetch(`${API_URL}/api/jobs/${jobId}/mappings/${mappingId}/reject`, { method: "POST" }); setMappings((prev) => prev.map((m) => (m.id === mappingId ? { ...m, status: "rejected" } : m))); } catch { setError("Failed to reject mapping."); }
    setActionLoading(null);
  };

  const handleApproveAll = async () => {
    setActionLoading("bulk");
    try { await fetch(`${API_URL}/api/jobs/${jobId}/mappings/approve-all`, { method: "POST" }); setMappings((prev) => prev.map((m) => m.status === "proposed" && m.confidence >= 85 ? { ...m, status: "approved" } : m)); } catch { setError("Failed to bulk approve."); }
    setActionLoading(null);
  };

  const handleComplete = async () => {
    setCompleting(true); setError("");
    try {
      const res = await fetch(`${API_URL}/api/jobs/${jobId}/complete`, { method: "POST" });
      if (!res.ok) { const errData = await res.json().catch(() => null); throw new Error(errData?.detail || "Pipeline completion failed"); }
      const data = await res.json();
      sessionStorage.setItem("completion_result", JSON.stringify(data));
      router.push(`/results/${jobId}`);
    } catch (err: unknown) { setError(err instanceof Error ? err.message : "Completion failed."); setCompleting(false); }
  };

  const proposedCount = mappings.filter((m) => m.status === "proposed").length;
  const approvedCount = mappings.filter((m) => m.status === "approved" || m.status === "corrected").length;
  const rejectedCount = mappings.filter((m) => m.status === "rejected").length;

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
          <span className="text-sm font-mono" style={{ color: "var(--dw-text-muted)" }}>Job: {jobId?.slice(0, 8)}...</span>
          <ThemeToggle />
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-bold mb-1">Review Mappings</h1>
            <p className="text-sm" style={{ color: "var(--dw-text-secondary)" }}>Our AI mapped your columns. Review and approve before transforming.</p>
          </div>
          {result?.mapping_summary && (
            <div className="flex gap-2 text-xs font-mono">
              <span className="px-2.5 py-1 bg-[#4ADE80]/10 text-[#4ADE80] rounded-md">{result.mapping_summary.pattern_agent_resolved} pattern</span>
              <span className="px-2.5 py-1 bg-[#FBBF24]/10 text-[#FBBF24] rounded-md">{result.mapping_summary.llm_resolved} LLM</span>
              <span className="px-2.5 py-1 rounded-md" style={{ background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)", color: "var(--dw-text-secondary)" }}>{result.metadata?.row_count} rows</span>
            </div>
          )}
        </div>

        {/* Action bar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6 p-4 rounded-xl" style={{ background: isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)", border: "1px solid var(--dw-border)" }}>
          <div className="flex gap-4 text-sm" style={{ color: "var(--dw-text-secondary)" }}>
            <span><span className="text-[#FBBF24] font-bold">{proposedCount}</span> pending</span>
            <span><span className="text-[#4ADE80] font-bold">{approvedCount}</span> approved</span>
            <span><span className="text-[#E94560] font-bold">{rejectedCount}</span> rejected</span>
          </div>
          <div className="flex gap-3">
            {proposedCount > 0 && (
              <button onClick={handleApproveAll} disabled={actionLoading === "bulk"} className="px-4 py-2 bg-[#4ADE80]/10 hover:bg-[#4ADE80]/20 border border-[#4ADE80]/20 text-[#4ADE80] text-sm rounded-lg transition-all disabled:opacity-50">
                {actionLoading === "bulk" ? "Approving..." : "Approve All ≥85%"}
              </button>
            )}
            <button onClick={handleComplete} disabled={completing} className="px-5 py-2 bg-[#E94560] hover:bg-[#D63B55] text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50">
              {completing ? (<span className="flex items-center gap-2"><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>Transforming...</span>) : "Transform & Validate →"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-xl" style={{ background: "var(--dw-error-light)", border: "1px solid var(--dw-error-border)" }}>
            <p className="text-sm" style={{ color: "var(--dw-error)" }}>{error}</p>
          </div>
        )}

        {/* Mapping cards */}
        <div className="space-y-3">
          {mappings.map((mapping, index) => (
            <div
              key={mapping.id || `mapping-${index}`}
              className="rounded-xl p-5 transition-all duration-200"
              style={{
                border: mapping.status === "approved" || mapping.status === "corrected"
                  ? "1px solid rgba(74,222,128,0.2)" : mapping.status === "rejected"
                  ? "1px solid rgba(233,69,96,0.2)" : "1px solid var(--dw-border)",
                background: mapping.status === "approved" || mapping.status === "corrected"
                  ? "rgba(74,222,128,0.03)" : mapping.status === "rejected"
                  ? "rgba(233,69,96,0.03)" : isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.01)",
                opacity: mapping.status === "rejected" ? 0.5 : 1,
              }}
            >
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="flex-1 flex items-center gap-3 min-w-0">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs mb-1" style={{ color: "var(--dw-text-tertiary)" }}>Source Column</div>
                    <div className="font-mono text-sm truncate" style={{ color: "var(--dw-text-primary)" }}>{mapping.source_name}</div>
                  </div>
                  <div className="text-lg shrink-0" style={{ color: "var(--dw-text-muted)" }}>→</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs mb-1" style={{ color: "var(--dw-text-tertiary)" }}>Target Field</div>
                    <div className="font-mono text-sm truncate" style={{ color: "var(--dw-text-primary)" }}>
                      {mapping.target_field || <span style={{ color: "var(--dw-text-muted)", fontStyle: "italic" }}>unmapped</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <div className="text-sm font-bold font-mono" style={{ color: confidenceColor(mapping.confidence) }}>{mapping.confidence}%</div>
                    <div className="text-[10px]" style={{ color: "var(--dw-text-muted)" }}>{confidenceLabel(mapping.confidence)}</div>
                  </div>
                  <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full" style={{ backgroundColor: mapping.agent_source === "pattern" ? "#4ADE8015" : "#FBBF2415", color: mapping.agent_source === "pattern" ? "#4ADE80" : "#FBBF24" }}>{mapping.agent_source}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {mapping.status === "proposed" ? (
                    <>
                      <button onClick={() => handleApprove(mapping.id)} disabled={actionLoading === mapping.id} className="px-3 py-1.5 bg-[#4ADE80]/10 hover:bg-[#4ADE80]/20 text-[#4ADE80] text-xs rounded-lg transition-all disabled:opacity-50">✓</button>
                      <button onClick={() => handleReject(mapping.id)} disabled={actionLoading === mapping.id} className="px-3 py-1.5 bg-[#E94560]/10 hover:bg-[#E94560]/20 text-[#E94560] text-xs rounded-lg transition-all disabled:opacity-50">✕</button>
                    </>
                  ) : (
                    <span className={`text-xs font-medium px-3 py-1.5 rounded-lg ${mapping.status === "approved" || mapping.status === "corrected" ? "bg-[#4ADE80]/10 text-[#4ADE80]" : "bg-[#E94560]/10 text-[#E94560]"}`}>{mapping.status}</span>
                  )}
                </div>
              </div>
              {mapping.reasoning && (
                <div className="mt-3 pt-3" style={{ borderTop: `1px solid ${isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}` }}>
                  <p className="text-xs" style={{ color: "var(--dw-text-muted)" }}>{mapping.reasoning}</p>
                </div>
              )}
            </div>
          ))}
        </div>

        {mappings.length === 0 && (
          <div className="text-center py-20" style={{ color: "var(--dw-text-muted)" }}>
            <p>No mappings found. Please upload a file first.</p>
            <a href="/upload" className="text-[#E94560] text-sm mt-2 inline-block hover:underline">Go to upload →</a>
          </div>
        )}
      </div>
    </div>
  );
}
