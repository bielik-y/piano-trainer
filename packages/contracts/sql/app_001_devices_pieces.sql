-- Данные приложения (app.sqlite): устройства и библиотека пьес (ARCHITECTURE §5.2, §8).
-- Миграция 1. Применяет API при запуске, см. apps/api/src/database/migrations.ts.

-- Анонимное устройство. Токен хранится только как sha256: показать его второй раз нельзя.
CREATE TABLE devices (
  id           TEXT PRIMARY KEY,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

-- Пьеса в библиотеке. Сервер — источник правды, телефон держит кэш и подтягивает изменения
-- по updated_at; удаление мягкое (deleted_at), чтобы кэш узнал об удалении.
CREATE TABLE pieces (
  id                    TEXT PRIMARY KEY,
  device_id             TEXT NOT NULL REFERENCES devices (id),
  title                 TEXT NOT NULL,
  composer              TEXT,
  -- title и composer в нижнем регистре для поиска: LOWER в SQLite не понимает кириллицу.
  search_text           TEXT NOT NULL,
  source_kind           TEXT NOT NULL CHECK (source_kind IN ('musicxml', 'mxl', 'omr')),
  -- Задача распознавания, из которой создана пьеса; одна задача — одна пьеса.
  omr_job_id            TEXT UNIQUE,
  -- Путь к MusicXML внутри папки пьесы.
  score_path            TEXT NOT NULL,
  measure_count         INTEGER NOT NULL,
  -- JSON-массив индексов тактов (с 0), которые не оцениваются: подозрительные после OMR.
  unscored_measures     TEXT NOT NULL DEFAULT '[]',
  time_signature        TEXT,
  time_signature_source TEXT CHECK (time_signature_source IN ('engine', 'inferred', 'user')),
  key_fifths            INTEGER,
  tempo_text            TEXT,
  tempo_bpm             INTEGER,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL,
  deleted_at            TEXT,
  last_practiced_at     TEXT
);

CREATE INDEX pieces_device_updated ON pieces (device_id, updated_at, id);
