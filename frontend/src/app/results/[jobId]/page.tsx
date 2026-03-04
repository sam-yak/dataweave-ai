"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useTheme, ThemeToggle } from "@/components/ThemeProvider";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface ValidationError { type: string; field: string; row: number | null; value: string | null; message: string; severity: string; }
interface ValidationWarning { type: string; field: string; row: number | null; message: string; severity: string; null_rate?: number; }
interface ValidationInfo { type: string; field: string; row: number | null; message: string; severity: string; is_required?: boolean; }

interface CompletionResult {
  job_id: string; status: string; quality_score: number;
  validation_report: { total_rows: number; clean_rows: number; rows_with_errors: number; total_errors: number; total_warnings: number; total_info?: number; summary: { required_field_errors: number; type_errors: number; format_errors: number; duplicate_warnings: number; anomaly_warnings?: number; anomaly_info?: number; completeness_warnings?: number; unmapped_fields?: number; }; errors: ValidationError[]; warnings: ValidationWarning[]; info?: ValidationInfo[]; };
  export: { csv: string; json: Record<string, unknown>[]; preview: Record<string, unknown>[]; columns: string[]; row_count: number; };
  mappings_applied: number; mappings_rejected: number;
}

export default function ResultsPage() {
  const params = useParams();
  const jobId = params.jobId as string;
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [result, setResult] = useState<CompletionResult | null>(null);
  const [showPreview, setShowPreview] = useState(true);
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    const stored = sessionStorage.getItem("completion_result");
    if (stored) setResult(JSON.parse(stored));
  }, []);

  const handleDownloadCSV = () => {
    if (!result?.export?.csv) return;
    const blob = new Blob([result.export.csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `clean_data_${jobId.slice(0, 8)}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  const handleDownloadJSON = () => {
    if (!result?.export?.json) return;
    const blob = new Blob([JSON.stringify(result.export.json, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `clean_data_${jobId.slice(0, 8)}.json`; a.click(); URL.revokeObjectURL(url);
  };

  const scoreColor = (score: number) => { if (score >= 90) return "#4ADE80"; if (score >= 70) return "#FBBF24"; return "#E94560"; };

  if (!result) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
        <div className="text-center">
          <p style={{ color: "var(--dw-text-secondary)" }} className="mb-4">No results found. Please run the pipeline first.</p>
          <a href="/upload" className="text-[#E94560] hover:underline">Go to upload →</a>
        </div>
      </div>
    );
  }

  const report = result.validation_report;
  const infoMessages = report.info || [];
  const unmappedCount = report.summary?.unmapped_fields || 0;

  return (
    <div className="min-h-screen" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-20 py-5" style={{ borderBottom: "1px solid var(--dw-border)" }}>
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ color: "var(--dw-text-primary)" }}>data<span className="text-[#E94560]">weave</span></span>
        </a>
        <ThemeToggle />
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Quality score */}
        <div className="text-center mb-12">
          <div className="text-xs font-mono uppercase tracking-[0.2em] mb-4" style={{ color: "var(--dw-text-tertiary)" }}>Quality Score</div>
          <div className="text-8xl font-bold mb-2" style={{ color: scoreColor(result.quality_score) }}>{result.quality_score}%</div>
          <p style={{ color: "var(--dw-text-secondary)" }}>{report.clean_rows} of {report.total_rows} rows are clean</p>
          {unmappedCount > 0 && <p className="text-xs mt-2" style={{ color: "var(--dw-text-muted)" }}>{unmappedCount} schema field{unmappedCount > 1 ? "s" : ""} had no source data — this is expected and does not affect the score.</p>}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
          {[
            { label: "Total Rows", value: report.total_rows, color: "var(--dw-text-primary)" },
            { label: "Clean Rows", value: report.clean_rows, color: "#4ADE80" },
            { label: "Errors", value: report.total_errors, color: "#E94560" },
            { label: "Warnings", value: report.total_warnings, color: "#FBBF24" },
          ].map((stat, i) => (
            <div key={i} className="rounded-xl p-4 text-center" style={{ background: "var(--dw-bg-card)", border: "1px solid var(--dw-border)" }}>
              <div className="text-2xl font-bold" style={{ color: stat.color }}>{stat.value}</div>
              <div className="text-xs mt-1" style={{ color: "var(--dw-text-tertiary)" }}>{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Mappings summary */}
        <div className="flex gap-3 mb-10">
          <div className="flex-1 bg-[#4ADE80]/[0.05] border border-[#4ADE80]/10 rounded-xl p-4 text-center">
            <div className="text-xl font-bold text-[#4ADE80]">{result.mappings_applied}</div>
            <div className="text-xs mt-1" style={{ color: "var(--dw-text-tertiary)" }}>Mappings Applied</div>
          </div>
          <div className="flex-1 bg-[#E94560]/[0.05] border border-[#E94560]/10 rounded-xl p-4 text-center">
            <div className="text-xl font-bold text-[#E94560]">{result.mappings_rejected}</div>
            <div className="text-xs mt-1" style={{ color: "var(--dw-text-tertiary)" }}>Rejected</div>
          </div>
          <div className="flex-1 rounded-xl p-4 text-center" style={{ background: "var(--dw-bg-card)", border: "1px solid var(--dw-border)" }}>
            <div className="text-xl font-bold">{result.export.columns.length}</div>
            <div className="text-xs mt-1" style={{ color: "var(--dw-text-tertiary)" }}>Output Columns</div>
          </div>
        </div>

        {/* Download */}
        <div className="flex gap-4 mb-10">
          <button onClick={handleDownloadCSV} className="flex-1 py-3.5 bg-[#E94560] hover:bg-[#D63B55] rounded-xl text-white font-semibold transition-all text-center">Download CSV</button>
          <button onClick={handleDownloadJSON} className="flex-1 py-3.5 rounded-xl font-medium transition-all text-center" style={{ background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)", border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.1)"}`, color: "var(--dw-text-secondary)" }}>Download JSON</button>
        </div>

        {/* Errors */}
        {report.errors.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-[#E94560]">Errors ({report.total_errors})</h2>
            <div className="space-y-2">
              {report.errors.map((err, i) => (
                <div key={i} className="bg-[#E94560]/[0.05] border border-[#E94560]/10 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <span className="text-xs font-mono text-[#E94560] bg-[#E94560]/10 px-2 py-0.5 rounded">{err.type}</span>
                      <p className="text-sm mt-2" style={{ color: "var(--dw-text-secondary)" }}>{err.message}</p>
                    </div>
                    {err.row !== null && <span className="text-xs font-mono shrink-0" style={{ color: "var(--dw-text-muted)" }}>Row {err.row + 1}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Warnings */}
        {report.warnings.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-[#FBBF24]">Warnings ({report.total_warnings})</h2>
            <div className="space-y-2">
              {report.warnings.map((warn, i) => (
                <div key={i} className="bg-[#FBBF24]/[0.05] border border-[#FBBF24]/10 rounded-lg p-4">
                  <span className="text-xs font-mono text-[#FBBF24] bg-[#FBBF24]/10 px-2 py-0.5 rounded">{warn.type}</span>
                  <p className="text-sm mt-2" style={{ color: "var(--dw-text-secondary)" }}>{warn.message}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Info */}
        {infoMessages.length > 0 && (
          <div className="mb-8">
            <button onClick={() => setShowInfo(!showInfo)} className="flex items-center gap-2 text-lg font-semibold text-[#60A5FA] mb-4 hover:text-[#93C5FD] transition-colors">
              Info ({infoMessages.length}) <span className={`text-sm transition-transform ${showInfo ? "rotate-180" : ""}`}>▾</span>
            </button>
            {showInfo && (
              <div className="space-y-2">
                {infoMessages.map((info, i) => (
                  <div key={i} className="bg-[#60A5FA]/[0.04] border border-[#60A5FA]/10 rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-[#60A5FA] bg-[#60A5FA]/10 px-2 py-0.5 rounded">{info.type}</span>
                      {info.is_required && <span className="text-[10px] font-mono text-[#FBBF24] bg-[#FBBF24]/10 px-1.5 py-0.5 rounded">required in schema</span>}
                    </div>
                    <p className="text-sm mt-2" style={{ color: "var(--dw-text-secondary)" }}>{info.message}</p>
                  </div>
                ))}
              </div>
            )}
            {!showInfo && <p className="text-xs" style={{ color: "var(--dw-text-muted)" }}>These are schema fields with no source data. They don&apos;t affect your quality score.</p>}
          </div>
        )}

        {/* Data preview */}
        <div className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Data Preview</h2>
            <button onClick={() => setShowPreview(!showPreview)} className="text-xs transition-colors" style={{ color: "var(--dw-text-tertiary)" }}>{showPreview ? "Hide" : "Show"}</button>
          </div>
          {showPreview && (
            <div className="overflow-x-auto rounded-xl" style={{ border: "1px solid var(--dw-border)" }}>
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--dw-border)" }}>
                    {result.export.columns.map((col) => (
                      <th key={col} className="px-4 py-3 text-left font-medium whitespace-nowrap" style={{ color: "var(--dw-text-secondary)", background: isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)" }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.export.preview.map((row, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.03)"}` }}>
                      {result.export.columns.map((col) => (
                        <td key={col} className="px-4 py-2.5 whitespace-nowrap max-w-[200px] truncate" style={{ color: "var(--dw-text-secondary)" }}>
                          {row[col] !== null && row[col] !== undefined ? String(row[col]) : "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="text-center pt-6" style={{ borderTop: "1px solid var(--dw-border)" }}>
          <a href="/upload" className="text-sm transition-colors" style={{ color: "var(--dw-text-tertiary)" }}>← Upload another file</a>
        </div>
      </div>
    </div>
  );
}
