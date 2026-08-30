# Lecture Intelligence Platform

Turns a course's slides, notes and lecture recordings into a searchable knowledge
base that answers questions **only** from that material, with citations you can
click and verify.

> Explain recursion using only material from Week 4.
> → an answer where every sentence carries a citation, and clicking `[2]` renders
> slide 23 with the exact region highlighted.

Not a chatbot with a PDF attached. The engineering is the point: provenance that
survives ingestion, hybrid retrieval, and a measured hallucination rate.

---

## Measured quality

Every run is stored in `eval_runs` with its git SHA and full retrieval config, so
these numbers are reproducible and regressions fail CI.

| metric | vector only | + keyword (RRF) | + cross-encoder rerank |
|---|---|---|---|
| recall@5 | _run it_ | _run it_ | _run it_ |
| MRR | | | |
| citation precision | | | |
| unsupported-claim rate | | | |
| refusal accuracy (unanswerable set) | | | |

Fill this in from `make eval-ablation`. The *deltas* are the interesting part:
they show which engineering decisions actually bought accuracy.

The eval set contains ~60 questions across three kinds: `factual`, `synthesis`,
and `unanswerable`. The unanswerable controls exist so that "correctly says the
material doesn't cover this" is a measurable behaviour rather than a hope.

---

## Three ideas worth reading the code for

**1. Provenance is atomic** (`app/ingest/base.py`)
Extractors emit `Block`s that already carry their exact location — PDF page +
normalised bbox, PPTX slide + shape, transcript `t_start`/`t_end`. The chunker may
only *merge* locators, never blur them, and never across a page boundary. If a
bbox is lost at extraction time no amount of downstream cleverness can render a
citation, so the tests in `tests/test_core.py` assert this directly.

**2. Transcript ↔ slide alignment** (`app/ingest/align.py`)
A lecturer moves through slides in order, so segment→slide is monotonic. That
makes it a constrained DTW over the segment × slide similarity matrix. Result: a
transcript chunk gains a slide number and a slide chunk gains a timestamp, so one
citation can say *"Lecture 7, slide 23 @ 06:52"* and the tutor can answer "what did
he actually **say** about this slide?"

**3. Answers are checked, not trusted** (`app/answer/verify.py`)
After generation, the answer is split into sentences; each sentence's own
citations are fed to a cheap judge that returns SUPPORTED / PARTIAL / UNSUPPORTED.
That's both a UI guardrail and the `unsupported_claim_rate` metric above.

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

One database does both relational and vector work. No separate vector store: the
RRF query in `app/retrieval/search.py` is a single round-trip.

## Stack

Python 3.12 · FastAPI · asyncpg · Postgres 16 + pgvector · PyMuPDF · python-pptx ·
faster-whisper · sentence-transformers (bge-m3 / bge-reranker-v2-m3) ·
Next.js + TypeScript + Tailwind · Docker · GitHub Actions

## Run it

```bash
cp .env.example .env          # add one API key
make up                       # postgres + api on :8000
curl localhost:8000/health

# create a course and upload a lecture
curl -X POST localhost:8000/courses -H 'content-type: application/json' \
     -d '{"name":"Algorithms"}'
curl -X POST localhost:8000/sources \
     -F course_id=<uuid> -F week=4 -F title="Lecture 7 — Recursion" \
     -F file=@lecture07.pdf

# ask
curl -X POST localhost:8000/ask -H 'content-type: application/json' \
     -d '{"question":"Explain recursion","course_id":"<uuid>","week":4,"mode":"simple"}'
```

## Build the eval set

```bash
python -m app.evaluation.build_set --course-id <uuid> --n 60 --unanswerable 12
# hand-review evalsets/candidates.jsonl — this step is not optional
python -m app.evaluation.build_set --course-id <uuid> --load evalsets/candidates.jsonl
make eval
```

## Status

- [x] PDF / PPTX / notes ingestion with locator-preserving chunking
- [x] Hybrid retrieval (pgvector + tsvector, RRF) with cross-encoder rerank
- [x] Grounded answering, citation parsing, per-sentence verification
- [x] Eval harness: recall@k, MRR, citation precision, unsupported-claim rate
- [x] Citation viewer (page render + bbox overlay, audio seek)
- [ ] Audio ingestion behind a job queue + slide alignment wired into ingest
- [ ] Topic extraction, quiz generation, mastery model (Elo-style θ per topic)
- [ ] Study-plan agent with tool access to the above

## Engineering notes

### Retrieval latency
| config | p50 | note |
|---|---|---|
| bge-reranker-v2-m3 (568M), cold | 431s | model loaded inside the request |
| bge-reranker-v2-m3, warmed at startup | 15.5s | CPU inference dominates |
| no rerank | 3.1s | embedding + SQL only |
| ms-marco-MiniLM-L-6-v2 (22M), warmed | 3.5s | reranker cost ~0.4s |

