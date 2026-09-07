# Lecture Intelligence Platform

![ci](https://github.com/niveditha-das/Lecture_Intelligence/actions/workflows/ci.yml/badge.svg)

Turns a course's slides, notes and recordings into a searchable knowledge base
that answers questions **only** from that material — and shows you the exact
slide region each sentence came from.

> *Explain deadlock using only material from Week 4.*
> → an answer where every sentence carries a citation, and clicking `[2]`
> renders slide 68 with the supporting region boxed.

Not a chatbot with a PDF attached. The interesting parts are the provenance
chain, the hybrid retrieval, and the measurement.

<!-- Replace with a screenshot of an answer with a citation open:
     ![Citation viewer](docs/screenshot.png) -->

---

## Measured quality

Every eval run is stored in `eval_runs` with its git SHA and full retrieval
config, so these numbers are reproducible and regressions fail CI.

### Retrieval — CSC1021, 5 lectures, 399 chunks

16 hand-verified factual questions, 5 unanswerable controls, k=5.

| config | recall@5 | MRR | p50 latency |
|---|---|---|---|
| hybrid (vector + keyword, RRF) | 0.938 | 0.875 | 606 ms |
| + cross-encoder rerank | 0.938 | 0.875 | 4626 ms |

**Reranking contributed nothing on this corpus**, against +0.083 MRR on a
smaller one, for 8× the latency. Reranking only helps when fusion ordering is
wrong; here RRF already put gold first in most cases. Worth measuring per
corpus rather than assuming.

### Generation

| metric | value |
|---|---|
| citation precision (strict, vs gold labels) | 0.722 |
| citation precision (counting verified sources) | 1.000 |
| unsupported-claim rate | 0.03 |
| refusal accuracy on unanswerable controls | 1.00 (6/6) |

Two citation-precision numbers, because the first measures the wrong thing.
Strict precision scores a citation correct only if it appears in the gold label,
which lists one chunk per question — but a concept usually spans consecutive
slides. Measured case: *"why is a context switch pure overhead?"* cited chunk
213 (gold) and 212, where 212 reads "a context switch occurs when the CPU
switches from one process to another". A correct, relevant source, scored 0.5.

The relaxed metric counts a citation as correct if it is a gold chunk **or** if
the per-sentence entailment checker independently confirmed it supports the
sentence citing it. That is a second signal, not a loosened threshold — the
judge never sees the gold labels.

### Corpus size determines what you can measure

The same code, thresholds and settings across three corpora:

| corpus | chunks | recall@5 | topics kept | topics pruned |
|---|---|---|---|---|
| Machine Learning | 33 | — | 4 | 65 |
| Probability | 43 | 1.00 (saturated) | 13 | 25 |
| Operating Systems | 399 | 0.938 | 72 | 0 |

At 43 chunks both retrieval arms return nearly the whole index, so recall
saturates at 1.00 and the metric describes the corpus rather than the system.
Topic extraction shows the same effect from the other side: a concept needs to
appear on more than one slide to be a topic at all, and in a 33-chunk corpus
almost nothing does.

---

## Three ideas worth reading the code for

**1. Provenance is atomic** — `backend/app/ingest/base.py`

Extractors emit `Block`s that already know exactly where they came from: PDF
page + normalised bbox, PPTX slide + shape, transcript `t_start`/`t_end`. The
chunker may only *merge* locators, never blur them, and never across a page
boundary. If a bbox is lost at extraction time no downstream cleverness can
recover it, so `tests/test_core.py` asserts this directly.

**2. Transcript ↔ slide alignment** — `backend/app/ingest/align.py`

A lecturer moves through slides in order, so segment → slide is monotonically
non-decreasing. That makes it a constrained DTW over the segment × slide
similarity matrix. A transcript chunk gains a slide number and a slide chunk
gains a timestamp, so a citation can read *"Lecture 7, slide 23 @ 06:52"*.

**3. Answers are checked, not trusted** — `backend/app/answer/verify.py`

After generation the answer is split into sentences and each sentence's own
citations are checked for entailment by a second model. That is both a UI
guardrail and the `unsupported_claim_rate` metric above.

---

## Architecture

```
upload ──► extract ──► chunk ──► embed ──► Postgres (pgvector + tsvector)
           (bbox /     (never    (1024d)         │
            slide /     crosses                  ▼
            timestamp)  a page)        ┌──────────────────┐
                                       │ ANN  ∥  keyword  │  two arms
                                       └────────┬─────────┘
                                          RRF fusion
                                                │
                                       cross-encoder rerank
                                                │
                                     grounded generation → [n] markers
                                                │
                                     per-sentence entailment check
                                                │
                                     citations → rendered page + bbox
```

One database does both relational and vector work. No separate vector store —
the RRF query in `backend/app/retrieval/search.py` is a single round-trip.

---

## What it does

**Ask** — questions answered only from your material, with clickable citations
that render the source page and box the region used. Filter by course and week,
or search every course at once. Four explanation styles: simple, technical,
worked example, Socratic.

**Study** — LLM topic extraction with embedding-based label merging, question
generation in three formats (MCQ, short answer, long answer) grounded in
specific chunks, an Elo-style mastery model, and a revision planner.

**Exam** — a short paper with model answers withheld until submission, then all
marked at once. Question selection is deliberately *not* adaptive: practice
targets your current ability, but an exam should sample the syllabus including
what you have avoided.

**Library** — drag-and-drop upload, in-browser recording, and per-file
management with transcript download.

---

## Stack

Python 3.12 · FastAPI · asyncpg · Postgres 16 + pgvector · PyMuPDF ·
python-pptx · faster-whisper · sentence-transformers (bge-m3,
ms-marco-MiniLM-L-6-v2) · Next.js 16 · TypeScript · Tailwind · Docker ·
GitHub Actions

Generation runs through any OpenAI-compatible endpoint. Embeddings run locally,
so retrieval and the eval harness need no API key at all.

---

## Run it

```bash
cp .env.example .env          # add one API key for generation
make up                       # postgres + api on :8000
curl localhost:8000/health

cd frontend
cp .env.local.example .env.local
npm install && npm run dev    # :3000
```

Open http://localhost:3000/library, create a course, and drop in some PDFs. The
three sample decks in `samples/` are committed so the project can be run
without supplying your own material.

### Evaluate

```bash
make eval-ablation            # retrieval only: free, no API key
make eval                     # adds generation, citation precision, refusal
make eval-history             # every run, with its git SHA
```

---

## Engineering notes

Things that only surfaced by running the system.

### Retrieval latency

| config | p50 | note |
|---|---|---|
| bge-reranker-v2-m3 (568M), cold | 431 s | model loaded inside the request |
| bge-reranker-v2-m3, warmed | 15.5 s | CPU inference dominates |
| no rerank | 3.1 s | embedding + SQL only |
| ms-marco-MiniLM-L-6-v2 (22M), warmed | 3.5 s | reranker cost ~0.4 s |

Swapping a 568M reranker for a 22M one cut reranking from ~12.4 s to ~0.4 s
with no change to the top-6 ordering on spot-checked queries.

### The one retrieval failure is a chunking problem

*"How does Round Robin turnaround compare to SJF?"* has its answer in chunk 70,
which states it in one clear sentence — but that chunk is dominated by a Gantt
chart whose text extracted as `P1 P1 P1 P P P 1 1 1 0 18 30 26 14 4 7 10 22`.
The relevant sentence is ~12% of the chunk; the rest is diagram debris pulling
the embedding away from any prose query. Retrieval behaved correctly given a
poisoned chunk.

Filtering blocks by alphabetic-character ratio would fix this case and also
discard legitimate notation-heavy slides (`S = {H, T}`, formula derivations).
Left unfixed and documented rather than papered over with a heuristic that
trades one failure mode for another.

### Controls must be verified, not assumed

Eight unanswerable controls were hand-written for the OS corpus. Three —
banker's algorithm, TLB address translation, copy-on-write — turned out to be
covered, scoring +7.33, +5.85 and +1.76 on the reranker. Loading them unchecked
would have reported refusal accuracy of 5/8 and suggested the system
hallucinates, when in fact it correctly answered three mislabelled questions.
A wrong benchmark is worse than no benchmark.

### Gold labels have to be portable

`eval_examples.gold_chunk_ids` held bigserial ids assigned at ingest time, so a
fresh database assigned different numbers to the same passages and every label
silently pointed at the wrong chunk. Gold labels are now exported as
`(source_title, ordinal)` and resolved on import — which is what makes the CI
gate possible at all.

### Concurrent lazy initialisation

Eight concurrent eval requests each saw `_model is None` and started building
their own copy of a 568M embedding model. Memory ran out mid-load and torch
left the weights on the meta device, surfacing as `Cannot copy out of meta
tensor` — an error that says nothing about the cause. Fixed with
double-checked locking plus loading both models at startup.

### A throttle that fixed batch work broke interactive work

Centralising rate limiting in `llm.py` (one call per ~4.5 s) made evaluation
reproducible, but verification made one judge call per sentence — so a
six-sentence answer took ~32 s. Verification now checks every sentence in a
single call: claims are numbered, the judge returns one verdict per index.
`/ask` went 32 s → 6.4 s with no change in verdict quality.

The lesson isn't about rate limits. A shared resource control has to be judged
against every caller, not just the one that motivated it.

### Failed checks are not hallucinations

`unsupported_claim_rate` originally counted judge failures as unsupported
claims, reporting 0.778 when only 2 of 9 sentences had actually been checked.
UNKNOWN verdicts are now excluded from the denominator and surfaced separately.
An infrastructure error must never masquerade as a quality signal.

### The verifier only sees passage text

An early answer opened with *"As covered in the Week 1 lecture…"* and the judge
returned PARTIAL — correctly, since the passage contains no week metadata. The
generator can see citation labels the verifier cannot, so it is now forbidden
from narrating provenance in prose. The citation objects carry it.

---

## CI

Three jobs on every push:

- **unit tests** — provenance preservation, retrieval metrics, the mastery
  maths and DTW monotonicity. No database, no models, ~30 s.
- **app imports** — walks and imports every module. Catches import-time errors
  a syntax check misses, such as a dataclass field ordering bug that took the
  API down at startup.
- **retrieval quality gate** — ingests the committed sample PDFs, loads the
  hand-verified gold set, and fails the build if recall@5 drops below 0.80 or
  MRR below 0.70. Retrieval only, so it needs no API key and costs nothing.

The fixture corpus is small, so the gate catches breakage rather than subtle
regression. It is still the difference between "the chunker change looked fine"
and "the chunker change silently stopped matching anything".

---

## Status

- [x] PDF / PPTX / notes ingestion with locator-preserving chunking
- [x] Hybrid retrieval (pgvector + tsvector, RRF) with cross-encoder rerank
- [x] Grounded answering, citation parsing, per-sentence verification
- [x] Eval harness: recall@k, MRR, citation precision, refusal accuracy
- [x] Citation viewer — page render with bbox overlay, audio seek
- [x] Topic extraction with embedding-based label merging
- [x] Question generation: MCQ, short answer, long answer
- [x] Elo-style mastery model with self-assessed written answers
- [x] Deterministic revision planner and exam mode
- [x] Slide browser with per-page explanation
- [x] Transcript-to-slide alignment wired into ingestion
- [x] CI: unit tests, import check, retrieval quality gate
- [ ] Alignment verified against a real recording — the code path has only run
      on synthetic embeddings
- [ ] Audio ingestion behind a job queue; it is currently a FastAPI background
      task, which will not survive a deployed instance
- [ ] Topic extraction is not idempotent — re-running accumulates topics rather
      than replacing them

## Known limitations

**The revision planner ranks a topic answered once above eleven never
assessed**, because untested topics get a fixed retention floor while a tested
topic's retention decays toward the exam. Recent evidence of weakness
outranking absence of evidence is defensible; a *correct* answer outranking an
untested topic is not. All untested topics also tie exactly, so their relative
order is arbitrary — a real course would break that tie on week proximity.

Both are visible because the ranking is returned with the plan rather than
hidden inside a prompt, which is the argument for a deterministic planner over
asking a model for a timetable.

**Written answers are self-assessed**, which is noisier than a multiple-choice
comparison. Those attempts are flagged `self_assessed` in the database so a
later calibration pass can down-weight them.
