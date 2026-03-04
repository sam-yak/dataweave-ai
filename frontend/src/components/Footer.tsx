"use client";

import { useTheme } from "./ThemeProvider";

export default function Footer() {
  const { theme } = useTheme();
  const year = new Date().getFullYear();

  const isDark = theme === "dark";

  return (
    <footer
      className="relative z-10 w-full py-6 px-6 md:px-12 lg:px-20"
      style={{
        borderTop: isDark
          ? "1px solid rgba(255,255,255,0.05)"
          : "1px solid rgba(0,0,0,0.08)",
        background: isDark ? "#0A0A0F" : "#FAFAFA",
      }}
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Left: Copyright */}
        <p
          className="text-xs"
          style={{ color: isDark ? "rgba(255,255,255,0.3)" : "rgba(0,0,0,0.4)" }}
        >
          © {year} DataWeave AI. All rights reserved.
        </p>

        {/* Right: Links */}
        <div className="flex items-center gap-4">
          <a
            href="https://github.com/sam-yak/dataweave-ai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs transition-colors"
            style={{ color: isDark ? "rgba(255,255,255,0.3)" : "rgba(0,0,0,0.4)" }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.color = isDark
                ? "rgba(255,255,255,0.6)"
                : "rgba(0,0,0,0.7)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.color = isDark
                ? "rgba(255,255,255,0.3)"
                : "rgba(0,0,0,0.4)")
            }
          >
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
