"use client";

/**
 * The signature element.
 *
 * "Source: Lecture 7, slide 23" is a claim. This renders the actual page and
 * draws the region the answer came from, so the claim can be checked in one
 * glance. It works only because bboxes are captured at extraction time and the
 * chunker is forbidden from merging across page boundaries — the provenance
 * chain is intact all the way from PyMuPDF to this <span>.
 */

import { useEffect, useRef, useState } from "react";
import { API, Citation, timecode } from "../lib/api";

export function CitationViewer({ citation }: { citation: Citation }) {
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

  // --- audio: seek to the moment the lecturer said it ---------------------
  if (source_kind === "audio" && locator.t_start !== undefined) {
    return (
      <figure className="border border-rule bg-card">
        <div className="border-b border-rule px-4 py-3">
          <p className="eyebrow">Recording</p>
          <p className="mt-1 text-sm">
            {citation.source_title}{" "}
            <span className="num text-muted">
              {timecode(locator.t_start)}–
              {timecode(locator.t_end ?? locator.t_start)}
            </span>
          </p>
        </div>
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

  // --- notes / anything without a page ------------------------------------
  if (!page) {
    return (
      <figure className="border border-rule bg-card p-4">
        <p className="eyebrow">Source</p>
        <p className="mt-1 text-sm">{citation.label}</p>
        {locator.line_start !== undefined && (
          <p className="num mt-2 text-xs text-muted">
            lines {locator.line_start}–{locator.line_end}
          </p>
        )}
      </figure>
    );
  }

  // --- pdf / pptx: render the page and box the region ---------------------
  return (
    <figure className="border border-rule bg-card">
      <div className="flex items-baseline justify-between border-b border-rule px-4 py-3">
        <p className="eyebrow">Cited source</p>
        <p className="num text-xs text-muted">
          {regions.length} region{regions.length === 1 ? "" : "s"}
        </p>
      </div>

      <div className="relative bg-paper">
        {!loaded && !failed && (
          <div className="flex h-64 items-center justify-center">
            <p className="eyebrow animate-pulse">Rendering page {page}</p>
          </div>
        )}
        {failed && (
          <div className="flex h-40 items-center justify-center px-6 text-center">
            <p className="text-sm text-muted">
              Couldn&apos;t render this page. The API may be down, or this source
              isn&apos;t a PDF.
            </p>
          </div>
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${API}/sources/${source_id}/page/${page}.png`}
          alt={`${citation.source_title}, page ${page}`}
          className={loaded ? "block w-full" : "hidden"}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
        {/* bboxes are 0..1 page-relative, so the overlay is scale-independent */}
        {loaded &&
          regions.map((r, i) => (
            <span
              key={i}
              aria-hidden
              className="pointer-events-none absolute border-2 border-marker bg-marker/10"
              style={{
                left: `${r.bbox[0] * 100}%`,
                top: `${r.bbox[1] * 100}%`,
                width: `${(r.bbox[2] - r.bbox[0]) * 100}%`,
                height: `${(r.bbox[3] - r.bbox[1]) * 100}%`,
              }}
            />
          ))}
      </div>

      <figcaption className="border-t border-rule px-4 py-3 text-sm">
        {citation.label}
        <span className="num ml-2 text-xs text-muted">
          chunk {citation.chunk_id}
        </span>
      </figcaption>
    </figure>
  );
}
