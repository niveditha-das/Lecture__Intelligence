"use client";

/**
 * The cited slide, with the exact region boxed.
 *
 * Orange appears nowhere else in the interface, so the eye goes straight to the
 * evidence. On a dark page the rendered PDF is a bright white slab, so it sits
 * inside a padded rounded frame — that reads as "a document" rather than as a
 * rendering fault. The overlay is inset by the same padding.
 */

import { useEffect, useRef, useState } from "react";
import { API, Citation, timecode } from "../lib/api";

export function SourceView({ citation }: { citation: Citation }) {
  const { locator, source_id, source_kind } = citation;
  const page = locator.page ?? locator.slide;
  const regions = (locator.regions ?? []).filter((r) => r.page === page);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    setLoaded(false);
    setFailed(false);
  }, [citation.chunk_id]);

  if (source_kind === "audio" && locator.t_start !== undefined) {
    return (
      <figure className="card animate-rise overflow-hidden">
        <figcaption className="border-b border-rule px-4 py-3 text-sm">
          {citation.source_title} · {timecode(locator.t_start)}
        </figcaption>
        <div className="p-4">
          <audio
            ref={audioRef}
            controls
            className="w-full"
            src={`${API}/sources/${source_id}/file`}
            onLoadedMetadata={() => {
              if (audioRef.current && locator.t_start !== undefined) {
                audioRef.current.currentTime = locator.t_start;
              }
            }}
          />
        </div>
      </figure>
    );
  }

  if (!page) {
    return <p className="card px-4 py-3 text-sm text-muted">From {citation.label}</p>;
  }

  return (
    <figure className="card animate-rise overflow-hidden">
      <figcaption className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-3 text-sm">
        <span className="chip bg-highlight/15 text-highlight">Source</span>
        <span className="font-medium">{citation.label}</span>
        <span className="text-muted">— highlighted below</span>
      </figcaption>

      <div className="relative bg-raise p-3">
        {!loaded && !failed && (
          <div className="flex h-56 items-center justify-center text-sm text-muted">
            Loading page {page}…
          </div>
        )}
        {failed && (
          <div className="px-5 py-8 text-center text-sm text-muted">
            Couldn&apos;t show this page. It may not be a PDF.
          </div>
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${API}/sources/${source_id}/page/${page}.png`}
          alt={`${citation.source_title}, page ${page}`}
          className={loaded ? "block w-full rounded-md" : "hidden"}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
        {loaded && (
          <div className="pointer-events-none absolute inset-3">
            {regions.map((r, i) => (
              <span
                key={i}
                aria-hidden
                className="absolute rounded border-2 border-highlight bg-highlight/10"
                style={{
                  left: `${r.bbox[0] * 100}%`,
                  top: `${r.bbox[1] * 100}%`,
                  width: `${(r.bbox[2] - r.bbox[0]) * 100}%`,
                  height: `${(r.bbox[3] - r.bbox[1]) * 100}%`,
                }}
              />
            ))}
          </div>
        )}
      </div>
    </figure>
  );
}
