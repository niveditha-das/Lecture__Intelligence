"use client";

/**
 * Exam mode.
 *
 * Practice reveals each answer immediately, which is right for learning and
 * wrong for rehearsal — you never find out whether you can hold several answers
 * in your head unaided. Here nothing is revealed until the paper is submitted,
 * and then everything is marked at once.
 */

import { useCallback, useEffect, useState } from "react";
import { API, Course, getCourses } from "../lib/api";
import { selfAssess } from "../lib/study-api";
import { Details, Header, PageIntro, TopicChip } from "../components/Shell";

type Q = {
  question_id: string;
  topic: string;
  week: number | null;
  stem: string;
  model_answer: string;
  marking_points: string[];
  difficulty: number;
};

type Paper = {
  format: string;
  n: number;
  suggested_minutes: number;
  topics: string[];
  questions: Q[];
};

export default function ExamPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [count, setCount] = useState(5);
  const [format, setFormat] = useState<"long" | "short">("long");

  const [paper, setPaper] = useState<Paper | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCourses()
      .then((cs) => {
        setCourses(cs);
        if (cs.length) setCourseId(cs[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  const start = useCallback(async () => {
    if (!courseId) return;
    setBusy(true);
    setError(null);
    setPaper(null);
    setAnswers({});
    setMarks({});
    setSubmitted(false);
    setElapsed(0);
    try {
      const res = await fetch(
        `${API}/study/exam?course_id=${courseId}&n=${count}&format=${format}`,
      );
      if (!res.ok) throw new Error(await res.text());
      const p: Paper = await res.json();
      if (!p.questions.length) {
        setError("No questions of that type for this course yet — generate some on the Study page.");
      } else {
        setPaper(p);
        setRunning(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [courseId, count, format]);

  function submit() {
    setSubmitted(true);
    setRunning(false);
  }

  async function mark(q: Q, correct: boolean) {
    setMarks((m) => ({ ...m, [q.question_id]: correct }));
    try {
      await selfAssess(q.question_id, correct);
    } catch {
      /* the mark still shows locally; mastery just won't move */
    }
  }

  const marked = paper ? paper.questions.filter((q) => q.question_id in marks) : [];
  const score = marked.filter((q) => marks[q.question_id]).length;

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <>
      <Header active="exam" />
      <PageIntro
        title="Exam mode"
        sub="A short paper from your own lectures. Nothing is revealed until you submit."
      />

      <main className="mx-auto max-w-4xl px-5 py-8 pb-16">
        {/* ---- setup ---- */}
        {!paper && (
          <section className="card p-5">
            <div className="flex flex-wrap items-end gap-4">
              {courses.length > 1 && (
                <label className="flex flex-col gap-1 text-sm text-muted">
                  Course
                  <select
                    value={courseId}
                    onChange={(e) => setCourseId(e.target.value)}
                    className="field py-1.5"
                  >
                    {courses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="flex flex-col gap-1 text-sm text-muted">
                Questions
                <select
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  className="field w-24 py-1.5"
                >
                  {[3, 5, 8, 10].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-muted">
                Type
                <select
                  value={format}
                  onChange={(e) => setFormat(e.target.value as "long" | "short")}
                  className="field py-1.5"
                >
                  <option value="long">Long answer</option>
                  <option value="short">Short answer</option>
                </select>
              </label>
              <button onClick={() => void start()} disabled={busy} className="btn">
                {busy ? "Setting the paper…" : "Start"}
              </button>
            </div>

            <Details summary="How questions are chosen">
              <p className="text-sm text-muted">
                Unlike practice, this isn&apos;t adaptive. Practice targets your current
                ability; an exam should sample the syllabus, including the parts
                you&apos;ve quietly avoided. Questions spread across topics first, then
                prefer topics you&apos;ve seen least.
              </p>
            </Details>
          </section>
        )}

        {error && (
          <p className="card mt-5 border-rose/30 bg-rose/10 px-4 py-3 text-sm">{error}</p>
        )}

        {/* ---- the paper ---- */}
        {paper && (
          <>
            <div className="card sticky top-2 z-10 mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">
                  {paper.n} questions · {paper.topics.length} topics
                </span>
                <span className="text-sm text-muted">
                  suggested {paper.suggested_minutes} min
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`font-mono text-sm ${running ? "text-teal" : "text-muted"}`}>
                  {mm}:{ss}
                </span>
                {!submitted ? (
                  <button onClick={submit} className="btn">Submit paper</button>
                ) : (
                  <span className="chip bg-brand-soft text-brand">
                    {score}/{marked.length} marked correct
                  </span>
                )}
              </div>
            </div>

            <ol className="space-y-5">
              {paper.questions.map((q, i) => (
                <li key={q.question_id} className="card p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="chip bg-brand-soft text-brand">Q{i + 1}</span>
                    <TopicChip name={q.topic} />
                    {q.week !== null && (
                      <span className="text-xs text-muted">Week {q.week}</span>
                    )}
                  </div>

                  <p className="mt-3 text-lg">{q.stem}</p>

                  <textarea
                    value={answers[q.question_id] ?? ""}
                    onChange={(e) =>
                      setAnswers((a) => ({ ...a, [q.question_id]: e.target.value }))
                    }
                    rows={paper.format === "long" ? 7 : 4}
                    disabled={submitted}
                    placeholder="Your answer…"
                    className="field mt-4 w-full resize-y disabled:opacity-70"
                  />

                  {submitted && (
                    <div className="mt-5 animate-rise rounded-lg border border-rule bg-raise p-4">
                      <p className="text-sm font-medium text-brand">Model answer</p>
                      <p className="mt-2 whitespace-pre-line">{q.model_answer}</p>

                      {q.marking_points.length > 0 && (
                        <>
                          <p className="mt-4 text-sm font-medium text-brand">
                            A marker looks for
                          </p>
                          <ul className="mt-2 space-y-1.5">
                            {q.marking_points.map((p, j) => (
                              <li key={j} className="flex gap-2 text-sm">
                                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                                <span>{p}</span>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}

                      <div className="mt-4 flex items-center gap-2 border-t border-rule pt-4">
                        {q.question_id in marks ? (
                          <span
                            className={`chip ${
                              marks[q.question_id]
                                ? "bg-teal/15 text-teal"
                                : "bg-rose/15 text-rose"
                            }`}
                          >
                            {marks[q.question_id] ? "Marked correct" : "Marked incorrect"}
                          </span>
                        ) : (
                          <>
                            <span className="text-sm text-muted">Did you cover it?</span>
                            <button onClick={() => void mark(q, true)} className="btn-soft">
                              Yes
                            </button>
                            <button onClick={() => void mark(q, false)} className="btn-quiet">
                              No
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>

            {submitted && (
              <div className="mt-6 flex justify-center">
                <button onClick={() => setPaper(null)} className="btn-quiet">
                  New paper
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </>
  );
}
