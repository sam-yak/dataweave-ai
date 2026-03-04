"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTheme } from "@/components/ThemeProvider";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

interface Stage {
  key: string;
  label: string;
  description: string;
}

const STAGES: Stage[] = [
  { key: "uploading", label: "Upload", description: "Receiving your file..." },
  { key: "ingesting", label: "Ingestion Agent", description: "Parsing file, detecting types, profiling columns..." },
  { key: "mapping", label: "Pattern + Schema Agent", description: "AI is mapping your columns to the target schema..." },
  { key: "awaiting_review", label: "Ready for Review", description: "Mapping complete — redirecting to review page..." },
];

function getStageIndex(stage: string): number {
  if (stage === "complete" || stage === "awaiting_review") return STAGES.length - 1;
  const idx = STAGES.findIndex((s) => s.key === stage);
  return idx >= 0 ? idx : 0;
}

export default function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [stage, setStage] = useState("uploading");
  const [message, setMessage] = useState("Starting pipeline...");
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dots, setDots] = useState("");
  const [redirecting, setRedirecting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dotsRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    dotsRef.current = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 500);
    return () => { if (dotsRef.current) clearInterval(dotsRef.current); };
  }, []);

  const pollStatus = useCallback(async () => {
    if (redirecting) return;
    try {
      const res = await fetch(`${API_URL}/api/jobs/${jobId}/status`);
      if (!res.ok) return;
      const data = await res.json();
      setStage(data.stage);
      setMessage(data.message || "Processing...");
      if (data.progress >= 0) setProgress(data.progress);
      if (data.elapsed_seconds) setElapsed(data.elapsed_seconds);
      if (data.stage === "failed" || data.error) {
        setError(data.error || "Pipeline failed");
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
      const isDone = data.stage === "awaiting_review" || data.stage === "complete";
      if (isDone && data.has_result) {
        if (pollRef.current) clearInterval(pollRef.current);
        setRedirecting(true);
        try {
          const resultRes = await fetch(`${API_URL}/api/jobs/${jobId}/result`);
          if (resultRes.ok) {
            const resultData = await resultRes.json();
            sessionStorage.setItem("pipeline_result", JSON.stringify(resultData));
          }
        } catch {}
        setTimeout(() => { router.push(`/review/${jobId}`); }, 1200);
      }
    } catch {}
  }, [jobId, router, redirecting]);

  useEffect(() => {
    pollStatus();
    pollRef.current = setInterval(pollStatus, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollStatus]);

  const currentStageIndex = getStageIndex(stage);
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
      {/* Grain overlay (dark only) */}
      <div
        className="fixed inset-0 pointer-events-none z-50"
        style={{
          opacity: "var(--dw-grain-opacity)",
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
      {isDark && <div className="fixed top-0 left-1/3 w-[500px] h-[500px] bg-[#E94560]/5 rounded-full blur-[180px] pointer-events-none" />}

      {/* Nav */}
      <nav className="relative z-40 flex items-center justify-between px-6 md:px-12 lg:px-20 py-5" style={{ borderBottom: "1px solid var(--dw-border)" }}>
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
        <div className="text-xs font-mono" style={{ color: "var(--dw-text-muted)" }}>
          Job: {jobId?.slice(0, 8)}...
        </div>
      </nav>

      <div className="relative z-10 max-w-xl mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h1 className="text-2xl font-bold mb-2">
            {error ? "Pipeline Failed" : redirecting ? "Ready for Review!" : "Processing Your Data"}
          </h1>
          <p className="text-sm" style={{ color: "var(--dw-text-secondary)" }}>
            {error ? "Something went wrong during processing." : redirecting ? "Redirecting you to review your column mappings..." : "Our AI agents are working on your file. This usually takes 10–30 seconds."}
          </p>
        </div>

        {!error && (
          <div className="mb-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono" style={{ color: "var(--dw-text-secondary)" }}>{progress}%</span>
              <span className="text-xs font-mono" style={{ color: "var(--dw-text-muted)" }}>{formatTime(elapsed)}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" }}>
              <div className="h-full bg-gradient-to-r from-[#E94560] to-[#FF6B6B] rounded-full transition-all duration-700 ease-out" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        <div className="space-y-0">
          {STAGES.map((s, i) => {
            const isActive = i === currentStageIndex && !error && !redirecting;
            const isDone = i < currentStageIndex || redirecting;
            const isFuture = i > currentStageIndex && !redirecting;
            return (
              <div key={s.key} className="flex gap-4">
                <div className="flex flex-col items-center w-6 shrink-0">
                  <div className={`w-3 h-3 rounded-full shrink-0 transition-all duration-500 ${isDone ? "bg-[#4ADE80]" : isActive ? "bg-[#E94560] shadow-[0_0_12px_rgba(233,69,96,0.5)]" : ""}`} style={!isDone && !isActive ? { background: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)" } : {}} />
                  {i < STAGES.length - 1 && (
                    <div className="w-0.5 flex-1 min-h-[40px] transition-colors duration-500" style={{ background: isDone ? "rgba(74,222,128,0.3)" : isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" }} />
                  )}
                </div>
                <div className={`pb-6 ${isFuture ? "opacity-30" : ""}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: isActive ? "var(--dw-text-primary)" : isDone ? "var(--dw-text-secondary)" : "var(--dw-text-tertiary)" }}>{s.label}</span>
                    {isDone && <span className="text-[10px] font-mono text-[#4ADE80]">DONE</span>}
                    {isActive && <span className="text-[10px] font-mono text-[#E94560]">RUNNING{dots}</span>}
                  </div>
                  <p className="text-xs mt-0.5" style={{ color: isActive ? "var(--dw-text-secondary)" : "var(--dw-text-muted)" }}>{isActive ? message : s.description}</p>
                </div>
              </div>
            );
          })}
        </div>

        {error && (
          <div className="mt-8">
            <div className="p-5 rounded-xl mb-6" style={{ background: "var(--dw-error-light)", border: "1px solid var(--dw-error-border)" }}>
              <div className="flex items-start gap-3">
                <div className="text-lg shrink-0 mt-0.5" style={{ color: "var(--dw-error)" }}>✕</div>
                <div>
                  <p className="text-sm font-medium mb-1" style={{ color: "var(--dw-error)" }}>Error</p>
                  <p className="text-xs font-mono break-all" style={{ color: "var(--dw-text-secondary)" }}>{error}</p>
                </div>
              </div>
            </div>
            <div className="flex gap-3">
              <a href="/upload" className="flex-1 py-3 bg-[#E94560] hover:bg-[#D63B55] rounded-xl text-white text-sm font-semibold text-center transition-colors">Try Again</a>
              <a href="/" className="py-3 px-6 rounded-xl text-sm text-center transition-colors" style={{ background: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)", border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`, color: "var(--dw-text-secondary)" }}>Home</a>
            </div>
          </div>
        )}

        {redirecting && (
          <div className="mt-4 text-center">
            <p className="text-sm text-[#4ADE80] animate-pulse">Redirecting to review page...</p>
          </div>
        )}
      </div>
    </div>
  );
}
