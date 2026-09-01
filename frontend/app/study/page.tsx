"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Course, getCourses } from "../lib/api";
import {
  AnswerResult,
  buildPlan,
  getMastery,
  getNextQuestions,
  MasteryRow,
  Plan,
  QuizQuestion,
} from "../lib/study-api";
import { QuizCard } from "../components/QuizCard";
import { MasteryPanel, PlanView } from "../components/StudyPanels";

function inDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function StudyPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");

  const [queue, setQueue] = useState<QuizQuestion[]>([]);
  const [mastery, setMastery] = useState<MasteryRow[]>([]);
  const [lastTopic, setLastTopic] = useState<string | null>(null);
  const [answered, setAnswered] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [examDate, setExamDate] = useState(inDays(14));
  const [minutes, setMinutes] = useState(60);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planning, setPlanning] = useState(false);

  useEffect(() => {
    getCourses()
      .then((cs) => {
        setCourses(cs);
        if (cs.length) setCourseId(cs[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const refresh = useCallback(async () => {
    if (!courseId) return;
    setLoading(true);
    setError(null);
    try {
      const [qs, ms] = await Promise.all([
        getNextQuestions(courseId, 5),
        getMastery(courseId),
      ]);
      setQueue(qs);
      setMastery(ms);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    void refresh();
    setPlan(null);
  }, [refresh]);

  function handleAnswered(r: AnswerResult) {
    setLastTopic(r.topic);
    setAnswered((n) => n + 1);
    // Reflect the new estimate immediately rather than waiting for a refetch.
    setMastery((rows) =>
      rows.map((row) =>
        row.topic === r.topic
          ? {
              ...row,
              theta: r.theta_after,
              n_seen: row.n_seen + 1,
              n_correct: row.n_correct + (r.correct ? 1 : 0),
            }
          : row,
      ),
    );
  }

  function nextQuestion() {
    setQueue((q) => q.slice(1));
  }

  async function makePlan() {
    if (!courseId) return;
    setPlanning(true);
    setError(null);
    try {
      const p = await buildPlan(courseId, examDate, minutes);
      if (p.error) setError(p.error);
      else setPlan(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPlanning(false);
    }
  }

  const current = queue[0];

  return (
    <main className="min-h-screen">
      <header className="border-b border-rule bg-ink text-paper">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-6 py-7">
          <div>
            <h1 className="font-display text-4xl leading-none tracking-tight">
              Study
            </h1>
            <p className="mt-2 max-w-measure text-sm text-paper/70">
              Questions drawn from your own lectures, with an ability estimate that
              updates as you answer.
            </p>
          </div>
          <nav className="flex gap-4 text-sm">
            <Link href="/" className="text-paper/70 underline hover:text-paper">
              Ask
            </Link>
            <span className="text-paper">Study</span>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center gap-4 border border-rule bg-card px-4 py-3">
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
          <span className="num text-xs text-muted">
            {answered} answered this session
          </span>
          <button
            onClick={() => void refresh()}
            className="ml-auto border border-rule px-2 py-1 text-xs text-muted hover:border-ink hover:text-ink"
          >
            Refresh queue
          </button>
        </div>

        {error && (
          <p className="mb-6 border border-marker/40 bg-marker/5 px-4 py-3 text-sm">
            {error}
          </p>
        )}

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="space-y-8">
            {loading && <p className="eyebrow animate-pulse">Loading questions</p>}

            {!loading && current && (
              <QuizCard
                key={current.question_id}
                question={current}
                onAnswered={handleAnswered}
                onNext={nextQuestion}
              />
            )}

            {!loading && !current && (
              <section className="border border-rule bg-card px-5 py-8">
                <p className="text-sm">
                  No questions left in the queue.
                </p>
                <p className="mt-2 max-w-measure text-sm text-muted">
                  Questions you have already answered correctly are excluded. Generate
                  more with <span className="num">POST /study/quiz/generate</span>, or
                  refresh to pick up newly created ones.
                </p>
              </section>
            )}

            <section className="border border-rule bg-card">
              <header className="border-b border-rule px-4 py-3">
                <p className="eyebrow">Plan revision</p>
              </header>
              <div className="flex flex-wrap items-end gap-4 px-4 py-4">
                <label className="flex flex-col gap-1">
                  <span className="eyebrow">Exam date</span>
                  <input
                    type="date"
                    value={examDate}
                    onChange={(e) => setExamDate(e.target.value)}
                    className="border border-rule bg-paper px-2 py-1 text-sm"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="eyebrow">Minutes per day</span>
                  <input
                    type="number"
                    min={20}
                    step={10}
                    value={minutes}
                    onChange={(e) => setMinutes(Number(e.target.value))}
                    className="w-24 border border-rule bg-paper px-2 py-1 text-sm"
                  />
                </label>
                <button
                  onClick={() => void makePlan()}
                  disabled={planning}
                  className="bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {planning ? "Planning…" : "Build plan"}
                </button>
              </div>
            </section>

            {plan && <PlanView plan={plan} />}
          </div>

          <aside className="lg:sticky lg:top-6 lg:self-start">
            <MasteryPanel rows={mastery} highlight={lastTopic} />
          </aside>
        </div>
      </div>
    </main>
  );
}
