import type { Config } from "tailwindcss";

/**
 * Design tokens for the OptionsFlow terminal.
 * Dark graphite luxury: near-black blue-tinted base, white-alpha surfaces, a single emerald
 * interactive accent with cyan as its gradient partner, and strict call/put semantics.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic market colors — the only red/green in the system.
        call: "#34d399",
        put: "#f87171",
        // Interactive accent scale (emerald, tuned for near-black backgrounds).
        accent: {
          DEFAULT: "#10b981",
          bright: "#34d399",
          dim: "#059669",
          cyan: "#22d3ee",
        },
        // Layered background surfaces.
        base: "#05060a",
        surface: {
          1: "rgba(255,255,255,0.03)",
          2: "rgba(255,255,255,0.05)",
          3: "rgba(255,255,255,0.08)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-jbm)", "ui-monospace", "SF Mono", "Cascadia Code", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        // Panel depth: inset top highlight + soft ambient drop.
        panel: "inset 0 1px 0 rgba(255,255,255,0.04), 0 10px 30px -16px rgba(0,0,0,0.6)",
        "panel-lift": "inset 0 1px 0 rgba(255,255,255,0.06), 0 16px 40px -16px rgba(0,0,0,0.7)",
        "glow-accent": "0 0 24px -6px rgba(16,185,129,0.45)",
        "glow-cyan": "0 0 24px -6px rgba(34,211,238,0.4)",
        "glow-put": "0 0 24px -6px rgba(248,113,113,0.4)",
      },
      letterSpacing: {
        tightest: "-0.04em",
        micro: "0.1em",
      },
      borderRadius: {
        panel: "12px",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "none" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        shimmer: {
          to: { backgroundPosition: "-135% 0" },
        },
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        breathe: {
          "0%, 100%": { opacity: "0.7", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.35)" },
        },
        "drift-x": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-48px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.6s ease both",
        shimmer: "shimmer 1.4s ease infinite",
        marquee: "marquee 45s linear infinite",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        breathe: "breathe 2.8s ease-in-out infinite",
        "drift-x": "drift-x 6s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
