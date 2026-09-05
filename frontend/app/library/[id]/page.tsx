"use client";

/**
 * Browse a source page by page, and ask about one slide.
 *
 * The rest of the app runs question -> answer -> source. This runs the other
 * way: you're stuck on slide 23, you click slide 23, and it gets explained
 * using that slide plus its neighbours — because a slide mid-derivation means
 * nothing without the one before it.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { API } from "../../lib/api";
import { Details, Header, PageIntro } from "../../components/Shell";

type Page = { page: number; chunk_ids: number[]; preview: string; t_start?: number | null };
type Meta = { id: string; title: string; kind: string; week: number | null };

export default function SourcePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [meta, setMeta] = useState<Meta | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [selected, setSelected] = useState<Page | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetch(`${API}/sources/${id}/pages`)
      .then((r) => r.json())
      .then((d) => {
        setMeta(d.source);
        setPages(d.pages ?? []);
      })
      .catch((e) => setError(String(e)));
  }, [id]);

  async function explain(p: Page) {
    setSelected(p);
    setAnswer(null);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/explain-slide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source_id: id, page: p.page }),
      });
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      setAnswer(d.answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const isPdf = meta?.kind === "pdf";

  return (
    <>
      <Header active="library" />
      <PageIntro
        title={meta?.title ?? "Loading…"}
        sub={
          pages.length
            ? `${pages.length} pages. Click one to have it explained from the surrounding material.`
            : "Reading pages…"
        }
      />

      <main className="mx-auto max-w-5xl px-5 py-8 pb-16">
        <a href="/library" className="text-sm text-muted hover:text-ink">
          ← Back to library
        </a>

        {error && (
          <p className="card mt-4 border-rose/30 bg-rose/10 px-4 py-3 text-sm">{error}</p>
        )}

        {/* --- the explanation, above the grid once something is picked --- */}
        {selected && (
          <section className="card mt-5 animate-rise p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="chip bg-brand-soft text-brand">Page {selected.page}</span>
              {selected.t_start != null && (
                <span className="chip bg-teal/15 text-teal">
                  {Math.floor(selected.t_start / 60)}:
                  {String(Math.floor(selected.t_start % 60)).padStart(2, "0")} in the recording
                </span>
              )}
            </div>

            {busy && <p className="mt-4 text-sm text-muted">Reading the slide…</p>}
            {answer && <p className="mt-4 whitespace-pre-line text-lg">{answer}</p>}

            {isPdf && (
              <div className="mt-5 rounded-lg bg-raise p-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`${API}/sources/${id}/page/${selected.page}.png`}
                  alt={`Page ${selected.page}`}
                  className="w-full rounded-md"
                />
              </div>
            )}
          </section>
        )}

        {/* --- page grid --- */}
        <section className="mt-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pages.map((p) => (
              <button
                key={p.page}
                onClick={() => void explain(p)}
                className={`card p-4 text-left transition hover:border-brand ${
                  selected?.page === p.page ? "border-brand" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Page {p.page}</span>
                  {p.t_start != null && (
                    <span className="text-xs text-teal">
                      {Math.floor(p.t_start / 60)}:
                      {String(Math.floor(p.t_start % 60)).padStart(2, "0")}
                    </span>
                  )}
                </div>
                <p className="mt-2 line-clamp-3 text-sm text-muted">{p.preview}</p>
              </button>
            ))}
          </div>

          {pages.length === 0 && !error && (
            <p className="card px-4 py-8 text-center text-sm text-muted">
              No pages indexed for this file yet.
            </p>
          )}
        </section>

        <Details summary="Why neighbouring slides are included">
          <p className="text-sm text-muted">
            A slide in the middle of a derivation is meaningless on its own, and a
            term is often defined on the slide after the one that uses it. The
            explanation is given the page before and after as context, but is told
            to stay on the page you picked.
          </p>
        </Details>
      </main>
    </>
  );
}
