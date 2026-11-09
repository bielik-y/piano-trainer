import type { DatabaseSync } from 'node:sqlite';
import { z } from 'zod';
import {
  OmrErrorCode,
  OmrJobStatus,
  OmrPage,
  OmrProgress,
  OmrReport,
  OmrSourceKind,
  StoredSourceFile,
} from '@piano/contracts';
import { OMR_MIGRATIONS } from '../../database/migrations.js';
import { openDatabase } from '../../database/sqlite.js';
import { JobRepository, type JobRecord, type NewJob } from './job-repository.js';

const Row = z.object({
  id: z.string(),
  status: OmrJobStatus,
  revision: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  source_kind: OmrSourceKind,
  source_files: z.string(),
  progress: z.string().nullable(),
  pages: z.string().nullable(),
  result: z.string().nullable(),
  error_code: OmrErrorCode.nullable(),
  error_message: z.string().nullable(),
  cancel_requested: z.number(),
});

const json = <T extends z.ZodType>(schema: T, value: string | null): z.infer<T> | null =>
  value === null ? null : schema.parse(JSON.parse(value));

const now = () => new Date().toISOString();

/**
 * Задачи в SQLite (ARCHITECTURE §7.1.1). Тот же файл открывает воркер: таблица одновременно
 * и очередь. WAL позволяет читать, пока воркер пишет. JSON-поля проверяются схемами контракта,
 * поэтому расхождение с моделями воркера сразу видно.
 */
export class SqliteJobRepository extends JobRepository {
  private readonly db: DatabaseSync;

  constructor(dbPath: string) {
    super();
    this.db = openDatabase(dbPath, OMR_MIGRATIONS);
  }

  close(): void {
    this.db.close();
  }

  insert(job: NewJob): JobRecord {
    const at = now();
    this.db
      .prepare(
        `INSERT INTO omr_jobs (id, status, created_at, updated_at, source_kind, source_files, pages)
         VALUES (?, 'queued', ?, ?, ?, ?, '[]')`,
      )
      .run(job.id, at, at, job.sourceKind, JSON.stringify(job.sourceFiles));
    return this.get(job.id)!;
  }

  get(id: string): JobRecord | null {
    const row = this.db.prepare('SELECT * FROM omr_jobs WHERE id = ?').get(id);
    return row ? toRecord(row) : null;
  }

  revision(id: string): number | null {
    const row = this.db.prepare('SELECT revision FROM omr_jobs WHERE id = ?').get(id) as
      | { revision: number }
      | undefined;
    return row ? row.revision : null;
  }

  list(limit: number): JobRecord[] {
    return this.db
      .prepare('SELECT * FROM omr_jobs ORDER BY created_at DESC, id DESC LIMIT ?')
      .all(limit)
      .map(toRecord);
  }

  cancelQueued(id: string): boolean {
    const at = now();
    const { changes } = this.db
      .prepare(
        `UPDATE omr_jobs SET status = 'cancelled', cancel_requested = 1, finished_at = ?,
           updated_at = ?, revision = revision + 1
         WHERE id = ? AND status = 'queued'`,
      )
      .run(at, at, id);
    return changes > 0;
  }

  requestCancel(id: string): boolean {
    const { changes } = this.db
      .prepare(
        `UPDATE omr_jobs SET cancel_requested = 1, updated_at = ?, revision = revision + 1
         WHERE id = ? AND status = 'processing' AND cancel_requested = 0`,
      )
      .run(now(), id);
    return changes > 0;
  }

  deleteFinishedBefore(before: string): string[] {
    const rows = this.db
      .prepare(
        `DELETE FROM omr_jobs WHERE status IN ('done', 'failed', 'cancelled') AND finished_at < ?
         RETURNING id`,
      )
      .all(before) as { id: string }[];
    return rows.map((r) => r.id);
  }
}

function toRecord(raw: unknown): JobRecord {
  const row = Row.parse(raw);
  return {
    id: row.id,
    status: row.status,
    revision: row.revision,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    sourceKind: row.source_kind,
    sourceFiles: z.array(StoredSourceFile).parse(JSON.parse(row.source_files)),
    progress: json(OmrProgress, row.progress),
    pages: json(z.array(OmrPage), row.pages) ?? [],
    result: json(OmrReport, row.result),
    error: row.error_code ? { code: row.error_code, message: row.error_message ?? '' } : null,
    cancelRequested: row.cancel_requested !== 0,
  };
}
