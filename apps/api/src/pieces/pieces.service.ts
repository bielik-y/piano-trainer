import { HttpStatus, Inject, Injectable, Logger } from '@nestjs/common';
import { Piece, type CreatePieceFromOmr, type PieceList, type UpdatePiece } from '@piano/contracts';
import { ApiException, notFound } from '../common/api-exception.js';
import { uuidv7 } from '../common/uuid.js';
import { OmrService } from '../omr/omr.service.js';
import { FileStorage, PIECE_FILES } from '../storage/file-storage.js';
import { PieceRepository, type PieceQuery, type PieceRecord } from './piece-repository.js';

const SCORE_PATH = 'score.musicxml';
const UNTITLED = 'Без названия';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface ListParams {
  q?: string;
  updatedSince?: string;
  cursor?: string;
  limit: number;
}

@Injectable()
export class PiecesService {
  private readonly log = new Logger(PiecesService.name);

  constructor(
    // Токены указаны явно: Vitest не генерирует метаданные типов для DI.
    @Inject(PieceRepository) private readonly pieces: PieceRepository,
    @Inject(PIECE_FILES) private readonly files: FileStorage,
    @Inject(OmrService) private readonly omr: OmrService,
  ) {}

  /**
   * «Добавить в библиотеку» из результата распознавания. MusicXML копируется к пьесе: задачи
   * удаляются через OMR_RETENTION_DAYS, а пьеса остаётся. Повторный вызов для той же задачи
   * возвращает уже созданную пьесу (удалённую — восстанавливает), created = false.
   */
  async createFromOmr(
    deviceId: string,
    body: CreatePieceFromOmr,
  ): Promise<{ piece: Piece; created: boolean }> {
    const existing = this.existingForJob(deviceId, body.jobId);
    if (existing) return { piece: existing, created: false };

    const { report, musicXml } = await this.omr.result(deviceId, body.jobId);
    const id = uuidv7();
    await this.files.write(id, SCORE_PATH, musicXml);
    const record = this.pieces.insert({
      id,
      deviceId,
      title: body.title ?? (report.title?.trim() || UNTITLED),
      composer:
        body.composer === undefined ? report.composer?.trim() || null : body.composer || null,
      sourceKind: 'omr',
      omrJobId: body.jobId,
      scorePath: SCORE_PATH,
      measureCount: report.measureCount,
      unscoredMeasures: report.suspiciousMeasures.map((m) => m.index),
      timeSignature: report.timeSignature,
      timeSignatureSource: report.timeSignatureSource,
      keyFifths: report.keyFifths,
      tempoText: report.tempoText,
      tempoBpm: report.tempoBpm,
      createdAt: new Date().toISOString(),
    });
    if (!record) {
      // Параллельный запрос успел создать пьесу из этой задачи первым.
      await this.files.remove(id);
      const winner = this.existingForJob(deviceId, body.jobId);
      if (!winner) throw new Error(`пьеса из задачи ${body.jobId} пропала`);
      return { piece: winner, created: false };
    }
    this.log.log(`${id}: добавлена из задачи ${body.jobId}`);
    return { piece: toPiece(record), created: true };
  }

  get(deviceId: string, id: string): Piece {
    return toPiece(this.live(deviceId, id));
  }

  list(deviceId: string, params: ListParams): PieceList {
    const serverTime = new Date().toISOString();
    const query: PieceQuery = {
      deviceId,
      q: params.q?.trim() || undefined,
      updatedSince: params.updatedSince,
      after: params.cursor === undefined ? undefined : decodeCursor(params.cursor),
      limit: params.limit + 1,
    };
    const records = this.pieces.list(query);
    const page = records.slice(0, params.limit);
    const last = page.at(-1);
    return {
      items: page.map(toPiece),
      nextCursor: records.length > params.limit && last ? encodeCursor(last) : null,
      serverTime,
    };
  }

  update(deviceId: string, id: string, body: UpdatePiece): Piece {
    this.live(deviceId, id);
    const record = this.pieces.update(
      id,
      {
        title: body.title,
        composer: body.composer === undefined ? undefined : body.composer || null,
      },
      new Date().toISOString(),
    );
    return toPiece(record!);
  }

  /** Мягкое удаление; повторное — без ошибки. Файл партитуры остаётся. */
  remove(deviceId: string, id: string): void {
    const record = this.owned(deviceId, id);
    if (record.deletedAt) return;
    this.pieces.update(id, { deletedAt: new Date().toISOString() }, new Date().toISOString());
  }

  async score(deviceId: string, id: string) {
    const record = this.live(deviceId, id);
    const data = await this.files.read(id, record.scorePath);
    if (!data) throw notFound('Файл партитуры не найден');
    return {
      ...data,
      // Партитура пьесы пока не меняется после создания, поэтому id и размера достаточно.
      etag: `"${id}-${data.size}"`,
      contentType: 'application/vnd.recordare.musicxml+xml',
      fileName: `${id}.musicxml`,
    };
  }

  private existingForJob(deviceId: string, jobId: string): Piece | null {
    const existing = this.pieces.findByOmrJob(jobId);
    if (!existing || existing.deviceId !== deviceId) return null;
    if (!existing.deletedAt) return toPiece(existing);
    const at = new Date().toISOString();
    return toPiece(this.pieces.update(existing.id, { deletedAt: null }, at)!);
  }

  /** Пьеса устройства, в том числе удалённая. Чужая неотличима от несуществующей: 404. */
  private owned(deviceId: string, id: string): PieceRecord {
    const record = UUID.test(id) ? this.pieces.get(id) : null;
    if (!record || record.deviceId !== deviceId) throw notFound('Пьеса не найдена');
    return record;
  }

  /** Неудалённая пьеса устройства. */
  private live(deviceId: string, id: string): PieceRecord {
    const record = this.owned(deviceId, id);
    if (record.deletedAt) throw notFound('Пьеса удалена');
    return record;
  }
}

function toPiece(record: PieceRecord): Piece {
  return Piece.parse({
    id: record.id,
    title: record.title,
    composer: record.composer,
    sourceKind: record.sourceKind,
    omrJobId: record.omrJobId,
    measureCount: record.measureCount,
    unscoredMeasures: record.unscoredMeasures,
    timeSignature: record.timeSignature,
    timeSignatureSource: record.timeSignatureSource,
    keyFifths: record.keyFifths,
    tempoText: record.tempoText,
    tempoBpm: record.tempoBpm,
    scoreUrl: `/v1/pieces/${record.id}/score.musicxml`,
    createdAt: record.createdAt,
    updatedAt: record.updatedAt,
    deletedAt: record.deletedAt,
    lastPracticedAt: record.lastPracticedAt,
  });
}

function encodeCursor(record: PieceRecord): string {
  return Buffer.from(JSON.stringify([record.updatedAt, record.id])).toString('base64url');
}

function decodeCursor(cursor: string): { updatedAt: string; id: string } {
  try {
    const [updatedAt, id] = JSON.parse(Buffer.from(cursor, 'base64url').toString()) as unknown[];
    if (typeof updatedAt === 'string' && typeof id === 'string') return { updatedAt, id };
  } catch {
    // ниже — общая ошибка
  }
  throw new ApiException(
    HttpStatus.BAD_REQUEST,
    'invalid_request',
    'cursor: передайте nextCursor из прошлого ответа',
  );
}
