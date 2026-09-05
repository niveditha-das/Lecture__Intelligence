import type { Config } from "tailwindcss";

/**
 * Dark blue on light sky.
 *
 * The page is tinted and cards are left white, so a card reads as raised
 * rather than as a slightly different shade of the same thing. That inversion
 * is what stops a tinted background looking muddy.
 *
 *   cyan-slate  the page
 *   cool grey   surfaces and borders
 *   navy        headings and the wordmark
 *   blue        interactive chrome
 *
 * Headings sit at #1e3a8a — deep enough to anchor a white page at 10.5:1,
 * where the earlier cyan managed only 5.4 and read washed out.
 *
 * Token names unchanged, so no page needs editing.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        heading: "#1e3a8a",      // navy
        link: "#1d4ed8",
        muted: "#4b5563",
        faint: "#8b93a5",
        void: "#e8f4fd",         // light sky — clearly blue, still light
        card: "#ffffff",         // cards stay white, so they lift off it
        raise: "#f0f8ff",        // between page and card
        rule: "#c6dff2",
        brand: { DEFAULT: "#1d4ed8", deep: "#1e3a8a", soft: "#e6edfd" },
        teal: "#0f766e",
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
        card: "0 1px 2px rgba(15,40,70,.08), 0 10px 30px -18px rgba(15,40,70,.35)",
        glow: "0 1px 2px rgba(29,78,216,.20), 0 8px 20px -10px rgba(29,78,216,.45)",
      },
      backgroundImage: {
        hero: "linear-gradient(118deg,#d7ecfb 0%,#dceffd 55%,#d3f0fa 100%)",
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
