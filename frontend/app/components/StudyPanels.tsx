"use client";

import { MasteryRow, Plan, thetaFraction } from "../lib/study-api";

/** Ability per topic, weakest first — the same ordering the planner uses. */
export function MasteryPanel({
  rows,
  highlight,
}: {
  rows: MasteryRow[];
  highlight?: string | null;
}) {
  if (!rows.length) {
    return (
      <section className="border border-rule bg-card px-4 py-6">
        <p className="text-sm text-muted">
          No topics yet. Run topic extraction for this course first.
        </p>
      </section>
    );
  }

  return (
    <section className="border border-rule bg-card">
      <header className="flex items-baseline justify-between border-b border-rule px-4 py-3">
        <p className="eyebrow">Mastery</p>
        <p className="num text-xs text-muted">{rows.length} topics</p>
      </header>

      <ul className="divide-y divide-rule">
        {rows.map((r) => {
          const active = highlight === r.topic;
          const untested = r.n_seen === 0;
          return (
            <li key={r.topic_id} className={`px-4 py-3 ${active ? "bg-paper" : ""}`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate text-sm">{r.topic}</span>
                <span className="num shrink-0 text-xs text-muted">
                  {untested ? "—" : `${r.theta >= 0 ? "+" : ""}${r.theta.toFixed(2)}`}
                </span>
              </div>

              <div className="mt-1.5 h-1.5 w-full bg-ink/[0.07]">
                {!untested && (
                  <span
                    className={`block h-full ${r.theta < 0 ? "bg-marker" : "bg-accent"}`}
                    style={{ width: `${thetaFraction(r.theta) * 100}%` }}
                  />
                )}
              </div>

              <p className="num mt-1.5 text-[0.6875rem] text-muted">
                {untested
                  ? `not assessed · ${r.n_questions} question${r.n_questions === 1 ? "" : "s"} available`
                  : `${r.n_correct}/${r.n_seen} correct` +
                    (r.retention !== null
                      ? ` · retention ${(r.retention * 100).toFixed(0)}%`
                      : "")}
              </p>
            </li>
          );
        })}
      </ul>

      <footer className="border-t border-rule px-4 py-3">
        <p className="text-xs text-muted">
          Ability is a single logistic parameter per topic, updated Elo-style after
          each answer. Untested topics show no estimate rather than a default of
          zero — unknown is not the same as average.
        </p>
      </footer>
    </section>
  );
}

/** The generated revision schedule, with the ranking that produced it. */
export function PlanView({ plan }: { plan: Plan }) {
  const byDay = plan.items.reduce<Record<string, typeof plan.items>>((acc, it) => {
    (acc[it.day] ??= []).push(it);
    return acc;
  }, {});
  const days = Object.keys(byDay).sort();

  return (
    <div className="space-y-6">
      <section className="border border-rule bg-card">
        <header className="flex items-baseline justify-between border-b border-rule px-4 py-3">
          <p className="eyebrow">Why this order</p>
          <p className="num text-xs text-muted">
            {plan.n_items} sessions · {plan.days} days
          </p>
        </header>
        <ul className="divide-y divide-rule">
          {plan.ranking.slice(0, 8).map((r) => (
            <li key={r.topic} className="flex items-baseline gap-3 px-4 py-2">
              <span className="num w-12 shrink-0 text-xs text-muted">
                {r.urgency.toFixed(2)}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm">{r.topic}</span>
              <span className="num shrink-0 text-[0.6875rem] text-muted">
                {r.n_seen === 0 ? "untested" : `θ ${r.theta >= 0 ? "+" : ""}${r.theta.toFixed(2)}`}
              </span>
            </li>
          ))}
        </ul>
        <footer className="border-t border-rule px-4 py-3">
          <p className="text-xs text-muted">
            Urgency is <span className="num">(1 − predicted retention at exam) × (1 + weakness)</span>,
            computed in code rather than asked of a model — so the schedule can be
            checked, re-ordered and re-planned.
          </p>
        </footer>
      </section>

      <section className="border border-rule bg-card">
        <header className="border-b border-rule px-4 py-3">
          <p className="eyebrow">Schedule</p>
        </header>
        <ul className="divide-y divide-rule">
          {days.map((day) => (
            <li key={day} className="px-4 py-3">
              <p className="num text-xs text-muted">{day}</p>
              <ul className="mt-2 space-y-2">
                {byDay[day].map((it, i) => (
                  <li key={i} className="flex items-baseline gap-3">
                    <span className="eyebrow w-14 shrink-0">{it.activity}</span>
                    <span className="min-w-0 flex-1">
                      <span className="text-sm">{it.topic}</span>
                      <span className="num ml-2 text-[0.6875rem] text-muted">
                        {it.minutes}m
                      </span>
                      <span className="block text-xs text-muted">{it.rationale}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
