"use client";

import { useState, useEffect, useRef } from "react";
import { useTheme, ThemeToggle } from "@/components/ThemeProvider";
import Footer from "@/components/Footer";

// ── Animated counter ────────────────────────────────────────
function AnimatedNumber({ target, suffix = "" }: { target: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasAnimated.current) {
          hasAnimated.current = true;
          let start = 0;
          const duration = 1500;
          const step = (timestamp: number) => {
            if (!start) start = timestamp;
            const progress = Math.min((timestamp - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            setCount(Math.floor(eased * target));
            if (progress < 1) requestAnimationFrame(step);
          };
          requestAnimationFrame(step);
        }
      },
      { threshold: 0.5 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [target]);

  return (
    <span ref={ref}>
      {count}
      {suffix}
    </span>
  );
}

// ── Fade-in on scroll ───────────────────────────────────────
function FadeIn({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.15 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(32px)",
        transition: `opacity 0.7s ease ${delay}ms, transform 0.7s ease ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

// ── Agent card ──────────────────────────────────────────────
function AgentCard({
  number,
  name,
  description,
  tag,
  color,
  delay,
}: {
  number: string;
  name: string;
  description: string;
  tag: string;
  color: string;
  delay: number;
}) {
  return (
    <FadeIn delay={delay}>
      <div
        className="group relative backdrop-blur-sm rounded-2xl p-7 transition-all duration-500 h-full"
        style={{
          background: "var(--dw-bg-card)",
          border: "1px solid var(--dw-border)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--dw-border-strong)";
          e.currentTarget.style.background = "var(--dw-bg-card-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--dw-border)";
          e.currentTarget.style.background = "var(--dw-bg-card)";
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-mono font-bold"
            style={{ backgroundColor: color + "20", color }}
          >
            {number}
          </div>
          <span
            className="text-[11px] font-mono uppercase tracking-widest px-2.5 py-1 rounded-full"
            style={{ backgroundColor: color + "15", color }}
          >
            {tag}
          </span>
        </div>
        <h3 className="text-lg font-semibold mb-2" style={{ color: "var(--dw-text-primary)" }}>{name}</h3>
        <p className="text-sm leading-relaxed" style={{ color: "var(--dw-text-secondary)" }}>{description}</p>
      </div>
    </FadeIn>
  );
}

// ── Main page ───────────────────────────────────────────────
export default function Home() {
  const { theme } = useTheme();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const isDark = theme === "dark";

  const handleWaitlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://dataweave-ai-production-8516.up.railway.app";
      const res = await fetch(`${API_URL}/api/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (res.ok) {
        setSubmitted(true);
      }
    } catch (err) {
      console.error("Waitlist error:", err);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: "var(--dw-bg-primary)", color: "var(--dw-text-primary)" }}>
      {/* ── Grain overlay (dark only) ── */}
      <div
        className="fixed inset-0 pointer-events-none z-50"
        style={{
          opacity: "var(--dw-grain-opacity)",
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />

      {/* ── Gradient blobs (dark only) ── */}
      {isDark && (
        <>
          <div className="fixed top-0 left-1/4 w-[600px] h-[600px] bg-[#E94560]/5 rounded-full blur-[150px] pointer-events-none" />
          <div className="fixed bottom-0 right-1/4 w-[500px] h-[500px] bg-[#0F3460]/10 rounded-full blur-[150px] pointer-events-none" />
        </>
      )}

      {/* ══════════════════════════════════════════════════════
          NAV
      ══════════════════════════════════════════════════════ */}
      <nav className="relative z-40 flex items-center justify-between px-6 md:px-12 lg:px-20 py-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ color: "var(--dw-text-primary)" }}>
            data<span className="text-[#E94560]">weave</span>
          </span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm" style={{ color: "var(--dw-text-secondary)" }}>
          <a href="#how-it-works" className="hover:opacity-80 transition-opacity">How it works</a>
          <a href="#agents" className="hover:opacity-80 transition-opacity">Agents</a>
          <a href="/upload" className="hover:opacity-80 transition-opacity">Upload</a>
          <ThemeToggle />
          <a
            href="#waitlist"
            className="px-4 py-2 bg-[#E94560] hover:bg-[#E94560]/80 rounded-lg text-white text-sm font-medium transition-colors"
          >
            Join Waitlist
          </a>
        </div>
      </nav>

      {/* ══════════════════════════════════════════════════════
          HERO
      ══════════════════════════════════════════════════════ */}
      <section className="relative z-10 px-6 md:px-12 lg:px-20 pt-20 pb-32">
        <div className="max-w-4xl mx-auto text-center">
          <FadeIn>
            <div
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs mb-8"
              style={{
                background: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)",
                border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`,
                color: "var(--dw-text-secondary)",
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
              5 AI agents working in sequence
            </div>
          </FadeIn>

          <FadeIn delay={100}>
            <h1 className="text-5xl md:text-7xl font-bold leading-[1.08] tracking-tight mb-6">
              Messy CSV in.
              <br />
              <span className="bg-gradient-to-r from-[#E94560] via-[#FF6B6B] to-[#E94560] bg-clip-text text-transparent">
                Clean data out.
              </span>
            </h1>
          </FadeIn>

          <FadeIn delay={200}>
            <p className="text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed" style={{ color: "var(--dw-text-secondary)" }}>
              Upload your messy spreadsheet. Our AI agents map columns, normalize formats,
              and validate every row — in under 60 seconds.
              No SDK. No integration. Just clean data.
            </p>
          </FadeIn>

          <FadeIn delay={300}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href="/upload"
                className="group px-8 py-3.5 bg-[#E94560] hover:bg-[#D63B55] rounded-xl text-white font-semibold transition-all duration-300 hover:shadow-[0_0_40px_rgba(233,69,96,0.3)]"
              >
                Try It Now
                <span className="inline-block ml-2 group-hover:translate-x-1 transition-transform">→</span>
              </a>
              <a
                href="#how-it-works"
                className="px-8 py-3.5 rounded-xl font-medium transition-all"
                style={{
                  background: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)",
                  border: `1px solid ${isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.1)"}`,
                  color: "var(--dw-text-secondary)",
                }}
              >
                See How It Works
              </a>
            </div>
          </FadeIn>

          {/* ── Terminal preview ── */}
          <FadeIn delay={450}>
            <div className="mt-16 max-w-2xl mx-auto">
              <div
                className="rounded-xl overflow-hidden"
                style={{
                  background: isDark ? "#12121A" : "#1E1E2E",
                  border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.12)"}`,
                  boxShadow: "var(--dw-shadow-lg)",
                }}
              >
                <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.08)"}` }}>
                  <div className="w-3 h-3 rounded-full bg-[#FF5F57]" />
                  <div className="w-3 h-3 rounded-full bg-[#FEBC2E]" />
                  <div className="w-3 h-3 rounded-full bg-[#28C840]" />
                  <span className="ml-3 text-xs text-white/30 font-mono">dataweave pipeline</span>
                </div>
                <div className="p-5 font-mono text-sm space-y-2.5 text-left">
                  <p>
                    <span className="text-white/30">$</span>{" "}
                    <span className="text-[#4ADE80]">POST</span>{" "}
                    <span className="text-white/70">/api/upload</span>{" "}
                    <span className="text-white/30">contacts.csv</span>
                  </p>
                  <p className="text-white/40">
                    ▸ Ingestion Agent: parsed 1,247 rows, 15 columns
                  </p>
                  <p className="text-white/40">
                    ▸ Pattern Agent: matched 10 columns{" "}
                    <span className="text-[#4ADE80]">(FREE)</span>
                  </p>
                  <p className="text-white/40">
                    ▸ Schema Agent: mapped 5 unknowns via Claude{" "}
                    <span className="text-white/25">($0.01)</span>
                  </p>
                  <p className="text-white/40">
                    ▸ Transform Agent: normalized dates, emails, phones
                  </p>
                  <p className="text-white/40">
                    ▸ Validation Agent: quality score{" "}
                    <span className="text-[#4ADE80] font-bold">89.5%</span>
                  </p>
                  <div className="pt-2 border-t border-white/[0.05]">
                    <p>
                      <span className="text-[#4ADE80]">✓</span>{" "}
                      <span className="text-white/60">
                        Pipeline complete — clean_contacts.csv ready
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </FadeIn>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          STATS BAR
      ══════════════════════════════════════════════════════ */}
      <section className="relative z-10" style={{ borderTop: "1px solid var(--dw-border)", borderBottom: "1px solid var(--dw-border)", background: isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)" }}>
        <div className="max-w-5xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
          {[
            { value: 5, suffix: "", label: "AI Agents" },
            { value: 60, suffix: "s", label: "Processing Time" },
            { value: 89, suffix: "%", label: "Quality Score" },
            { value: 1, suffix: "¢", label: "Per File Cost" },
          ].map((stat, i) => (
            <FadeIn key={i} delay={i * 100} className="text-center">
              <div className="text-3xl md:text-4xl font-bold mb-1" style={{ color: "var(--dw-text-primary)" }}>
                {stat.suffix === "¢" ? (
                  <>
                    <AnimatedNumber target={stat.value} />
                    {stat.suffix}
                  </>
                ) : stat.suffix === "s" ? (
                  <>
                    {"<"}
                    <AnimatedNumber target={stat.value} />
                    {stat.suffix}
                  </>
                ) : (
                  <>
                    <AnimatedNumber target={stat.value} />
                    {stat.suffix}
                  </>
                )}
              </div>
              <div className="text-sm" style={{ color: "var(--dw-text-tertiary)" }}>{stat.label}</div>
            </FadeIn>
          ))}
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          HOW IT WORKS
      ══════════════════════════════════════════════════════ */}
      <section id="how-it-works" className="relative z-10 px-6 md:px-12 lg:px-20 py-28">
        <div className="max-w-5xl mx-auto">
          <FadeIn>
            <p className="text-xs font-mono uppercase tracking-[0.25em] text-[#E94560] mb-3">Workflow</p>
            <h2 className="text-3xl md:text-4xl font-bold mb-16">Three steps. Zero complexity.</h2>
          </FadeIn>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                step: "01",
                title: "Upload",
                desc: "Drag and drop your CSV, Excel, or JSON file. Select your target schema (HubSpot, Salesforce, or custom).",
                icon: "↑",
              },
              {
                step: "02",
                title: "Review",
                desc: "Our AI maps every column automatically. Review the proposals — approve, reject, or correct with one click.",
                icon: "⚡",
              },
              {
                step: "03",
                title: "Export",
                desc: "Download your clean, schema-compliant data as CSV or JSON. Ready to import into your target system.",
                icon: "↓",
              },
            ].map((item, i) => (
              <FadeIn key={i} delay={i * 150}>
                <div
                  className="relative rounded-2xl p-8 transition-all duration-500 h-full"
                  style={{
                    background: "var(--dw-bg-card)",
                    border: "1px solid var(--dw-border)",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--dw-border-strong)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--dw-border)"; }}
                >
                  <div className="text-4xl mb-5 opacity-60">{item.icon}</div>
                  <div className="text-xs font-mono text-[#E94560] mb-2">STEP {item.step}</div>
                  <h3 className="text-xl font-semibold mb-3" style={{ color: "var(--dw-text-primary)" }}>{item.title}</h3>
                  <p className="text-sm leading-relaxed" style={{ color: "var(--dw-text-secondary)" }}>{item.desc}</p>
                </div>
              </FadeIn>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          THE FIVE AGENTS
      ══════════════════════════════════════════════════════ */}
      <section id="agents" className="relative z-10 px-6 md:px-12 lg:px-20 py-28" style={{ background: isDark ? "rgba(255,255,255,0.01)" : "rgba(0,0,0,0.015)" }}>
        <div className="max-w-5xl mx-auto">
          <FadeIn>
            <p className="text-xs font-mono uppercase tracking-[0.25em] text-[#E94560] mb-3">Architecture</p>
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Five agents. One pipeline.</h2>
            <p className="max-w-xl mb-14" style={{ color: "var(--dw-text-secondary)" }}>
              Each agent handles a single responsibility. Three are fully deterministic (no AI cost).
              Only the Schema Agent calls an LLM — and only for columns it hasn&apos;t seen before.
            </p>
          </FadeIn>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            <AgentCard
              number="01"
              name="Ingestion Agent"
              description="Parses CSV, Excel, JSON, and TSV. Detects encoding, sniffs delimiters, infers column types, normalizes null values."
              tag="No LLM"
              color="#4ADE80"
              delay={0}
            />
            <AgentCard
              number="02"
              name="Pattern Agent"
              description="Checks every column against a database of known mappings. Gets smarter with every correction. 67% hit rate and climbing."
              tag="No LLM"
              color="#4ADE80"
              delay={100}
            />
            <AgentCard
              number="03"
              name="Schema Agent"
              description="Sends unknown columns to Claude in a single batched call. Caches results. Blends LLM confidence with heuristic boosts."
              tag="LLM for unknowns"
              color="#FBBF24"
              delay={200}
            />
            <AgentCard
              number="04"
              name="Transform Agent"
              description="Renames columns, casts types, parses 15+ date formats to ISO 8601, normalizes emails and phone numbers."
              tag="No LLM"
              color="#4ADE80"
              delay={300}
            />
            <AgentCard
              number="05"
              name="Validation Agent"
              description="Checks required fields, type conformance, format validation, duplicates, and statistical anomalies. Produces a quality score."
              tag="No LLM"
              color="#4ADE80"
              delay={400}
            />
            <FadeIn delay={500}>
              <div className="relative bg-gradient-to-br from-[#E94560]/10 to-[#0F3460]/10 border border-[#E94560]/20 rounded-2xl p-7 h-full flex flex-col justify-center">
                <div className="text-2xl font-bold mb-2" style={{ color: "var(--dw-text-primary)" }}>3 of 5 agents</div>
                <div className="text-2xl font-bold text-[#4ADE80] mb-3">cost $0.00</div>
                <p className="text-sm" style={{ color: "var(--dw-text-secondary)" }}>
                  Only unknown columns trigger an LLM call. As patterns learn, AI costs approach zero.
                </p>
              </div>
            </FadeIn>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          BEFORE / AFTER
      ══════════════════════════════════════════════════════ */}
      <section className="relative z-10 px-6 md:px-12 lg:px-20 py-28">
        <div className="max-w-5xl mx-auto">
          <FadeIn>
            <p className="text-xs font-mono uppercase tracking-[0.25em] text-[#E94560] mb-3">Transformation</p>
            <h2 className="text-3xl md:text-4xl font-bold mb-14">See the difference.</h2>
          </FadeIn>

          <div className="grid md:grid-cols-2 gap-6">
            <FadeIn delay={0}>
              <div
                className="rounded-xl overflow-hidden"
                style={{
                  background: isDark ? "#12121A" : "#1E1E2E",
                  border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.12)"}`,
                }}
              >
                <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.08)"}` }}>
                  <span className="w-2 h-2 rounded-full bg-[#FF5F57]" />
                  <span className="text-xs font-mono text-white/30">messy_contacts.csv</span>
                </div>
                <div className="p-5 font-mono text-xs space-y-1.5 text-white/50">
                  <p><span className="text-white/25">Col A:</span> Cust Email</p>
                  <p><span className="text-white/25">Col B:</span> Signup Date</p>
                  <p><span className="text-white/25">Col C:</span> Org</p>
                  <p><span className="text-white/25">Col D:</span> State/Province</p>
                  <p><span className="text-white/25">Col E:</span> Personal Website</p>
                  <div className="pt-3 border-t border-white/[0.05] space-y-1">
                    <p className="text-[#FF6B6B]">⚠ Mixed date formats (MM/DD, DD-MM, &quot;Jan 15&quot;)</p>
                    <p className="text-[#FF6B6B]">⚠ Phones: +44-20-555, (555)010, 5550104</p>
                    <p className="text-[#FF6B6B]">⚠ Missing required fields on 3 rows</p>
                  </div>
                </div>
              </div>
            </FadeIn>

            <FadeIn delay={150}>
              <div
                className="rounded-xl overflow-hidden"
                style={{
                  background: isDark ? "#12121A" : "#1E1E2E",
                  border: "1px solid rgba(74,222,128,0.2)",
                }}
              >
                <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: "1px solid rgba(74,222,128,0.1)" }}>
                  <span className="w-2 h-2 rounded-full bg-[#4ADE80]" />
                  <span className="text-xs font-mono text-[#4ADE80]/60">clean_contacts.csv</span>
                </div>
                <div className="p-5 font-mono text-xs space-y-1.5 text-white/50">
                  <p><span className="text-[#4ADE80]/50">email:</span> john.doe@acme.com</p>
                  <p><span className="text-[#4ADE80]/50">created_at:</span> 2024-01-15</p>
                  <p><span className="text-[#4ADE80]/50">company:</span> Acme Corporation</p>
                  <p><span className="text-[#4ADE80]/50">state:</span> CA</p>
                  <p><span className="text-[#4ADE80]/50">website:</span> https://johndoe.dev</p>
                  <div className="pt-3 border-t border-[#4ADE80]/10 space-y-1">
                    <p className="text-[#4ADE80]">✓ All dates ISO 8601</p>
                    <p className="text-[#4ADE80]">✓ Phones normalized to +1XXXXXXXXXX</p>
                    <p className="text-[#4ADE80]">✓ Quality score: 89.5%</p>
                  </div>
                </div>
              </div>
            </FadeIn>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          WAITLIST
      ══════════════════════════════════════════════════════ */}
      <section id="waitlist" className="relative z-10 px-6 md:px-12 lg:px-20 py-28">
        <div className="max-w-xl mx-auto text-center">
          <FadeIn>
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Get early access.</h2>
            <p className="mb-10" style={{ color: "var(--dw-text-secondary)" }}>
              We&apos;re launching soon. Join the waitlist to be first in line.
            </p>
          </FadeIn>

          <FadeIn delay={100}>
            {submitted ? (
              <div className="rounded-xl p-6" style={{ background: "var(--dw-success-light)", border: "1px solid var(--dw-success-border)" }}>
                <div className="text-2xl mb-2">✓</div>
                <p className="font-medium" style={{ color: "var(--dw-success)" }}>You&apos;re on the list!</p>
                <p className="text-sm mt-1" style={{ color: "var(--dw-text-secondary)" }}>We&apos;ll email you when we launch.</p>
              </div>
            ) : (
              <form onSubmit={handleWaitlist} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  className="flex-1 px-5 py-3.5 rounded-xl focus:outline-none transition-colors"
                  style={{
                    background: "var(--dw-bg-input)",
                    border: "1px solid var(--dw-border-input)",
                    color: "var(--dw-text-primary)",
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = "var(--dw-border-input-focus)"; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "var(--dw-border-input)"; }}
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="px-8 py-3.5 bg-[#E94560] hover:bg-[#D63B55] disabled:opacity-60 rounded-xl text-white font-semibold transition-all whitespace-nowrap"
                >
                  {loading ? "Joining..." : "Join Waitlist"}
                </button>
              </form>
            )}
          </FadeIn>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          FOOTER
      ══════════════════════════════════════════════════════ */}
      <footer className="relative z-10 px-6 md:px-12 lg:px-20 py-10" style={{ borderTop: "1px solid var(--dw-border)" }}>
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[#E94560] to-[#E94560]/60 flex items-center justify-center">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
                <path d="M4 6h16M4 12h16M4 18h10" />
              </svg>
            </div>
            <span className="text-sm font-bold tracking-tight" style={{ color: "var(--dw-text-primary)" }}>
              data<span className="text-[#E94560]">weave</span>
            </span>
          </div>
          <div className="flex items-center gap-4">
            <p className="text-xs" style={{ color: "var(--dw-text-muted)" }}>
              © {new Date().getFullYear()} DataWeave AI. All rights reserved.
            </p>
            <span style={{ color: "var(--dw-text-muted)" }}>·</span>
            <p className="text-xs" style={{ color: "var(--dw-text-muted)" }}>
              Built with <span className="text-[#E94560]">♥</span> by{" "}
              <a
                href="https://linkedin.com/in/sam-agarwal-ai/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2 hover:opacity-80 transition-opacity"
                style={{ color: "var(--dw-text-secondary)" }}
              >
                Samyak
              </a>
            </p>
            <span style={{ color: "var(--dw-text-muted)" }}>·</span>
            <a
              href="https://github.com/sam-yak/dataweave-ai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline underline-offset-2 hover:opacity-80 transition-opacity"
              style={{ color: "var(--dw-text-secondary)" }}
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