Swapping a 568M reranker for a 22M one cut reranking from ~12.4s to ~0.4s with
no change to the top-6 ordering on spot-checked queries. Recall impact is
measured in the eval suite below.

### Reasoning models are wrong for pipeline roles
Both the judge and the generator initially used a reasoning model. Thinking
tokens consumed the output budget: the judge returned empty responses
(JSONDecodeError on every call) and the generator emitted truncated answers with
reasoning traces leaking into the body. Non-reasoning variants fixed both. Model
names are config strings, not constants — one provider model was retired between
writing this and running it, and the fix was a single env var.

### The verifier only sees passage text
An early answer opened with "As covered in the Week 1 lecture..." and the judge
returned PARTIAL: correctly, since the passage contains no week metadata. The
generator can see citation labels the verifier cannot. Fix was to forbid
narrating provenance in prose — the citation objects carry it, and the verifier's
job stays purely factual entailment.

### Failed judge calls are not hallucinations
`unsupported_claim_rate` originally counted judge failures as unsupported
claims, reporting 0.778 when only 2 of 9 sentences had actually been checked.
UNKNOWN verdicts are now excluded from the denominator and surfaced separately
as `n_unknown`. An infrastructure error must never masquerade as a quality signal.

### First eval run (43 chunks, 6 verified factual questions, k=5)

| config | recall@5 | MRR |
|---|---|---|
| hybrid (vector + keyword, RRF) | 1.00 | 0.917 |
| hybrid + cross-encoder rerank | 1.00 | 1.00 |

Recall is saturated at this corpus size — with 43 chunks, top-5 almost always
contains the gold chunk, so the metric cannot discriminate. MRR still moves:
reranking promoted one gold chunk from rank 2 to rank 1. The reranker reorders
rather than recovers, which is what a cross-encoder is for.

Gold labels were hand-verified against source passages. One auto-generated
question was cut because its labelled passage did not contain the answer — a
single bad label out of seven would have shifted recall by ~14 points.

### Refusal on unanswerable controls

6 control questions were written to sound like the course but be answerable
from no chunk in it (Bayes' theorem, Poisson, variance of a continuous density,
expected value, joint CDFs, hypergeometric vs binomial). All six retrieved
plausible-looking probability material and all six were correctly refused.

| metric | value |
|---|---|
| refusal accuracy | 1.00 (6/6) |
| unsupported-claim rate on answered questions | 0.00 |

Refusing correctly is treated as a measurable behaviour here rather than an
assumption. The controls are the only reason that number exists.

### Eval, consolidated corpus (43 chunks, 4 sources, 6 verified factual questions, k=5)

| config | recall@5 | MRR |
|---|---|---|
| hybrid (vector + keyword, RRF) | 1.00 | 0.917 |
| hybrid + cross-encoder rerank | 1.00 | 1.00 |

Refusal accuracy on 6 unanswerable controls: 1.00.
Unsupported-claim rate on a spot-checked answer: 0.00 (5/5 sentences entailed).

Honest caveat: recall is saturated at this corpus size. With 43 chunks, top-5
almost always contains the gold chunk, so recall cannot discriminate between
configurations — only MRR moves. These numbers demonstrate that the harness
works end to end; they are not yet a strong benchmark of retrieval quality.
Re-running on a full semester of material is the next step.

### Ablation (43 chunks, 12 examples, k=5, retrieval only)

| config | recall@5 | MRR | p50 latency |
|---|---|---|---|
| hybrid (vector + keyword, RRF) | 1.00 | 0.917 | 820ms |
| + cross-encoder rerank | 1.00 | 1.00 | 5932ms |

Reranking promoted one gold chunk from rank 2 to rank 1 — 0.083 MRR for roughly
7x the latency under concurrent load (single-query latency is ~3.5s). Whether
that trade is worth it depends on corpus size; at 43 chunks it clearly is not,
and the ablation is in the repo so the decision can be revisited with data.

Every run is persisted to `eval_runs` with its git SHA and full retrieval
config, and every per-example result to `eval_results`. `GET /eval/runs` returns
the history, so a regression is diffable rather than remembered.

### Two bugs worth recording

**Concurrent model loads.** Lazy initialisation with no lock: eight concurrent
eval requests each saw `_model is None` and started building their own copy of a
568M embedding model. Memory ran out mid-load and torch left the weights on the
meta device, surfacing as `Cannot copy out of meta tensor` — an error that says
nothing about the actual cause. Fixed with double-checked locking plus loading
both models at startup, so no request ever races to build one.

