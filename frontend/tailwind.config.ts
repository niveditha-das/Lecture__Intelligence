import type { Config } from "tailwindcss";

/**
 * Design tokens.
 *
 * The subject is evidence: every sentence traceable to a region of a real page.
 * So the palette is a document palette — ink on a cool paper stock — with
 * exactly one loud colour, `marker`, reserved for the thing that matters:
 * the highlighted region on a cited page. It appears nowhere else.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17171c",
        paper: "#f2f1ec",
        card: "#ffffff",
        rule: "#dcdbd3",
        muted: "#6e6e66",
        accent: "#0f5257",
        marker: "#ff4d00",
        verdict: {
          supported: "#1f7a4d",
          partial: "#a86a08",
          uncited: "#6e6e66",
          unknown: "#8a8a80",
        },
      },
      fontFamily: {
        display: ["'Instrument Serif'", "Georgia", "serif"],
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      maxWidth: { measure: "68ch" },
    },
  },
  plugins: [],
};

export default config;
