"use client";

/**
 * The quiz card.
 *
 * The point of interest is what happens *after* an answer: the card shows the
 * ability estimate moving, and what the model had predicted beforehand. A quiz
 * that only says "correct" hides the fact that there is a model underneath.
 * Showing theta before and after makes the Elo update legible — you can watch
 * a wrong answer on an easy question cost more than a wrong answer on a hard one.
 */

import { useState } from "react";
import { answerQuestion, AnswerResult, QuizQuestion, thetaFraction } from "../lib/study-api";

export function QuizCard({
  question,
  onAnswered,
  onNext,
}: {
  question: QuizQuestion;
  onAnswered: (r: AnswerResult) => void;
  onNext: () => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [startedAt] = useState(() => Date.now());

  async function submit(key: string) {
    if (result || busy) return;
    setBusy(true);
    setChosen(key);
    try {
      const r = await answerQuestion(question.question_id, key, Date.now() - startedAt);
      setResult(r);
      onAnswered(r);
    } catch {
      setChosen(null);
    } finally {
      setBusy(false);
    }
  }

  const entries = Object.entries(question.options);

  return (
    <section className="border border-rule bg-card">
      <header className="flex items-baseline justify-between border-b border-rule px-4 py-3">
        <p className="eyebrow">{question.topic}</p>
        <p className="num text-xs text-muted">
          difficulty {question.difficulty >= 0 ? "+" : ""}
          {question.difficulty.toFixed(1)}
        </p>
      </header>

      <div className="px-5 py-5">
        <p className="max-w-measure text-[1.0625rem] leading-relaxed">{question.stem}</p>

        <ul className="mt-5 space-y-2">
          {entries.map(([key, text]) => {
            const isChosen = chosen === key;
            const isAnswer = result && key === result.answer;
            const wrongPick = result && isChosen && !result.correct;

            let tone = "border-rule hover:border-ink";
            if (isAnswer) tone = "border-verdict-supported bg-verdict-supported/5";
            else if (wrongPick) tone = "border-marker bg-marker/5";
            else if (result) tone = "border-rule opacity-50";

            return (
              <li key={key}>
                <button
                  onClick={() => submit(key)}
                  disabled={!!result || busy}
                  className={`flex w-full items-start gap-3 border px-3 py-2.5 text-left text-sm transition-colors ${tone}`}
                >
                  <span className="num shrink-0 text-xs text-muted">{key}</span>
                  <span>{text}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {result && (
        <div className="border-t border-rule bg-paper px-5 py-4">
          <p className={`eyebrow ${result.correct ? "text-verdict-supported" : "text-marker"}`}>
            {result.correct ? "Correct" : `Not quite — the answer is ${result.answer}`}
          </p>
          {result.rationale && (
            <p className="mt-2 max-w-measure text-sm leading-relaxed">{result.rationale}</p>
          )}

          <ThetaShift result={result} />

          <p className="num mt-3 text-xs text-muted">
            grounded in chunk{result.grounding_chunk_ids.length === 1 ? "" : "s"}{" "}
            {result.grounding_chunk_ids.join(", ")}
          </p>

          <button
            onClick={onNext}
            className="mt-4 bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            Next question
          </button>
        </div>
      )}
    </section>
  );
}

/** Shows the ability estimate moving, with the model's prior prediction. */
function ThetaShift({ result }: { result: AnswerResult }) {
  const before = thetaFraction(result.theta_before);
  const after = thetaFraction(result.theta_after);
  const rose = result.theta_after > result.theta_before;

  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between">
        <p className="eyebrow">{result.topic}</p>
        <p className="num text-xs">
          <span className="text-muted">{result.theta_before.toFixed(2)}</span>
          <span className="mx-1.5 text-muted">→</span>
          <span className={rose ? "text-verdict-supported" : "text-marker"}>
            {result.theta_after >= 0 ? "+" : ""}
            {result.theta_after.toFixed(2)}
          </span>
        </p>
      </div>

      <div className="relative mt-2 h-2 w-full bg-ink/[0.07]">
        <span
          className="absolute inset-y-0 left-0 bg-ink/25"
          style={{ width: `${before * 100}%` }}
        />
        <span
          className={`absolute inset-y-0 ${rose ? "bg-verdict-supported" : "bg-marker"}`}
          style={{
            left: `${Math.min(before, after) * 100}%`,
            width: `${Math.abs(after - before) * 100}%`,
          }}
        />
      </div>

      <p className="mt-2 text-xs text-muted">
        The model gave you a{" "}
        <span className="num">{(result.predicted_p * 100).toFixed(0)}%</span> chance on
        this one, so {result.correct ? "getting it right" : "missing it"} moved the
        estimate by{" "}
        <span className="num">
          {Math.abs(result.theta_after - result.theta_before).toFixed(2)}
        </span>
        .
      </p>
    </div>
  );
}