**Gold labels were not portable.** `eval_examples.gold_chunk_ids` held bigserial
ids assigned at ingest time, so a fresh database — a colleague's laptop, a CI
runner — assigned different numbers to the same passages and every label
silently pointed at the wrong chunk. Gold labels are now exported as
`(source_title, ordinal)` and resolved to ids on import. A benchmark that only
works on the machine that created it is not a benchmark.

### Study planner: a known limitation

Urgency ranks a topic answered once (theta +0.30) above eleven topics never
assessed at all, because untested topics get a fixed retention floor of 0.25
while a tested topic's retention decays over the days to the exam. Recent
evidence of weakness outranking absence of evidence is defensible; a *correct*
answer outranking an untested topic is not.

All untested topics also tie at exactly 1.125, so their relative order is
arbitrary. A real course would break that tie on week proximity or chunk count.

Both are visible because the ranking is returned with the plan rather than
hidden inside a prompt — which is the argument for a deterministic planner over
asking a model to produce a timetable.

### Eval on a real corpus: CSC1021 (399 chunks, 5 lectures)

| config | recall@5 | MRR | p50 latency |
|---|---|---|---|
| hybrid (vector + keyword, RRF) | 0.938 | 0.875 | 606ms |
| + cross-encoder rerank | 0.938 | 0.875 | 4626ms |

16 hand-verified factual questions, 5 unanswerable controls. Unlike the 43-chunk
sample corpus, recall here is not saturated — the metric discriminates.

**Reranking contributed nothing on this corpus**, against +0.083 MRR on the
smaller one, for 8x the latency. Reranking only helps when fusion ordering is
wrong; here RRF already ranked gold first in most cases. Worth measuring per
corpus rather than assuming.

**The one failure is a chunking problem, not a retrieval one.** The question
"how does Round Robin turnaround compare to SJF?" has its answer in chunk 70,
which states it in one clear sentence — but that chunk is dominated by a Gantt
chart whose text extracted as `P1 P1 P1 P P P 1 1 1 0 18 30 26 14 4 7 10 22`.
The relevant sentence is ~12% of the chunk; the rest is diagram debris pulling
the embedding away from any prose query. Retrieval behaved correctly given a
poisoned chunk.

Filtering blocks by alphabetic-character ratio would fix this case, but would
also discard legitimate notation-heavy slides (`S = {H, T}`, formula
derivations). Left unfixed and documented rather than papered over with a
heuristic that trades one failure mode for another.

### Controls must be verified, not assumed

Eight unanswerable controls were hand-written for this corpus. Three —
banker's algorithm, TLB address translation, copy-on-write — turned out to be
covered in the lectures, scoring +7.33, +5.85 and +1.76 on the reranker. Loading
them unchecked would have reported refusal accuracy of 5/8 and suggested the
system hallucinates, when in fact it correctly answered three questions that
were mislabelled. A wrong benchmark is worse than no benchmark.

### Generation metrics, CSC1021 (6 questions)

| metric | value |
|---|---|
| citation precision (strict, vs gold labels) | 0.722 |
| citation precision (counting verified sources) | 1.000 |
| unsupported-claim rate | 0.056 |
| recall@5 / MRR | 1.00 / 1.00 |

Two citation-precision numbers, because the first was measuring the wrong thing.

Strict precision scores a citation correct only if it appears in the gold label,
which lists one chunk per question. But a concept usually spans consecutive
slides. Measured case: "why is a context switch pure overhead?" cited chunk 213
(gold) and 212, where 212 reads "a context switch occurs when the CPU switches
from one process to another" — a correct, relevant source. Scoring that 0.5
penalises better citation behaviour.

The relaxed metric counts a citation as correct if it is a gold chunk *or* if
the per-sentence entailment checker independently confirmed it supports the
sentence citing it. That is a genuine second signal, not a loosened threshold —
the judge never sees the gold labels.

Both are reported. The strict figure is a lower bound distorted by
single-chunk labelling; the relaxed figure says no citation was fabricated.

### Rate limiting belongs in one place

The eval initially failed on repeat runs with 429s. Rate limiting had grown up
in four places with four strategies — a semaphore in the verifier, a 5s pacer in
topic extraction, a semaphore in quiz generation, and nothing at all in the
answer path, which is why generation was the thing that died.

It now lives in `llm.py`, the single point every model call passes through:
one shared pacer (~13 req/min) plus retry-on-429 with escalating backoff. The
provider SDK's own retries fire within milliseconds and spend quota without
succeeding, so pacing at the source is the only thing that works.

Cost: eval p50 latency went 4.3s → 30.9s, since a run makes ~16 sequential
model calls. Interactive `/ask` is unaffected at ~4s — it makes one. The
unsupported-claim rate also improved (0.056 → 0.033) because judge calls that
previously died on 429s now complete: an infrastructure failure had been
degrading a quality metric.
