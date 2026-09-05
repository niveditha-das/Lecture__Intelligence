"use client";

/**
 * Ask, in three columns.
 *
 * Left: what's indexed. Middle: the question and the answer. Right: the slide a
 * citation points at.
 *
 * Putting the source beside the answer rather than below it is the point of the
 * change — the whole claim of this project is that every sentence is checkable,
 * and that's far more convincing when the sentence and its evidence are on
 * screen together. Below 1024px the columns stack and the source returns to
 * sitting under the answer.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ask,
  AskResponse,
  Citation,
  Course,
  getCourses,
  getSources,
  Source,
} from "./lib/api";
import { SourceView } from "./components/SourceView";
import { Sidebar } from "./components/Sidebar";
import { Details, Header, PageIntro } from "./components/Shell";

const MODES = [
  { id: "simple", label: "Simple" },
  { id: "technical", label: "Technical" },
  { id: "example", label: "Worked example" },
  { id: "socratic", label: "Socratic" },
];

const STARTERS = [
  "What is a deadlock?",
  "How does round robin scheduling work?",
  "Explain semaphores",
];

export default function AskPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [sources, setSources] = useState<Source[]>([]);

  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("simple");
  const [week, setWeek] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [open, setOpen] = useState<Citation | null>(null);
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    getCourses()
      .then(async (cs) => {
        setCourses(cs);
        if (!cs.length) return;
        // Open on the course with the most indexed material rather than
        // whichever happened to be created first — an empty-looking app on
        // first load reads as broken.
        const sizes = await Promise.all(
          cs.map(async (c) => {
            try {
              const ss = await getSources(c.id);
              return ss.reduce(
                (n, x) =>
                  n + (((x as unknown as { meta?: { n_chunks?: number } }).meta?.n_chunks) ?? 0),
                0,
              );
            } catch {
              return 0;
            }
          }),
        );
        const best = sizes.indexOf(Math.max(...sizes));
        setCourseId(cs[best >= 0 ? best : 0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!courseId) {
      setSources([]);
      return;
    }
    let cancelled = false;
    getSources(courseId).then((s) => !cancelled && setSources(s)).catch(() => {});
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
      setRecent((r) => [text, ...r.filter((x) => x !== text)].slice(0, 8));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header active="ask" />
      <PageIntro
        title="Ask your lectures"
        sub="Answers come only from material you've uploaded."
      />

      <div className="mx-auto flex max-w-[92rem] gap-8 px-5 py-8 pb-16">
        <Sidebar
          courses={courses}
          courseId={courseId}
          sources={sources}
          onSelectCourse={setCourseId}
          recent={recent}
          onPickRecent={(q) => void submit(q)}
        />

        {/* ---- middle: question and answer ---- */}
        <main className="min-w-0 flex-1">
          <div className="card p-4">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
              }}
              rows={2}
              placeholder="What is a deadlock?"
              className="field w-full resize-y text-lg"
            />

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                onClick={() => void submit()}
                disabled={loading || !question.trim()}
                className="btn"
              >
                {loading ? "Thinking…" : "Ask"}
              </button>

              {/* Course lives in the rail on wide screens; keep a picker here
                  for narrow ones, where the rail is hidden. */}
              {courses.length > 1 && (
                <label className="flex items-center gap-2 text-sm text-muted lg:hidden">
                  Course
                  <select
                    value={courseId}
                    onChange={(e) => setCourseId(e.target.value)}
                    className="field py-1.5 text-sm"
                  >
                    {courses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </label>
              )}

              {weeks.length > 0 && (
                <label className="flex items-center gap-2 text-sm text-muted">
                  Week
                  <select
                    value={week}
                    onChange={(e) => setWeek(e.target.value)}
                    className="field py-1.5 text-sm"
                  >
                    <option value="">Any</option>
                    {weeks.map((w) => (
                      <option key={w} value={w}>{w}</option>
                    ))}
                  </select>
                </label>
              )}

              <label className="flex items-center gap-2 text-sm text-muted">
                Style
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="field py-1.5 text-sm"
                >
                  {MODES.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {error && (
            <p className="card mt-5 border-rose/30 px-4 py-3 text-sm">
              {error}
              <span className="mt-1 block text-muted">
                Check the backend is running on port 8000.
              </span>
            </p>
          )}

          {!result && !loading && (
            <div className="mt-6">
              <p className="text-sm text-muted">Try one of these</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {STARTERS.map((s) => (
                  <button key={s} onClick={() => void submit(s)} className="btn-quiet">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {result && (
            <div className="mt-7 animate-rise">
              {result.refused && (
                <p className="card mb-4 border-amber/40 px-4 py-3">
                  That isn&apos;t covered in the material you&apos;ve uploaded.
                </p>
              )}

              <Answer result={result} activeN={open?.n ?? null} onPick={setOpen} />

              {/* On narrow screens the right column is gone, so the source
                  falls back to sitting under the answer. */}
              {open && (
                <div className="mt-5 xl:hidden">
                  <SourceView citation={open} />
                </div>
              )}

              <GroundingNote result={result} />
            </div>
          )}
        </main>

        {/* ---- right: the cited slide ---- */}
        <div className="hidden w-[22rem] shrink-0 xl:block">
          <div className="sticky top-6">
            {open ? (
              <SourceView citation={open} />
            ) : !result ? (
              <div className="card p-4">
                <p className="text-sm font-medium">How this works</p>
                <ol className="mt-3 space-y-2.5 text-sm text-muted">
                  <li>1. Ask anything covered by your slides.</li>
                  <li>2. Every sentence gets a numbered citation.</li>
                  <li>3. Tap a number — the slide appears here with the exact
                      region boxed.</li>
                  <li>4. A second model checks each sentence against the slides
                      it cites.</li>
                </ol>
              </div>
            ) : (
              result && (
                <p className="card px-4 py-6 text-sm text-muted">
                  {result.citations.length
                    ? "Tap a number in the answer to see the slide it came from."
                    : "No citations — nothing in your material answers this."}
                </p>
              )
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Answer({
  result,
  activeN,
  onPick,
}: {
  result: AskResponse;
  activeN: number | null;
  onPick: (c: Citation) => void;
}) {
  const byN = new Map(result.citations.map((c) => [c.n, c]));
  return (
    <div className="max-w-measure space-y-4 text-lg">
      {result.answer.split(/\n{2,}/).map((para, pi) => (
        <p key={pi}>
          {para.split(/(\[\d+\])/g).map((part, i) => {
            const m = /^\[(\d+)\]$/.exec(part);
            const cite = m ? byN.get(Number(m[1])) : undefined;
            if (!cite) return <span key={i}>{part}</span>;
            return (
              <button
                key={i}
                onClick={() => onPick(cite)}
                title={`Show ${cite.label}`}
                className={`mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md align-super text-xs font-semibold transition ${
                  activeN === cite.n
                    ? "bg-highlight text-white"
                    : "bg-brand-soft text-brand-deep hover:bg-brand hover:text-white"
                }`}
              >
                {cite.n}
              </button>
            );
          })}
        </p>
      ))}
    </div>
  );
}

function GroundingNote({ result }: { result: AskResponse }) {
  const v = result.verification;
  if (!v) return null;

  const unsupported = v.sentences.filter(
    (s) => s.verdict === "PARTIAL" || s.verdict === "UNSUPPORTED",
  ).length;
  const ok = unsupported === 0;

  return (
    <div className="mt-8 border-t border-rule pt-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`chip ${ok ? "bg-teal/10 text-teal" : "bg-rose/10 text-rose"}`}>
          {ok ? "Checked" : "Check this one"}
        </span>
        <p className="text-sm text-muted">
          {ok
            ? `All ${v.n_checked} sentences match your slides.`
            : `${unsupported} sentence${unsupported === 1 ? "" : "s"} isn't fully backed by your slides.`}
        </p>
      </div>

      <Details summary="How this was checked">
        <ul className="space-y-3">
          {v.sentences.map((s, i) => (
            <li key={i} className="text-sm">
              <span
                className={`chip mr-2 ${
                  s.verdict === "SUPPORTED"
                    ? "bg-teal/10 text-teal"
                    : s.verdict === "UNCITED"
                      ? "bg-raise text-muted"
                      : "bg-rose/10 text-rose"
                }`}
              >
                {s.verdict === "SUPPORTED"
                  ? "Backed up"
                  : s.verdict === "UNCITED"
                    ? "Added context"
                    : s.verdict === "UNKNOWN"
                      ? "Not checked"
                      : "Partly backed"}
              </span>
              <span className="text-muted">{s.sentence}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-muted">
          Every sentence is checked against the slides it cites, in one call to a
          second model that never sees the answer&apos;s reasoning.
        </p>
      </Details>

      <Details summary="Where this came from">
        <ul className="space-y-2 text-sm">
          {result.hits.map((h) => (
            <li key={h.chunk_id} className="flex gap-3">
              <span className="font-mono text-xs text-link">
                {h.rerank_score !== null ? h.rerank_score.toFixed(1) : h.rrf.toFixed(3)}
              </span>
              <span className="text-muted">{h.label}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-muted">
          Slides are found by meaning and by keyword, the two lists merged, then
          re-scored for how well each actually answers the question.
        </p>
      </Details>
    </div>
  );
}
