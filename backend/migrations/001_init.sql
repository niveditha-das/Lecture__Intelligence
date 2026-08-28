-- Lecture Intelligence Platform :: initial schema
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE courses (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sources (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id    uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    kind         text NOT NULL CHECK (kind IN ('pdf','pptx','audio','notes')),
    title        text NOT NULL,
    week         int,
    storage_uri  text NOT NULL,          -- original file: needed to RENDER citations
    status       text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','processing','ready','failed')),
    error        text,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON sources (course_id, week);

-- One row per retrievable unit. `locator` is the whole point of this project:
--   pdf   -> {"page": 23, "regions": [{"page":23,"bbox":[x0,y0,x1,y1]}]}   bbox normalised 0..1
--   pptx  -> {"slide": 23, "shapes": [4,5]}
--   audio -> {"t_start": 412.3, "t_end": 448.1, "slide": 23}
--   notes -> {"line_start": 40, "line_end": 58}
CREATE TABLE chunks (
    id          bigserial PRIMARY KEY,
    source_id   uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    course_id   uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,  -- denormalised for filtering
    week        int,
    ordinal     int NOT NULL,
    text        text NOT NULL,
    n_tokens    int NOT NULL DEFAULT 0,
    locator     jsonb NOT NULL,
    embedding   vector(1024),
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX chunks_course_idx    ON chunks (course_id, week);
CREATE UNIQUE INDEX chunks_src_ord_idx ON chunks (source_id, ordinal);

-- ---------- topics / quizzes / mastery (steps 4-5) ----------
CREATE TABLE topics (
    id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name      text NOT NULL,
    week      int,
    UNIQUE (course_id, name)
);

CREATE TABLE chunk_topics (
    chunk_id bigint NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    topic_id uuid   NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    weight   real   NOT NULL DEFAULT 1.0,
    PRIMARY KEY (chunk_id, topic_id)
);

CREATE TABLE quiz_questions (
    id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            uuid REFERENCES topics(id) ON DELETE CASCADE,
    stem                text NOT NULL,
    options             jsonb NOT NULL,
    answer              text NOT NULL,
    rationale           text,
    difficulty          real NOT NULL DEFAULT 0.0,   -- `b` in the logistic model
    grounding_chunk_ids bigint[] NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attempts (
    id          bigserial PRIMARY KEY,
    user_id     uuid NOT NULL,
    question_id uuid NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    correct     boolean NOT NULL,
    ms_taken    int,
    answered_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mastery (
    user_id   uuid NOT NULL,
    topic_id  uuid NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    theta     real NOT NULL DEFAULT 0.0,        -- ability estimate
    n_seen    int  NOT NULL DEFAULT 0,
    last_seen timestamptz,
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE study_plans (
    id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id   uuid NOT NULL,
    course_id uuid NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    exam_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE study_plan_items (
    id        bigserial PRIMARY KEY,
    plan_id   uuid NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    day       date NOT NULL,
    topic_id  uuid REFERENCES topics(id) ON DELETE SET NULL,
    activity  text NOT NULL,            -- review | quiz | practice
    minutes   int  NOT NULL DEFAULT 30,
    rationale text,
    done      boolean NOT NULL DEFAULT false
);

-- ---------- evaluation harness (the part recruiters read) ----------
CREATE TABLE eval_examples (
    id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id      uuid REFERENCES courses(id) ON DELETE CASCADE,
    question       text NOT NULL,
    gold_chunk_ids bigint[] NOT NULL DEFAULT '{}',
    gold_answer    text,
    kind           text NOT NULL DEFAULT 'factual'
                   CHECK (kind IN ('factual','synthesis','unanswerable')),
    week           int
);

CREATE TABLE eval_runs (
    id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    git_sha    text,
    label      text,
    config     jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    metrics    jsonb
);

CREATE TABLE eval_results (
    run_id             uuid NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    example_id         uuid NOT NULL REFERENCES eval_examples(id) ON DELETE CASCADE,
    retrieved_ids      bigint[] NOT NULL DEFAULT '{}',
    recall_at_k        real,
    mrr                real,
    citation_precision real,
    supported_ratio    real,
    refused            boolean,
    answer             text,
    latency_ms         int,
    PRIMARY KEY (run_id, example_id)
);
