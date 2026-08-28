# Frontend

Next.js 14 (app router) + TypeScript + Tailwind.

```bash
cp .env.local.example .env.local   # points at http://localhost:8000
npm install
npm run dev                        # http://localhost:3000
```

The backend must be running (`make up` in the repo root). CORS is already
configured for `localhost:3000`.

## What's here

- `app/page.tsx` — ask form, mode + week filters, answer, evidence panel
- `app/components/CitationViewer.tsx` — renders the cited PDF page and draws the
  bbox region; seeks the audio player for transcript citations
- `app/components/AnswerView.tsx` — `[n]` markers as clickable chips, the
  per-sentence grounding verdicts, and the retrieved-passage list
- `app/lib/api.ts` — typed client for the FastAPI backend
