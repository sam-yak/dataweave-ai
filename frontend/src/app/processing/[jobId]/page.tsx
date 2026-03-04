"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://dataweave-ai-production-8516.up.railway.app";

// ── Pipeline stages in order ──────────────────────────────────

interface Stage {
  key: string;
  label: string;
  description: string;
}

const STAGES: Stage[] = [
  {
    key: "uploading",
    label: "Upload",
    description: "Receiving your file...",
  },
  {
    key: "ingesting",
    label: "Ingestion Agent",
    description: "Parsing file, detecting types, profiling columns...",
  },
  {
    key: "mapping",
    label: "Pattern + Schema Agent",
    description: "AI is mapping your columns to the target schema...",
  },
  {
    key: "awaiting_review",
    label: "Ready for Review",
    description: "Mapping complete — redirecting to review page...",
  },
];

function getStageIndex(stage: string): number {
  // "complete" means the async pipeline finished — same as awaiting_review for UI
  if (stage === "complete" || stage === "awaiting_review") {
    return STAGES.length - 1; // Last stage (Ready for Review)
  }
  const idx = STAGES.findIndex((s) => s.key === stage);
  return idx >= 0 ? idx : 0;
}

// ── Component ─────────────────────────────────────────────────

export default function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();

  const [stage, setStage] = useState("uploading");
  const [message, setMessage] = useState("Starting pipeline...");
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dots, setDots] = useState("");
  const [redirecting, setRedirecting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dotsRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Animate dots
  useEffect(() => {
    dotsRef.current = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 500);
    return () => {
      if (dotsRef.current) clearInterval(dotsRef.current);
    };
  }, []);

  // Poll for status
  const pollStatus = useCallback(async () => {
    if (redirecting) return; // Don't poll if already redirecting

    try {
      const res = await fetch(`${API_URL}/api/jobs/${jobId}/status`);
      if (!res.ok) return;

      const data = await res.json();

      setStage(data.stage);
      setMessage(data.message || "Processing...");
      if (data.progress >= 0) setProgress(data.progress);
      if (data.elapsed_seconds) setElapsed(data.elapsed_seconds);

      // Handle errors
      if (data.stage === "failed" || data.error) {
        setError(data.error || "Pipeline failed");
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }

      // Pipeline done — redirect to review page
      // Check BOTH "awaiting_review" and "complete" since the background
      // task calls set_complete() which sets stage to "complete"
      const isDone =
        data.stage === "awaiting_review" || data.stage === "complete";

      if (isDone && data.has_result) {
        if (pollRef.current) clearInterval(pollRef.current);
        setRedirecting(true);

        // Fetch the full result and store for review page
        try {
          const resultRes = await fetch(
            `${API_URL}/api/jobs/${jobId}/result`
          );
          if (resultRes.ok) {
            const resultData = await resultRes.json();
            sessionStorage.setItem(
              "pipeline_result",
              JSON.stringify(resultData)
            );
          }
        } catch {
          // Result fetch failed — review page will handle it via API
        }

        // Short delay so user sees "Ready for Review" state
        setTimeout(() => {
          router.push(`/review/${jobId}`);
        }, 1200);
      }
    } catch {
      // Network error — keep polling, it might recover
    }
  }, [jobId, router, redirecting]);

  useEffect(() => {
    // Start polling immediately
    pollStatus();
    pollRef.current = setInterval(pollStatus, 1500);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollStatus]);

  // ── Render ────────────────────────────────────────────────

  const currentStageIndex = getStageIndex(stage);
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };

  return (
    <div className="min-h-screen bg-[#0A0A0F] text-white">
      {/* Grain overlay */}
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-[0.03]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
      <div className="fixed top-0 left-1/3 w-[500px] h-[500px] bg-[#E94560]/5 rounded-full blur-[180px] pointer-events-none" />

      {/* Nav */}
      <nav className="relative z-40 flex items-center justify-between px-6 md:px-12 lg:px-20 py-5 border-b border-white/[0.05]">
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </div>
          <span className="text-lg font-bold tracking-tight">
            data<span className="text-[#E94560]">weave</span>
          </span>
        </a>
        <div className="text-xs text-white/25 font-mono">
          Job: {jobId?.slice(0, 8)}...
        </div>
      </nav>

      {/* Main content */}
      <div className="relative z-10 max-w-xl mx-auto px-6 py-20">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-2xl font-bold mb-2">
            {error
              ? "Pipeline Failed"
              : redirecting
              ? "Ready for Review!"
              : "Processing Your Data"}
          </h1>
          <p className="text-white/40 text-sm">
            {error
              ? "Something went wrong during processing."
              : redirecting
              ? "Redirecting you to review your column mappings..."
              : "Our AI agents are working on your file. This usually takes 10–30 seconds."}
          </p>
        </div>

        {/* Progress bar */}
        {!error && (
          <div className="mb-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/40 font-mono">
                {progress}%
              </span>
              <span className="text-xs text-white/25 font-mono">
                {formatTime(elapsed)}
              </span>
            </div>
            <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[#E94560] to-[#FF6B6B] rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Stage timeline */}
        <div className="space-y-0">
          {STAGES.map((s, i) => {
            const isActive = i === currentStageIndex && !error && !redirecting;
            const isDone = i < currentStageIndex || redirecting;
            const isFuture = i > currentStageIndex && !redirecting;

            return (
              <div key={s.key} className="flex gap-4">
                {/* Timeline line + dot */}
                <div className="flex flex-col items-center w-6 shrink-0">
                  {/* Dot */}
                  <div
                    className={`w-3 h-3 rounded-full shrink-0 transition-all duration-500 ${
                      isDone
                        ? "bg-[#4ADE80]"
                        : isActive
                        ? "bg-[#E94560] shadow-[0_0_12px_rgba(233,69,96,0.5)]"
                        : "bg-white/[0.08]"
                    }`}
                  />
                  {/* Line */}
                  {i < STAGES.length - 1 && (
                    <div
                      className={`w-0.5 flex-1 min-h-[40px] transition-colors duration-500 ${
                        isDone ? "bg-[#4ADE80]/30" : "bg-white/[0.06]"
                      }`}
                    />
                  )}
                </div>

                {/* Content */}
                <div className={`pb-6 ${isFuture ? "opacity-30" : ""}`}>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-medium ${
                        isActive ? "text-white" : isDone ? "text-white/60" : "text-white/30"
                      }`}
                    >
                      {s.label}
                    </span>
                    {isDone && (
                      <span className="text-[10px] font-mono text-[#4ADE80]">
                        DONE
                      </span>
                    )}
                    {isActive && (
                      <span className="text-[10px] font-mono text-[#E94560]">
                        RUNNING{dots}
                      </span>
                    )}
                  </div>
                  <p
                    className={`text-xs mt-0.5 ${
                      isActive ? "text-white/50" : "text-white/20"
                    }`}
                  >
                    {isActive ? message : s.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Error state */}
        {error && (
          <div className="mt-8">
            <div className="p-5 bg-[#E94560]/10 border border-[#E94560]/20 rounded-xl mb-6">
              <div className="flex items-start gap-3">
                <div className="text-[#E94560] text-lg shrink-0 mt-0.5">
                  ✕
                </div>
                <div>
                  <p className="text-sm font-medium text-[#E94560] mb-1">
                    Error
                  </p>
                  <p className="text-xs text-white/50 font-mono break-all">
                    {error}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <a
                href="/upload"
                className="flex-1 py-3 bg-[#E94560] hover:bg-[#D63B55] rounded-xl text-white text-sm font-semibold text-center transition-colors"
              >
                Try Again
              </a>
              <a
                href="/"
                className="py-3 px-6 bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.08] rounded-xl text-white/50 text-sm text-center transition-colors"
              >
                Home
              </a>
            </div>
          </div>
        )}

        {/* Redirecting notice */}
        {redirecting && (
          <div className="mt-4 text-center">
            <p className="text-sm text-[#4ADE80] animate-pulse">
              Redirecting to review page...
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
