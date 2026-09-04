import type { Config } from "tailwindcss";

/**
 * Cyan on slate.
 *
 *   slate   the page and every surface — cards, fields, controls
 *   cyan    headings and the wordmark
 *   blue    interactive chrome: buttons, links, the active tab
 *
 * Cooler and more technical than the green version, which suits a corpus that
 * is mostly operating systems. Cyan is bright enough to carry headings on a
 * dark slate without needing a second accent to prop it up.
 *
 * Unchanged from every other theme: rose → amber → emerald is the mastery
 * scale, and orange marks the cited region on a slide. Token names are the
 * same, so no page needs editing.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#e2e8f2",
        heading: "#22d3ee",      // cyan: headings and wordmark
        link: "#7dd3fc",
        muted: "#94a3b8",
        faint: "#64748b",
        void: "#080c14",         // slate-black page
        card: "#111826",         // slate panels
        raise: "#1a2233",
        rule: "#26314a",
        brand: { DEFAULT: "#38bdf8", deep: "#0284c7", soft: "#12283f" },
        teal: "#34d399",         // "Solid" / "Correct" — status, not styling
        amber: "#fbbf24",
        rose: "#fb7185",
        highlight: "#fb923c",
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
        card: "0 1px 0 rgba(255,255,255,.05) inset, 0 14px 36px -22px rgba(0,0,0,.95)",
        glow: "0 0 0 1px rgba(56,189,248,.26), 0 10px 26px -12px rgba(2,132,199,.5)",
      },
      backgroundImage: {
        hero: "linear-gradient(118deg,#0d1626 0%,#122438 55%,#0f2a38 100%)",
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
