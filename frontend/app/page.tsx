"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ask,
  AskResponse,
  Citation,
  Course,
  getCourses,
  getHealth,
  getSources,
  Source,
} from "./lib/api";
import { CitationViewer } from "./components/CitationViewer";
import {
  AnswerBody,
  RetrievalPanel,
  VerificationPanel,
} from "./components/AnswerView";

const MODES = [
  { id: "simple", label: "Explain simply" },
  { id: "technical", label: "Technical" },
  { id: "example", label: "Worked example" },
  { id: "socratic", label: "Socratic" },
];

const SAMPLES = [
  "What is a sample space?",
  "How do you calculate the probability of two overlapping events?",
  "What is the formula for the expected value of a binomial trial?",
];

export default function Page() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [sources, setSources] = useState<Source[]>([]);
  const [health, setHealth] = useState<{ chunks: number } | null>(null);

  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("simple");
  const [week, setWeek] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [open, setOpen] = useState<Citation | null>(null);

  useEffect(() => {
    getCourses()
      .then((cs) => {
        setCourses(cs);
        if (cs.length) setCourseId(cs[0].id);
      })
      .catch((e) => setError(String(e)));
    getHealth().then(setHealth).catch(() => {});
  }, []);

  useEffect(() => {
    if (!courseId) return;
    let cancelled = false;
    getSources(courseId)
      .then((s) => !cancelled && setSources(s))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const weeks = useMemo(() => {
    const ws = new Set<number>();
    sources.forEach((s) => s.week !== null && ws.add(s.week));
    return [...ws].sort((a, b) => a - b);
  }, [sources]);

  async function submit(q?: string) {
    const text = (q ?? question).trim();
    if (!text || loading) return;
    setQuestion(text);
    setLoading(true);
    setError(null);
    setResult(null);
    setOpen(null);
    try {
      const res = await ask({
        question: text,
        course_id: courseId || undefined,
        week: week ? Number(week) : null,
        mode,
      });
      setResult(res);
      if (res.citations.length) setOpen(res.citations[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen">
      {/* ---------------------------------------------------------------- */}
      <header className="border-b border-rule bg-ink text-paper">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-6 py-7">
          <div>
            <h1 className="font-display text-4xl leading-none tracking-tight">
              Lecture Intelligence
            </h1>
            <p className="mt-2 max-w-measure text-sm text-paper/70">
              Answers drawn only from your own course material, with every
              sentence traceable to the page it came from.
            </p>
          </div>
          {health && (
            <dl className="num flex gap-6 text-xs text-paper/60">
              <div>
                <dt className="eyebrow text-paper/50">Chunks</dt>
                <dd className="mt-1 text-lg text-paper">{health.chunks}</dd>
              </div>
              <div>
                <dt className="eyebrow text-paper/50">Sources</dt>
                <dd className="mt-1 text-lg text-paper">{sources.length}</dd>
              </div>
            </dl>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* -------------------------------------------------------------- */}
        <section className="border border-rule bg-card">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-rule px-4 py-3">
            {courses.length > 1 && (
              <label className="flex items-center gap-2">
                <span className="eyebrow">Course</span>
                <select
                  value={courseId}
                  onChange={(e) => setCourseId(e.target.value)}
                  className="border border-rule bg-paper px-2 py-1 text-sm"
                >
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="flex items-center gap-2">
              <span className="eyebrow">Week</span>
              <select
                value={week}
                onChange={(e) => setWeek(e.target.value)}
                className="border border-rule bg-paper px-2 py-1 text-sm"
              >
                <option value="">All</option>
                {weeks.map((w) => (
                  <option key={w} value={w}>
                    Week {w}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-center gap-2">
              <span className="eyebrow">Mode</span>
              <div className="flex flex-wrap gap-1">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setMode(m.id)}
                    className={[
                      "border px-2 py-1 text-xs transition-colors",
                      mode === m.id
                        ? "border-ink bg-ink text-paper"
                        : "border-rule text-muted hover:border-ink hover:text-ink",
                    ].join(" ")}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 p-4 sm:flex-row">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
              }}
              rows={2}
              placeholder="Ask about anything in your lectures…"
              className="min-h-[3.5rem] flex-1 resize-y border border-rule bg-paper px-3 py-2 text-base"
            />
            <button
              onClick={() => submit()}
              disabled={loading || !question.trim()}
              className="h-fit shrink-0 bg-accent px-5 py-3 text-sm font-medium text-white transition-opacity disabled:opacity-40"
            >
              {loading ? "Thinking…" : "Ask"}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-rule px-4 py-3">
            <span className="eyebrow">Try</span>
            {SAMPLES.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                className="border border-rule px-2 py-1 text-xs text-muted hover:border-ink hover:text-ink"
              >
                {s}
              </button>
            ))}
          </div>
        </section>

        {error && (
          <p className="mt-6 border border-marker/40 bg-marker/5 px-4 py-3 text-sm">
            {error}
            <span className="mt-1 block text-muted">
              Check the API is running on port 8000.
            </span>
          </p>
        )}

        {/* -------------------------------------------------------------- */}
        {result && (
          <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_26rem]">
            <div className="space-y-8">
              <section>
                {result.refused && (
                  <p className="eyebrow mb-3 inline-block border border-rule px-2 py-1 text-ink">
                    Not in your material
                  </p>
                )}
                <AnswerBody
                  answer={result.answer}
                  citations={result.citations}
                  activeN={open?.n ?? null}
                  onPick={setOpen}
                />
              </section>

              {result.verification && <VerificationPanel result={result} />}
            </div>

            <aside className="space-y-6 lg:sticky lg:top-6 lg:self-start">
              {open ? (
                <CitationViewer citation={open} />
              ) : (
                result.citations.length === 0 && (
                  <p className="border border-rule bg-card px-4 py-6 text-sm text-muted">
                    No citations — the system found nothing in your material that
                    answers this.
                  </p>
                )
              )}
              <RetrievalPanel result={result} />
            </aside>
          </div>
        )}

        {!result && !loading && (
          <p className="mt-10 max-w-measure text-sm text-muted">
            Click a numbered marker in any answer to see the exact region of the
            slide it came from.
          </p>
        )}
      </div>
    </main>
  );
}
