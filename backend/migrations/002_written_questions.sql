-- Written question formats: short answer and long answer, alongside MCQ.
--
-- Reuses quiz_questions rather than adding a table: a question is a question,
-- and mastery updates, topic links and grounding all work identically. Only the
-- shape of the expected answer differs.

ALTER TABLE quiz_questions
    ADD COLUMN IF NOT EXISTS format text NOT NULL DEFAULT 'mcq';

ALTER TABLE quiz_questions
    ADD COLUMN IF NOT EXISTS model_answer text;

ALTER TABLE quiz_questions
    ADD COLUMN IF NOT EXISTS marking_points jsonb NOT NULL DEFAULT '[]'::jsonb;

-- MCQ keeps its options; written formats have none.
ALTER TABLE quiz_questions ALTER COLUMN options SET DEFAULT '{}'::jsonb;
ALTER TABLE quiz_questions ALTER COLUMN answer DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'quiz_questions_format_check'
    ) THEN
        ALTER TABLE quiz_questions
            ADD CONSTRAINT quiz_questions_format_check
            CHECK (format IN ('mcq', 'short', 'long'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS quiz_questions_format_idx ON quiz_questions (topic_id, format);

-- Written answers are self-assessed, so the attempt needs to record that it was
-- graded by the student rather than by string comparison.
ALTER TABLE attempts
    ADD COLUMN IF NOT EXISTS self_assessed boolean NOT NULL DEFAULT false;
