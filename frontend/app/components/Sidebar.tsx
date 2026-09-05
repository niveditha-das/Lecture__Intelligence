"use client";

/**
 * Left rail.
 *
 * Four pages that each fetched their own course list felt like four tools that
 * happened to share a stylesheet. A persistent rail makes the corpus the
 * constant thing and the page the variable one — and it keeps the size of what
 * you've indexed visible, which is the honest measure of whether any of this is
 * working.
 */

import Link from "next/link";
import { Course, Source } from "../lib/api";

const KIND_MARK: Record<string, string> = {
  pdf: "PDF",
  pptx: "SLD",
  audio: "REC",
  notes: "TXT",
};

function chunkCount(s: Source): number {
  return ((s as unknown as { meta?: { n_chunks?: number } }).meta?.n_chunks) ?? 0;
}

export function Sidebar({
  courses,
  courseId,
  sources,
  onSelectCourse,
  recent,
  onPickRecent,
}: {
  courses: Course[];
  courseId: string;
  sources: Source[];
  onSelectCourse: (id: string) => void;
  recent?: string[];
  onPickRecent?: (q: string) => void;
}) {
  const total = sources.reduce((n, s) => n + chunkCount(s), 0);

  return (
    <aside className="hidden w-60 shrink-0 lg:block">
      <div className="sticky top-6 space-y-6">
        {/* ---- courses ---- */}
        <nav>
          <p className="px-2 text-xs font-semibold uppercase tracking-wide text-faint">
            Courses
          </p>
          <ul className="mt-2 space-y-0.5">
            {courses.map((c) => {
              const active = c.id === courseId;
              return (
                <li key={c.id}>
                  <button
                    onClick={() => onSelectCourse(c.id)}
                    className={`w-full rounded-lg px-2 py-1.5 text-left text-sm transition ${
                      active
                        ? "bg-brand-soft font-medium text-brand-deep"
                        : "text-muted hover:bg-raise hover:text-ink"
                    }`}
                  >
                    {c.name}
                  </button>

                  {/* Files belong to the course they're under, so they only
                      appear when that course is the one in play. */}
                  {active && sources.length > 0 && (
                    <ul className="mb-2 mt-1 space-y-0.5 border-l border-rule pl-2">
                      {sources.map((s) => (
                        <li key={s.id}>
                          <Link
                            href={`/library/${s.id}`}
                            className="group flex items-baseline gap-2 rounded px-2 py-1 text-xs text-muted transition hover:bg-raise hover:text-ink"
                          >
                            <span className="shrink-0 font-mono text-[0.625rem] text-faint">
                              {KIND_MARK[s.kind] ?? "?"}
                            </span>
                            <span className="min-w-0 flex-1 truncate">{s.title}</span>
                            {chunkCount(s) > 0 && (
                              <span className="shrink-0 font-mono text-[0.625rem] text-faint">
                                {chunkCount(s)}
                              </span>
                            )}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>

          {total > 0 && (
            <p className="mt-3 px-2 text-xs text-faint">
              {sources.length} files · {total} searchable pieces
            </p>
          )}

          <Link
            href="/library"
            className="mt-3 block px-2 text-xs font-medium text-link hover:underline"
          >
            Add material →
          </Link>
        </nav>

        {/* ---- this session ---- */}
        {recent && recent.length > 0 && (
          <nav>
            <p className="px-2 text-xs font-semibold uppercase tracking-wide text-faint">
              Asked this session
            </p>
            <ul className="mt-2 space-y-0.5">
              {recent.map((q, i) => (
                <li key={i}>
                  <button
                    onClick={() => onPickRecent?.(q)}
                    className="w-full truncate rounded-lg px-2 py-1.5 text-left text-xs text-muted transition hover:bg-raise hover:text-ink"
                    title={q}
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </div>
    </aside>
  );
}
