"use client";

import { useCallback, useEffect, useState } from "react";
import { Course, getCourses } from "../lib/api";
import {
  answerQuestion,
  AnswerResult,
  buildPlan,
  Counts,
  generateMcq,
  generateWritten,
  getCounts,
  getMastery,
  getNextQuestions,
  getWritten,
  MasteryRow,
  Plan,
  QuizQuestion,
  selfAssess,
  WrittenQuestion,
} from "../lib/study-api";
import {
  CoursePicker,
  Details,
  Header,
  PageIntro,
  strengthOf,
  StrengthBar,
  TopicChip,
} from "../components/Shell";

type Format = "mcq" | "short" | "long";

const FORMATS: { id: Format; label: string; blurb: string }[] = [
  { id: "mcq", label: "Quiz", blurb: "Multiple choice, marked instantly" },
  { id: "short", label: "Short answer", blurb: "Write 2–4 sentences, then mark yourself" },
  { id: "long", label: "Long answer", blurb: "Exam-style, connects several ideas" },
];

function inDays(n: number) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function StudyPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [format, setFormat] = useState<Format>("mcq");
  const [counts, setCounts] = useState<Counts | null>(null);

  const [mcq, setMcq] = useState<QuizQuestion[]>([]);
  const [written, setWritten] = useState<WrittenQuestion[]>([]);
  const [mastery, setMastery] = useState<MasteryRow[]>([]);

  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<Format | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState({ n: 0, right: 0 });

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
      const [c, ms, qs, sh] = await Promise.all([
        getCounts(courseId),
        getMastery(courseId),
        getNextQuestions(courseId, 5),
        getWritten(courseId, format === "long" ? "long" : "short", 3),
      ]);
      setCounts(c);
      setMastery(ms);
      setMcq(qs);
      setWritten(sh);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [courseId, format]);

  useEffect(() => {
    void refresh();
    setPlan(null);
  }, [refresh]);

  function applyResult(r: AnswerResult) {
    setDone((d) => ({ n: d.n + 1, right: d.right + (r.correct ? 1 : 0) }));
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

  async function generate(f: Format) {
    if (!courseId || generating) return;
    setGenerating(f);
    setNote(null);
    setError(null);
    try {
      const res =
        f === "mcq"
          ? await generateMcq(courseId)
          : await generateWritten(courseId, f);
      setNote(
        `Made ${res.questions_created} new question${res.questions_created === 1 ? "" : "s"} across ${res.topics_processed} topics.`,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(null);
    }
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

  const currentMcq = mcq[0];
  const currentWritten = written[0];
  const weakest = [...mastery].sort((a, b) => a.theta - b.theta).slice(0, 5);
  const have = counts ? counts[format] : 0;

  return (
    <>
      <Header active="study" />
      <PageIntro
        title="Study"
        sub="Questions written from your own lectures. Answer a few and the plan below reorders itself around what you're weakest on."
      />

      <main className="mx-auto max-w-5xl px-5 py-8 pb-16">
        {/* ---- make questions ---- */}
        <section className="card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold">Make questions</h2>
            <CoursePicker courses={courses} value={courseId} onChange={setCourseId} />
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {FORMATS.map((f) => (
              <div key={f.id} className="rounded-lg border border-rule p-4">
                <p className="font-medium">{f.label}</p>
                <p className="mt-1 text-sm text-muted">{f.blurb}</p>
                <p className="mt-2 text-sm text-brand">
                  {counts ? `${counts[f.id]} ready` : "…"}
                </p>
                <button
                  onClick={() => void generate(f.id)}
                  disabled={!!generating || !counts?.topics}
                  className="btn-soft mt-3 w-full justify-center"
                >
                  {generating === f.id ? "Writing…" : "Generate more"}
                </button>
              </div>
            ))}
          </div>

          {counts?.topics === 0 && (
            <p className="mt-3 text-sm text-amber">
              This course has no topics yet, so there&apos;s nothing to write questions
              from. Run topic extraction first.
            </p>
          )}
          {note && <p className="mt-3 text-sm text-teal">{note}</p>}
          {generating && (
            <p className="mt-2 text-sm text-muted">
              This takes a minute — questions are written one topic at a time.
            </p>
          )}
        </section>

        {error && (
          <p className="card mt-6 border-rose/30 bg-rose/10 px-4 py-3 text-sm">{error}</p>
        )}

        {/* ---- practise ---- */}
        <section className="mt-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex rounded-lg border border-rule bg-white p-1">
              {FORMATS.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setFormat(f.id)}
                  className={`rounded-md px-3 py-1.5 text-sm transition ${
                    format === f.id ? "bg-brand text-white" : "text-muted hover:text-ink"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            {done.n > 0 && (
              <span className="text-sm text-muted">
                {done.right} of {done.n} right this session
              </span>
            )}
          </div>

          <div className="mt-4">
            {loading && <p className="text-sm text-muted">Loading…</p>}

            {!loading && format === "mcq" && currentMcq && (
              <McqCard
                key={currentMcq.question_id}
                q={currentMcq}
                onDone={applyResult}
                onNext={() => setMcq((v) => v.slice(1))}
              />
            )}

            {!loading && format !== "mcq" && currentWritten && (
              <WrittenCard
                key={currentWritten.question_id}
                q={currentWritten}
                long={format === "long"}
                onDone={applyResult}
                onNext={() => setWritten((v) => v.slice(1))}
              />
            )}

            {!loading &&
              ((format === "mcq" && !currentMcq) ||
                (format !== "mcq" && !currentWritten)) && (
                <div className="card px-5 py-8 text-center">
                  <p className="font-medium">
                    {have === 0 ? "No questions of this type yet." : "You're through this batch."}
                  </p>
                  <p className="mx-auto mt-2 max-w-measure text-sm text-muted">
                    {have === 0
                      ? "Use “Generate more” above to write some from your lectures."
                      : "Questions you got right won't come back. Generate more or switch type."}
                  </p>
                </div>
              )}
          </div>
        </section>

        {/* ---- what to work on ---- */}
        {weakest.length > 0 && (
          <section className="mt-10">
            <h2 className="font-display text-lg font-semibold">What to work on</h2>
            <ul className="mt-3 space-y-2">
              {weakest.map((r) => {
                const s = strengthOf(r.theta, r.n_seen);
                return (
                  <li key={r.topic_id} className="card px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <TopicChip name={r.topic} />
                      <span className={`text-sm font-medium ${s.text}`}>{s.label}</span>
                    </div>
                    <div className="mt-2.5">
                      <StrengthBar theta={r.theta} seen={r.n_seen} />
                    </div>
                  </li>
                );
              })}
            </ul>

            <Details summary="See every topic">
              <ul className="space-y-2 text-sm">
                {mastery.map((r) => (
                  <li key={r.topic_id} className="flex items-center justify-between gap-3">
                    <span className="truncate text-muted">{r.topic}</span>
                    <span className="shrink-0 font-mono text-xs text-muted">
                      {r.n_seen === 0
                        ? "—"
                        : `${r.theta >= 0 ? "+" : ""}${r.theta.toFixed(2)} · ${r.n_correct}/${r.n_seen}`}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-sm text-muted">
                Each topic has one skill score. It rises when you answer correctly and
                falls when you don&apos;t, moving further when the result was surprising.
                Untested topics have no score rather than a zero.
              </p>
            </Details>
          </section>
        )}

        {/* ---- plan ---- */}
        <section className="mt-10">
          <h2 className="font-display text-lg font-semibold">Revision plan</h2>
          <div className="card mt-3 flex flex-wrap items-end gap-4 p-4">
            <label className="flex flex-col gap-1 text-sm text-muted">
              Exam date
              <input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} className="field py-1.5" />
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted">
              Minutes a day
              <input
                type="number"
                min={20}
                step={10}
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
                className="field w-24 py-1.5"
              />
            </label>
            <button onClick={() => void makePlan()} disabled={planning} className="btn">
              {planning ? "Planning…" : "Build plan"}
            </button>
          </div>

          {plan && <PlanView plan={plan} />}
        </section>
      </main>
    </>
  );
}

/* ------------------------------------------------------------------ MCQ -- */
function McqCard({
  q,
  onDone,
  onNext,
}: {
  q: QuizQuestion;
  onDone: (r: AnswerResult) => void;
  onNext: () => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [t0] = useState(() => Date.now());

  async function submit(key: string) {
    if (result || busy) return;
    setBusy(true);
    setChosen(key);
    try {
      const r = await answerQuestion(q.question_id, key, Date.now() - t0);
      setResult(r);
      onDone(r);
    } catch {
      setChosen(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card animate-rise p-5">
      <TopicChip name={q.topic} />
      <p className="mt-3 text-lg">{q.stem}</p>

      <ul className="mt-5 space-y-2">
        {Object.entries(q.options).map(([key, text]) => {
          const isAnswer = result && key === result.answer;
          const wrong = result && chosen === key && !result.correct;
          let tone = "border-rule hover:border-brand hover:bg-brand-soft/60";
          if (isAnswer) tone = "border-teal/60 bg-teal/10";
          else if (wrong) tone = "border-rose-400 bg-rose/10";
          else if (result) tone = "border-rule opacity-50";
          return (
            <li key={key}>
              <button
                onClick={() => submit(key)}
                disabled={!!result || busy}
                className={`w-full rounded-lg border px-4 py-3 text-left transition ${tone}`}
              >
                {text}
              </button>
            </li>
          );
        })}
      </ul>

      {result && <Outcome result={result} rationale={result.rationale} onNext={onNext} />}
    </div>
  );
}

/* -------------------------------------------------------------- written -- */
function WrittenCard({
  q,
  long,
  onDone,
  onNext,
}: {
  q: WrittenQuestion;
  long: boolean;
  onDone: (r: AnswerResult) => void;
  onNext: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function mark(correct: boolean) {
    if (result || busy) return;
    setBusy(true);
    try {
      const r = await selfAssess(q.question_id, correct);
      setResult(r);
      onDone(r);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card animate-rise p-5">
      <div className="flex flex-wrap items-center gap-2">
        <TopicChip name={q.topic} />
        <span className="chip bg-brand-soft text-brand">
          {long ? "Long answer" : "Short answer"}
        </span>
      </div>

      <p className="mt-3 text-lg">{q.stem}</p>

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={long ? 8 : 4}
        placeholder="Write your answer here — it stays on your machine."
        className="field mt-4 w-full resize-y"
      />

      {!revealed && (
        <button onClick={() => setRevealed(true)} className="btn mt-3">
          Show model answer
        </button>
      )}

      {revealed && (
        <div className="mt-5 animate-rise rounded-lg border border-rule bg-raise p-4">
          <p className="text-sm font-medium text-brand">Model answer</p>
          <p className="mt-2 whitespace-pre-line">{q.model_answer}</p>

          {q.marking_points.length > 0 && (
            <>
              <p className="mt-4 text-sm font-medium text-brand">
                A marker looks for
              </p>
              <ul className="mt-2 space-y-1.5">
                {q.marking_points.map((p, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {!result && (
            <div className="mt-5 border-t border-rule pt-4">
              <p className="text-sm text-muted">Did you cover the main points?</p>
              <div className="mt-2 flex gap-2">
                <button onClick={() => void mark(true)} disabled={busy} className="btn-soft">
                  Yes, mostly
                </button>
                <button onClick={() => void mark(false)} disabled={busy} className="btn-quiet">
                  Not really
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {result && <Outcome result={result} rationale={null} onNext={onNext} />}
    </div>
  );
}

/* -------------------------------------------------------------- outcome -- */
function Outcome({
  result,
  rationale,
  onNext,
}: {
  result: AnswerResult;
  rationale: string | null;
  onNext: () => void;
}) {
  const up = result.theta_after > result.theta_before;
  return (
    <div className="mt-5 border-t border-rule pt-4">
      <span className={`chip ${result.correct ? "bg-teal/15 text-teal" : "bg-rose/15 text-rose"}`}>
        {result.correct ? "Correct" : "Not quite"}
      </span>
      {rationale && <p className="mt-3 text-muted">{rationale}</p>}

      <p className="mt-3 text-sm text-muted">
        Your score on <span className="text-ink">{result.topic}</span>{" "}
        {up ? "went up" : "went down"}.
      </p>

      <Details summary="Show the numbers">
        <p className="text-sm text-muted">
          Skill score {result.theta_before.toFixed(2)} →{" "}
          <span className={up ? "text-teal" : "text-rose"}>
            {result.theta_after.toFixed(2)}
          </span>
          . The model expected you to get this right{" "}
          {(result.predicted_p * 100).toFixed(0)}% of the time, so the result moved it
          by {Math.abs(result.theta_after - result.theta_before).toFixed(2)}.
        </p>
      </Details>

      <button onClick={onNext} className="btn mt-4">
        Next question
      </button>
    </div>
  );
}

/* ----------------------------------------------------------------- plan -- */
const ACTIVITY_STYLE: Record<string, string> = {
  review: "bg-sky-500/15 text-sky-300",
  quiz: "bg-violet-500/15 text-violet-300",
  practice: "bg-emerald-500/15 text-emerald-300",
};

function PlanView({ plan }: { plan: Plan }) {
  const byDay = plan.items.reduce<Record<string, typeof plan.items>>((acc, it) => {
    (acc[it.day] ??= []).push(it);
    return acc;
  }, {});
  const days = Object.keys(byDay).sort();
  const focus = plan.ranking.slice(0, 3).map((r) => r.topic);

  return (
    <div className="mt-5 animate-rise">
      <div className="card bg-brand-soft/60 p-4">
        <p>
          <span className="font-medium">{plan.days} days</span> until your exam,{" "}
          <span className="font-medium">{plan.minutes_per_day} minutes</span> a day.
          Start with {focus.join(", ")}.
        </p>
      </div>

      <ol className="mt-4 space-y-3">
        {days.map((day, i) => (
          <li key={day} className="card p-4">
            <div className="flex items-baseline gap-3">
              <span className="chip bg-brand text-white">Day {i + 1}</span>
              <span className="text-sm text-muted">
                {new Date(day).toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "short",
                })}
              </span>
            </div>
            <ul className="mt-3 space-y-2">
              {byDay[day].map((it, j) => (
                <li key={j} className="flex flex-wrap items-center gap-2">
                  <span className={`chip ${ACTIVITY_STYLE[it.activity] ?? "bg-raise text-muted"}`}>
                    {it.activity === "review" ? "Read through" : "Test yourself"}
                  </span>
                  <span>{it.topic}</span>
                  <span className="text-sm text-muted">{it.minutes} min</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>

      <Details summary="Why this order">
        <ul className="space-y-1.5 text-sm">
          {plan.ranking.slice(0, 10).map((r) => (
            <li key={r.topic} className="flex justify-between gap-3">
              <span className="truncate text-muted">{r.topic}</span>
              <span className="shrink-0 font-mono text-xs text-brand">
                {r.urgency.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-muted">
          Topics are ranked by how much you&apos;re likely to have forgotten by the exam,
          weighted by how weak you are on them. Worked out in code rather than asked of
          a model, so the order can be explained and redone.
        </p>
      </Details>
    </div>
  );
}
