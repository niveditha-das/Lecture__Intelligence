export const API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Region = { page: number; bbox: [number, number, number, number] };

export type Locator = {
  page?: number;
  slide?: number;
  regions?: Region[];
  t_start?: number;
  t_end?: number;
  line_start?: number;
  line_end?: number;
  section?: string;
};

export type Citation = {
  n: number;
  chunk_id: number;
  source_id: string;
  source_title: string;
  source_kind: "pdf" | "pptx" | "audio" | "notes";
  label: string;
  locator: Locator;
};

export type Verdict =
  | "SUPPORTED"
  | "PARTIAL"
  | "UNSUPPORTED"
  | "UNCITED"
  | "UNKNOWN";

export type SentenceCheck = {
  sentence: string;
  citations: number[];
  verdict: Verdict;
  why?: string;
};

export type Verification = {
  sentences: SentenceCheck[];
  n_sentences: number;
  n_checked: number;
  n_unknown?: number;
  supported_ratio: number | null;
  uncited_sentences: number;
  unsupported_claim_rate: number | null;
};

export type Hit = {
  chunk_id: number;
  label: string;
  rrf: number;
  rerank_score: number | null;
  arms: string[];
};

export type AskResponse = {
  answer: string;
  citations: Citation[];
  refused: boolean;
  verification: Verification | null;
  hits: Hit[];
};

export type Source = {
  id: string;
  course_id: string;
  kind: string;
  title: string;
  week: number | null;
  status: string;
  error: string | null;
};

export type Course = { id: string; name: string };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const getCourses = () => get<Course[]>("/courses");

export const getSources = (courseId?: string) =>
  get<Source[]>(`/sources${courseId ? `?course_id=${courseId}` : ""}`);

export const getHealth = () =>
  get<{ ok: boolean; chunks: number; sources_ready: number }>("/health");

export async function ask(body: {
  question: string;
  course_id?: string;
  week?: number | null;
  mode: string;
}): Promise<AskResponse> {
  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...body, week: body.week ?? null }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export function timecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
