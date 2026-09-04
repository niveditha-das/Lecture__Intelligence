// ---------------------------------------------------------------------------
// Study loop: topics, quizzes, mastery, plans
//
// Kept separate from api.ts so the ask flow and the study flow can be read
// independently. `get` is re-declared here rather than exported from api.ts —
// a two-line helper is cheaper than widening that module's public surface.
// ---------------------------------------------------------------------------

import { API } from "./api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export type Topic = {
  id: string;
  name: string;
  week: number | null;
  n_chunks: number;
  n_questions: number;
};

export type QuizQuestion = {
  question_id: string;
  topic_id: string;
  topic: string;
  stem: string;
  options: Record<string, string>;
  difficulty: number;
  grounding_chunk_ids: number[];
};

export type AnswerResult = {
  correct: boolean;
  answer: string;
  rationale: string | null;
  topic: string;
  grounding_chunk_ids: number[];
  theta_before: number;
  theta_after: number;
  predicted_p: number;
  error?: string;
};

export type MasteryRow = {
  topic_id: string;
  topic: string;
  week: number | null;
  theta: number;
  n_seen: number;
  n_correct: number;
  n_questions: number;
  days_since_review: number | null;
  retention: number | null;
};

export type PlanItem = {
  day: string;
  topic_id: string;
  topic: string;
  activity: string;
  minutes: number;
  rationale: string;
};

export type Plan = {
  plan_id: string;
  exam_date: string;
  days: number;
  minutes_per_day: number;
  n_items: number;
  ranking: { topic: string; urgency: number; theta: number; n_seen: number }[];
  items: PlanItem[];
  error?: string;
};

export const getTopics = (courseId: string) =>
  get<Topic[]>(`/study/topics?course_id=${courseId}`);

export const getMastery = (courseId: string) =>
  get<MasteryRow[]>(`/study/mastery?course_id=${courseId}`);

export const getNextQuestions = (courseId: string, n = 5) =>
  get<QuizQuestion[]>(`/study/quiz/next?course_id=${courseId}&n=${n}`);

export async function answerQuestion(
  questionId: string,
  chosen: string,
  msTaken?: number,
): Promise<AnswerResult> {
  const res = await fetch(`${API}/study/quiz/answer`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      question_id: questionId,
      chosen,
      ms_taken: msTaken ?? null,
    }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export async function buildPlan(
  courseId: string,
  examDate: string,
  minutesPerDay: number,
): Promise<Plan> {
  const res = await fetch(`${API}/study/plan`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      course_id: courseId,
      exam_date: examDate,
      minutes_per_day: minutesPerDay,
    }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

/** theta runs roughly -1.5..1.5; map to 0..1 for a progress bar. */
export function thetaFraction(theta: number): number {
  return Math.max(0, Math.min(1, (theta + 1.5) / 3));
}
// --- written questions (append to app/lib/study-api.ts) --------------------

export type WrittenQuestion = {
  question_id: string;
  topic_id: string;
  topic: string;
  stem: string;
  model_answer: string;
  marking_points: string[];
  difficulty: number;
  grounding_chunk_ids: number[];
};

export type Counts = { mcq: number; short: number; long: number; topics: number };

export const getCounts = (courseId: string) =>
  get<Counts>(`/study/counts?course_id=${courseId}`);

export const getWritten = (courseId: string, format: "short" | "long", n = 3) =>
  get<WrittenQuestion[]>(
    `/study/questions/next?course_id=${courseId}&format=${format}&n=${n}`,
  );

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const generateMcq = (courseId: string, perTopic = 3, maxTopics = 6) =>
  post<{ questions_created: number; topics_processed: number }>(
    "/study/quiz/generate",
    { course_id: courseId, per_topic: perTopic, max_topics: maxTopics },
  );

export const generateWritten = (
  courseId: string,
  format: "short" | "long",
  perTopic = 2,
  maxTopics = 5,
) =>
  post<{ questions_created: number; topics_processed: number }>(
    "/study/questions/generate",
    { course_id: courseId, format, per_topic: perTopic, max_topics: maxTopics },
  );

export const selfAssess = (questionId: string, correct: boolean) =>
  post<AnswerResult>("/study/questions/assess", {
    question_id: questionId,
    correct,
  });
