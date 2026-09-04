"use client";

import Link from "next/link";
import { useState } from "react";

/* ---------------------------------------------------------------- topics --
 * A topic keeps the same colour everywhere it appears — quiz header, mastery
 * row, exam paper, plan entry. Derived from the name, so it needs no stored
 * state and survives topics being regenerated.
 */
const TOPIC_COLORS = [
  { bg: "bg-violet-500/15", text: "text-violet-300", dot: "bg-violet-400" },
  { bg: "bg-amber-500/15", text: "text-amber-300", dot: "bg-amber-400" },
  { bg: "bg-rose-500/15", text: "text-rose-300", dot: "bg-rose-400" },
  { bg: "bg-emerald-500/15", text: "text-emerald-300", dot: "bg-emerald-400" },
  { bg: "bg-fuchsia-500/15", text: "text-fuchsia-300", dot: "bg-fuchsia-400" },
  { bg: "bg-orange-500/15", text: "text-orange-300", dot: "bg-orange-400" },
  { bg: "bg-indigo-500/15", text: "text-indigo-300", dot: "bg-indigo-400" },
  { bg: "bg-pink-500/15", text: "text-pink-300", dot: "bg-pink-400" },
];

export function topicColor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return TOPIC_COLORS[h % TOPIC_COLORS.length];
}

export function TopicChip({ name }: { name: string }) {
  const c = topicColor(name);
  return (
    <span className={`chip ${c.bg} ${c.text}`}>
      <span className={`mr-1.5 h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {name}
    </span>
  );
}

/* ---------------------------------------------------------------- header -- */
export function Header({ active }: { active: "ask" | "study" | "exam" | "library" }) {
  const link = (href: string, label: string, id: string) => (
    <Link
      key={id}
      href={href}
      className={`rounded-lg px-3 py-1.5 text-sm transition ${
        active === id
          ? "bg-brand-soft font-medium text-link"
          : "text-muted hover:text-ink"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <header className="border-b border-rule bg-card/80 backdrop-blur">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-3">
        <Link href="/" className="font-display text-lg font-bold tracking-tight">
          <span className="bg-gradient-to-r from-heading to-sky-300 bg-clip-text text-transparent">
            Lecture Assistant
          </span>
        </Link>
        <nav className="flex gap-1">
          {link("/", "Ask", "ask")}
          {link("/study", "Study", "study")}
          {link("/exam", "Exam", "exam")}
          {link("/library", "Library", "library")}
        </nav>
      </div>
    </header>
  );
}

export function PageIntro({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="border-b border-rule bg-hero py-4">
      <div className="mx-auto max-w-4xl px-5">
        <h1 className="font-display text-xl font-bold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-measure text-sm text-muted">{sub}</p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- details --
 * Everything technical lives in one of these. The information stays available;
 * it just stops competing with the thing the page is for.
 */
export function Details({ summary, children }: { summary: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen(!open)}
        className="text-sm font-medium text-link underline-offset-2 hover:underline"
      >
        {open ? "Hide details" : summary}
      </button>
      {open && <div className="mt-3 animate-rise">{children}</div>}
    </div>
  );
}

export function CoursePicker({
  courses,
  value,
  onChange,
}: {
  courses: { id: string; name: string }[];
  value: string;
  onChange: (id: string) => void;
}) {
  if (courses.length <= 1) return null;
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      Course
      <select value={value} onChange={(e) => onChange(e.target.value)} className="field py-1.5 text-sm">
        {courses.map((c) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>
    </label>
  );
}

/* -------------------------------------------------------------- strength -- */
export function strengthOf(theta: number, seen: number) {
  if (seen === 0) return { label: "Not tried", bar: "bg-rule", text: "text-faint", pct: 0 };
  const pct = Math.max(5, Math.min(100, ((theta + 1.5) / 3) * 100));
  if (theta <= -0.4) return { label: "Needs work", bar: "bg-rose", text: "text-rose", pct };
  if (theta < 0.4) return { label: "Getting there", bar: "bg-amber", text: "text-amber", pct };
  return { label: "Solid", bar: "bg-teal", text: "text-teal", pct };
}

export function StrengthBar({ theta, seen }: { theta: number; seen: number }) {
  const s = strengthOf(theta, seen);
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-raise">
      <div
        className={`h-full rounded-full transition-all duration-500 ${s.bar}`}
        style={{ width: `${s.pct}%` }}
      />
    </div>
  );
}
