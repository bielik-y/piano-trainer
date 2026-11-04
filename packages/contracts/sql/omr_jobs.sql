-- Задачи распознавания в локальном режиме (ARCHITECTURE §7.1.1).
-- Таблицу создаёт API при запуске; воркер её только читает и обновляет.
-- JSON-поля соответствуют схемам из src/index.ts: progress — OmrProgress, pages — OmrPage[],
-- result — OmrReport, source_files — StoredSourceFile[].
CREATE TABLE IF NOT EXISTS omr_jobs (
  id               TEXT PRIMARY KEY,
  status           TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'done', 'failed', 'cancelled')),
  -- Растёт при каждом изменении записи: по нему SSE понимает, что пора отправить событие.
  revision         INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  started_at       TEXT,
  finished_at      TEXT,
  source_kind      TEXT NOT NULL CHECK (source_kind IN ('pdf', 'images')),
  source_files     TEXT NOT NULL,
  progress         TEXT,
  pages            TEXT,
  result           TEXT,
  error_code       TEXT,
  error_message    TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS omr_jobs_status_created ON omr_jobs (status, created_at);
