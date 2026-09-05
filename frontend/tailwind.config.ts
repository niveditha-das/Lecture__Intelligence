import type { Config } from "tailwindcss";

/**
 * Cyan on white.
 *
 * Note on the heading colour: the dark theme used #22d3ee, which is 1.7:1 on
 * white — invisible. The hue is kept and the lightness dropped to #0e7490,
 * which reads as the same cyan and clears 5.5:1. Bright accent colours almost
 * never survive a theme inversion unchanged.
 *
 *   white   the page
 *   slate   surfaces and borders
 *   cyan    headings and the wordmark
 *   blue    interactive chrome
 *
 * Token names are unchanged, so no page needs editing.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        heading: "#0e7490",      // cyan, darkened for a light background
        link: "#0369a1",
        muted: "#4a5768",
        faint: "#8f9bad",
        void: "#ffffff",         // white page
        card: "#ffffff",
        raise: "#f1f5f9",        // fields, model answers
        rule: "#e2e8f0",
        brand: { DEFAULT: "#0284c7", deep: "#0369a1", soft: "#e0f2fe" },
        teal: "#059669",         // "Solid" / "Correct"
        amber: "#b45309",
        rose: "#be123c",
        highlight: "#ea580c",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        base: ["1.0625rem", { lineHeight: "1.65" }],
        lg: ["1.1875rem", { lineHeight: "1.6" }],
      },
      maxWidth: { measure: "42rem" },
      boxShadow: {
        card: "0 1px 2px rgba(15,23,42,.05), 0 8px 24px -16px rgba(15,23,42,.18)",
        glow: "0 1px 2px rgba(2,132,199,.18), 0 8px 20px -10px rgba(2,132,199,.40)",
      },
      backgroundImage: {
        hero: "linear-gradient(118deg,#ecfeff 0%,#e0f2fe 55%,#eef7ff 100%)",
      },
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
      },
      animation: { rise: "rise .28s ease-out both" },
    },
  },
  plugins: [],
};

export default config;
