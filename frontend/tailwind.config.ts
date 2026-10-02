import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#07090d", 1: "#0b0f15", 2: "#10161f", 3: "#16202c" },
        line: { DEFAULT: "#1c2633", strong: "#2a3a4d" },
        fg: { DEFAULT: "#e6edf5", muted: "#8a98aa", faint: "#5b6878" },
        accent: { DEFAULT: "#22d3ee", blue: "#3b82f6", dim: "#0e7490" },
        sev: {
          critical: "#f43f5e",
          high: "#fb923c",
          medium: "#facc15",
          low: "#60a5fa",
          info: "#94a3b8",
        },
        ok: "#34d399",
      },
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', "Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ['"Cascadia Mono"', '"JetBrains Mono"', "Consolas", "ui-monospace", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", "1rem"] },
      boxShadow: { glow: "0 0 0 1px rgba(34,211,238,.25), 0 0 24px -8px rgba(34,211,238,.35)" },
      keyframes: {
        slidein: { from: { transform: "translateX(16px)", opacity: "0" }, to: { transform: "none", opacity: "1" } },
        sweep: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
      },
      animation: { slidein: "slidein .18s ease-out", sweep: "sweep 2.2s linear infinite" },
    },
  },
  plugins: [],
};

export default config;
