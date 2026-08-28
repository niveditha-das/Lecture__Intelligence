"use client";

import { AskResponse, Citation, SentenceCheck, Verdict } from "../lib/api";

const VERDICT_STYLE: Record<Verdict, string> = {
  SUPPORTED: "text-verdict-supported",
  PARTIAL: "text-verdict-partial",
  UNSUPPORTED: "text-marker",
  UNCITED: "text-verdict-uncited",
  UNKNOWN: "text-verdict-unknown",
};

const VERDICT_NOTE: Record<Verdict, string> = {
  SUPPORTED: "The cited passages state this.",
  PARTIAL: "The passages support part of this claim.",
  UNSUPPORTED: "The cited passages do not establish this.",
  UNCITED: "Written without a citation — usually an analogy the model added.",
  UNKNOWN: "The checker failed here, so this sentence is unmeasured.",
};

/** Splits the answer on [n] markers and makes each one a button. */
export function AnswerBody({
  answer,
  citations,
  activeN,
  onPick,
}: {
  answer: string;
  citations: Citation[];
  activeN: number | null;
  onPick: (c: Citation) => void;
}) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const paragraphs = answer.split(/\n{2,}/);

  return (
    <div className="max-w-measure space-y-4 text-[1.0625rem] leading-[1.7]">
      {paragraphs.map((para, pi) => (
        <p key={pi}>
          {para.split(/(\[\d+\])/g).map((part, i) => {
            const m = /^\[(\d+)\]$/.exec(part);
            const cite = m ? byN.get(Number(m[1])) : undefined;
            if (!cite) return <span key={i}>{part}</span>;
            const active = activeN === cite.n;
            return (
              <button
                key={i}
                onClick={() => onPick(cite)}
                title={cite.label}
                aria-label={`Show source ${cite.n}: ${cite.label}`}
                className={[
                  "num mx-[0.1em] inline-flex h-[1.35em] min-w-[1.35em] items-center justify-center",
                  "align-[0.15em] text-[0.7em] font-medium transition-colors",
                  active
                    ? "bg-marker text-white"
                    : "bg-ink/[0.07] text-ink hover:bg-accent hover:text-white",
                ].join(" ")}
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

/** Per-sentence grounding verdicts — the measurement, shown rather than claimed. */
export function VerificationPanel({ result }: { result: AskResponse }) {
  const v = result.verification;
  if (!v) return null;

  const rate = v.unsupported_claim_rate;
  const counts = v.sentences.reduce<Record<string, number>>((acc, s) => {
    acc[s.verdict] = (acc[s.verdict] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="border border-rule bg-card">
      <header className="flex items-baseline justify-between border-b border-rule px-4 py-3">
        <p className="eyebrow">Grounding check</p>
        <p className="num text-xs text-muted">
          {v.n_checked}/{v.n_sentences} checked
        </p>
      </header>

      <div className="flex items-baseline gap-3 border-b border-rule px-4 py-4">
        <span
          className={[
            "num text-3xl",
            rate === null
              ? "text-muted"
              : rate === 0
                ? "text-verdict-supported"
                : "text-verdict-partial",
          ].join(" ")}
        >
          {rate === null ? "—" : rate.toFixed(2)}
        </span>
        <span className="text-sm text-muted">
          unsupported-claim rate
          {rate === null && " (nothing could be checked)"}
        </span>
      </div>

      <ul className="divide-y divide-rule">
        {v.sentences.map((s: SentenceCheck, i) => (
          <li key={i} className="px-4 py-3">
            <div className="flex items-start gap-3">
              <span
                className={`eyebrow shrink-0 pt-[0.2rem] ${VERDICT_STYLE[s.verdict]}`}
              >
                {s.verdict}
              </span>
              <div className="min-w-0">
                <p className="text-sm leading-relaxed">{s.sentence}</p>
                <p className="mt-1 text-xs text-muted">
                  {s.why || VERDICT_NOTE[s.verdict]}
                </p>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <footer className="border-t border-rule px-4 py-3">
        <p className="num text-xs text-muted">
          {Object.entries(counts)
            .map(([k, n]) => `${k.toLowerCase()} ${n}`)
            .join("  ·  ")}
        </p>
      </footer>
    </section>
  );
}

/** What retrieval actually returned, and which arm found it. */
export function RetrievalPanel({ result }: { result: AskResponse }) {
  if (!result.hits.length) return null;
  return (
    <section className="border border-rule bg-card">
      <header className="border-b border-rule px-4 py-3">
        <p className="eyebrow">Retrieved passages</p>
      </header>
      <ul className="divide-y divide-rule">
        {result.hits.map((h) => (
          <li key={h.chunk_id} className="flex items-baseline gap-3 px-4 py-2">
            <span className="num w-14 shrink-0 text-xs text-muted">
              {h.rerank_score !== null ? h.rerank_score.toFixed(2) : h.rrf.toFixed(4)}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm">{h.label}</span>
            <span className="num shrink-0 text-[0.65rem] uppercase tracking-wide text-muted">
              {h.arms.join("+")}
            </span>
          </li>
        ))}
      </ul>
      <footer className="border-t border-rule px-4 py-3">
        <p className="text-xs text-muted">
          Score is the cross-encoder&apos;s when reranking ran, otherwise the RRF
          fusion score. <span className="num">vec</span> and{" "}
          <span className="num">kw</span> show which arm surfaced each passage.
        </p>
      </footer>
    </section>
  );
}
