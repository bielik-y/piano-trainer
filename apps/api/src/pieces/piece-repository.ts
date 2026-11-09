import type { DatabaseSync, SQLInputValue } from 'node:sqlite';
import { z } from 'zod';
import { PieceSourceKind, TimeSignatureSource } from '@piano/contracts';

/** Запись пьесы в хранилище (без ссылок — их добавляет сервис). */
export interface PieceRecord {
  id: string;
  deviceId: string;
  title: string;
  composer: string | null;
  sourceKind: PieceSourceKind;
  omrJobId: string | null;
  /** Путь к MusicXML внутри папки пьесы. */
  scorePath: string;
  measureCount: number;
  unscoredMeasures: number[];
  timeSignature: string | null;
  timeSignatureSource: TimeSignatureSource | null;
  keyFifths: number | null;
  tempoText: string | null;
  tempoBpm: number | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  lastPracticedAt: string | null;
}

export type NewPiece = Omit<PieceRecord, 'updatedAt' | 'deletedAt' | 'lastPracticedAt'>;

export interface PieceQuery {
  deviceId: string;
  /** Подстрока названия или автора, без учёта регистра. */
  q?: string;
  /** Изменённые не раньше этого момента, включая удалённые. Без него — только живые. */
  updatedSince?: string;
  /** Продолжить после этой пьесы (порядок — updatedAt, id). */
  after?: { updatedAt: string; id: string };
  limit: number;
}

export interface PiecePatch {
  title?: string;
  composer?: string | null;
  deletedAt?: string | null;
}

/**
 * Пьесы. Локально — app.sqlite, на сервере — Postgres. Класс — и интерфейс, и токен DI.
 */
export abstract class PieceRepository {
  /** null — пьеса из этой задачи уже есть (omr_job_id уникален). */
  abstract insert(piece: NewPiece): PieceRecord | null;
  abstract get(id: string): PieceRecord | null;
  abstract findByOmrJob(omrJobId: string): PieceRecord | null;
  abstract list(query: PieceQuery): PieceRecord[];
  /** Меняет поля и updated_at; null — пьесы нет. */
  abstract update(id: string, patch: PiecePatch, at: string): PieceRecord | null;
}

const Row = z.object({
  id: z.string(),
  device_id: z.string(),
  title: z.string(),
  composer: z.string().nullable(),
  source_kind: PieceSourceKind,
  omr_job_id: z.string().nullable(),
  score_path: z.string(),
  measure_count: z.number(),
  unscored_measures: z.string(),
  time_signature: z.string().nullable(),
  time_signature_source: TimeSignatureSource.nullable(),
  key_fifths: z.number().nullable(),
  tempo_text: z.string().nullable(),
  tempo_bpm: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  deleted_at: z.string().nullable(),
  last_practiced_at: z.string().nullable(),
});

function toRecord(raw: unknown): PieceRecord {
  const row = Row.parse(raw);
  return {
    id: row.id,
    deviceId: row.device_id,
    title: row.title,
    composer: row.composer,
    sourceKind: row.source_kind,
    omrJobId: row.omr_job_id,
    scorePath: row.score_path,
    measureCount: row.measure_count,
    unscoredMeasures: z.array(z.number().int()).parse(JSON.parse(row.unscored_measures)),
    timeSignature: row.time_signature,
    timeSignatureSource: row.time_signature_source,
    keyFifths: row.key_fifths,
    tempoText: row.tempo_text,
    tempoBpm: row.tempo_bpm,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    deletedAt: row.deleted_at,
    lastPracticedAt: row.last_practiced_at,
  };
}

/** Текст для поиска: LOWER в SQLite не знает кириллицы, поэтому регистр снимается здесь. */
const searchText = (title: string, composer: string | null) =>
  `${title}\n${composer ?? ''}`.toLowerCase();

const escapeLike = (s: string) => s.replace(/[\\%_]/g, (c) => `\\${c}`);

export class SqlitePieceRepository extends PieceRepository {
  constructor(private readonly db: DatabaseSync) {
    super();
  }

  insert(piece: NewPiece): PieceRecord | null {
    try {
      this.db
        .prepare(
          `INSERT INTO pieces (id, device_id, title, composer, search_text, source_kind,
             omr_job_id, score_path, measure_count, unscored_measures, time_signature,
             time_signature_source, key_fifths, tempo_text, tempo_bpm, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          piece.id,
          piece.deviceId,
          piece.title,
          piece.composer,
          searchText(piece.title, piece.composer),
          piece.sourceKind,
          piece.omrJobId,
          piece.scorePath,
          piece.measureCount,
          JSON.stringify(piece.unscoredMeasures),
          piece.timeSignature,
          piece.timeSignatureSource,
          piece.keyFifths,
          piece.tempoText,
          piece.tempoBpm,
          piece.createdAt,
          piece.createdAt,
        );
    } catch (e) {
      if (String(e).includes('UNIQUE constraint failed: pieces.omr_job_id')) return null;
      throw e;
    }
    return this.get(piece.id);
  }

  get(id: string): PieceRecord | null {
    const row = this.db.prepare('SELECT * FROM pieces WHERE id = ?').get(id);
    return row ? toRecord(row) : null;
  }

  findByOmrJob(omrJobId: string): PieceRecord | null {
    const row = this.db.prepare('SELECT * FROM pieces WHERE omr_job_id = ?').get(omrJobId);
    return row ? toRecord(row) : null;
  }

  list(query: PieceQuery): PieceRecord[] {
    const where = ['device_id = ?'];
    const params: SQLInputValue[] = [query.deviceId];
    if (query.updatedSince === undefined) {
      where.push('deleted_at IS NULL');
    } else {
      where.push('updated_at >= ?');
      params.push(query.updatedSince);
    }
    if (query.q) {
      where.push("search_text LIKE ? ESCAPE '\\'");
      params.push(`%${escapeLike(query.q.toLowerCase())}%`);
    }
    if (query.after) {
      where.push('(updated_at > ? OR (updated_at = ? AND id > ?))');
      params.push(query.after.updatedAt, query.after.updatedAt, query.after.id);
    }
    params.push(query.limit);
    return this.db
      .prepare(`SELECT * FROM pieces WHERE ${where.join(' AND ')} ORDER BY updated_at, id LIMIT ?`)
      .all(...params)
      .map(toRecord);
  }

  update(id: string, patch: PiecePatch, at: string): PieceRecord | null {
    const current = this.get(id);
    if (!current) return null;
    const title = patch.title ?? current.title;
    const composer = patch.composer === undefined ? current.composer : patch.composer;
    const deletedAt = patch.deletedAt === undefined ? current.deletedAt : patch.deletedAt;
    this.db
      .prepare(
        `UPDATE pieces SET title = ?, composer = ?, search_text = ?, deleted_at = ?,
           updated_at = ?
         WHERE id = ?`,
      )
      .run(title, composer, searchText(title, composer), deletedAt, at, id);
    return this.get(id);
  }
}
