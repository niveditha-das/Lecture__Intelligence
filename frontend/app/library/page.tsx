"use client";

/**
 * Library: get material in, and manage what's there.
 *
 * On recording: the browser captures audio, which is transcribed with
 * timestamps and stored as a source in its own right. It is deliberately not
 * converted to a PDF — a PDF would throw away the timestamps, and those are
 * what let a citation say "Lecture 7 @ 06:52" and seek the player to the
 * moment the lecturer said it. The transcript is downloadable as text if a
 * file is what you actually want.
 */

import { useEffect, useRef, useState } from "react";
import { API, Course, getCourses, getSources, Source } from "../lib/api";
import { CoursePicker, Header, PageIntro, Details } from "../components/Shell";

const KIND_LABEL: Record<string, string> = {
  pdf: "PDF",
  pptx: "Slides",
  audio: "Recording",
  notes: "Notes",
};

const ACCEPT = ".pdf,.pptx,.ppt,.md,.txt,.mp3,.m4a,.wav,.mp4,.webm,.ogg";

function fmtDuration(sec: number) {
  const m = Math.floor(sec / 60);
  return `${m}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
}

export default function LibraryPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newCourse, setNewCourse] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  // --- recording state ---
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  async function loadCourses() {
    const cs = await getCourses();
    setCourses(cs);
    if (!courseId && cs.length) setCourseId(cs[0].id);
  }

  async function loadSources(id: string) {
    if (!id) return;
    setSources(await getSources(id));
  }

  useEffect(() => {
    loadCourses().catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!courseId) return;
    void loadSources(courseId);
    // Ingestion runs in the background, so poll while anything is unfinished.
    const t = setInterval(() => {
      getSources(courseId).then((s) => {
        setSources(s);
        if (!s.some((x) => x.status === "pending" || x.status === "processing")) {
          clearInterval(t);
        }
      });
    }, 4000);
    return () => clearInterval(t);
  }, [courseId]);

  async function upload(files: FileList | File[]) {
    if (!courseId) {
      setError("Make a course first.");
      return;
    }
    setError(null);
    for (const file of Array.from(files)) {
      setBusy(`Uploading ${file.name}…`);
      const stem = file.name.replace(/\.[^.]+$/, "");
      const week = stem.match(/\d+/)?.[0];
      const form = new FormData();
      form.append("course_id", courseId);
      form.append("file", file);
      form.append("title", stem.replace(/[_-]+/g, " "));
      if (week) form.append("week", week);
      try {
        const res = await fetch(`${API}/sources`, { method: "POST", body: form });
        if (!res.ok) throw new Error(await res.text());
      } catch (e) {
        setError(`${file.name}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
    setBusy(null);
    void loadSources(courseId);
  }

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks.current = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
        await upload([new File([blob], `Recording ${stamp}.webm`, { type: "audio/webm" })]);
      };
      rec.start();
      recorder.current = rec;
      setRecording(true);
      setElapsed(0);
      timer.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch {
      setError("Couldn't access the microphone. Check the browser's permission prompt.");
    }
  }

  function stopRecording() {
    recorder.current?.stop();
    if (timer.current) clearInterval(timer.current);
    setRecording(false);
  }

  async function remove(s: Source) {
    if (!confirm(`Delete "${s.title}" and everything indexed from it?`)) return;
    await fetch(`${API}/sources/${s.id}`, { method: "DELETE" });
    void loadSources(courseId);
  }

  async function reingest(s: Source) {
    await fetch(`${API}/sources/${s.id}/reingest`, { method: "POST" });
    void loadSources(courseId);
  }

  async function createCourse() {
    const name = newCourse.trim();
    if (!name) return;
    const res = await fetch(`${API}/courses`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const c = await res.json();
    setNewCourse("");
    await loadCourses();
    setCourseId(c.id);
  }

  const totalChunks = sources.reduce(
    (n, s) => n + (((s as unknown as { meta?: { n_chunks?: number } }).meta?.n_chunks) ?? 0),
    0,
  );

  return (
    <>
      <Header active="library" />
      <PageIntro
        title="Library"
        sub="Add slides, notes or a recording. Everything you upload becomes searchable, with citations back to the exact page."
      />

      <main className="mx-auto max-w-4xl px-5 py-8 pb-16">
        {/* ---- course ---- */}
        <div className="flex flex-wrap items-center gap-3">
          <CoursePicker courses={courses} value={courseId} onChange={setCourseId} />
          <div className="flex items-center gap-2">
            <input
              value={newCourse}
              onChange={(e) => setNewCourse(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void createCourse()}
              placeholder="New course name"
              className="field py-1.5 text-sm"
            />
            <button onClick={() => void createCourse()} disabled={!newCourse.trim()} className="btn-soft">
              Add course
            </button>
          </div>
        </div>

        {/* ---- upload ---- */}
        <section
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void upload(e.dataTransfer.files);
          }}
          className="card mt-5 border-dashed p-8 text-center"
        >
          <p className="text-lg font-medium">Drop files here</p>
          <p className="mx-auto mt-1 max-w-measure text-sm text-muted">
            PDF, PowerPoint, markdown or audio. A number in the filename is read as
            the week, so <span className="font-mono text-xs">CSC1021_04.pdf</span>{" "}
            lands in week 4.
          </p>

          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <button onClick={() => fileInput.current?.click()} className="btn" disabled={!courseId}>
              Choose files
            </button>
            {!recording ? (
              <button onClick={() => void startRecording()} className="btn bg-rose/20 text-rose shadow-none hover:bg-rose hover:text-white" disabled={!courseId}>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-rose" />
                Record a lecture
              </button>
            ) : (
              <button onClick={stopRecording} className="btn-soft">
                <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-rose" />
                Stop — {fmtDuration(elapsed)}
              </button>
            )}
          </div>

          <input
            ref={fileInput}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => e.target.files && void upload(e.target.files)}
          />

          {recording && (
            <p className="mt-4 text-sm text-amber">
              Recording. Transcription runs after you stop and takes roughly as long
              as the recording itself.
            </p>
          )}
          {busy && <p className="mt-4 text-sm text-muted">{busy}</p>}
        </section>

        {error && (
          <p className="card mt-5 border-rose/30 bg-rose/10 px-4 py-3 text-sm">{error}</p>
        )}

        {/* ---- what's in here ---- */}
        <section className="mt-8">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-lg font-semibold">
              {sources.length} file{sources.length === 1 ? "" : "s"}
            </h2>
            {totalChunks > 0 && (
              <span className="text-sm text-muted">{totalChunks} searchable pieces</span>
            )}
          </div>

          {sources.length === 0 && (
            <p className="card mt-3 px-4 py-8 text-center text-sm text-muted">
              Nothing here yet.
            </p>
          )}

          <ul className="mt-3 space-y-2">
            {sources.map((s) => {
              const meta = (s as unknown as { meta?: { n_chunks?: number } }).meta;
              const pending = s.status === "pending" || s.status === "processing";
              return (
                <li key={s.id} className="card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <a href={`/library/${s.id}`} className="truncate font-medium hover:text-brand">
                        {s.title}
                      </a>
                      <p className="mt-0.5 text-sm text-muted">
                        {KIND_LABEL[s.kind] ?? s.kind}
                        {s.week !== null && ` · Week ${s.week}`}
                        {meta?.n_chunks ? ` · ${meta.n_chunks} pieces` : ""}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <span
                        className={`chip ${
                          s.status === "ready"
                            ? "bg-teal/15 text-teal"
                            : pending
                              ? "bg-amber/15 text-amber"
                              : "bg-rose/15 text-rose"
                        }`}
                      >
                        {s.status === "ready"
                          ? "Ready"
                          : pending
                            ? "Processing…"
                            : "Failed"}
                      </span>

                      {s.kind === "audio" && s.status === "ready" && (
                        <a
                          href={`${API}/sources/${s.id}/transcript.txt`}
                          className="btn-quiet"
                          download
                        >
                          Transcript
                        </a>
                      )}
                      {s.status === "failed" && (
                        <button onClick={() => void reingest(s)} className="btn-quiet">
                          Retry
                        </button>
                      )}
                      <button
                        onClick={() => void remove(s)}
                        className="btn-quiet hover:border-rose hover:text-rose"
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  {s.error && (
                    <p className="mt-3 rounded-md bg-rose/10 px-3 py-2 text-sm text-rose">
                      {s.error}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>

          <Details summary="What happens to an upload">
            <ol className="space-y-2 text-sm text-muted">
              <li>
                1. Text is extracted with its position kept — page number and the
                box on the page, or a timestamp for audio.
              </li>
              <li>
                2. It&apos;s split into pieces that never cross a page boundary, so a
                citation always points at one slide.
              </li>
              <li>
                3. Each piece is embedded for meaning-based search and indexed for
                keyword search.
              </li>
              <li>
                4. The original file is kept, which is what lets a citation render
                the actual page with the region highlighted.
              </li>
            </ol>
          </Details>
        </section>
      </main>
    </>
  );
}
