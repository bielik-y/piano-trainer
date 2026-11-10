import {
  HttpStatus,
  Inject,
  Injectable,
  Logger,
  type OnModuleDestroy,
  type OnModuleInit,
} from '@nestjs/common';
import { createHash, randomInt } from 'node:crypto';
import type { Readable } from 'node:stream';
import { OmrJob, OmrJobOptions, type OmrReport, type StoredSourceFile } from '@piano/contracts';
import { ApiException, notFound } from '../common/api-exception.js';
import { uuidv7 } from '../common/uuid.js';
import { OMR_CONFIG, type OmrConfig } from '../config.js';
import { sniffFileType, type SniffedType } from './file-type.js';
import { FileStorage, JOB_FILES } from '../storage/file-storage.js';
import { JobQueue } from './storage/job-queue.js';
import { JobRepository, type JobRecord } from './storage/job-repository.js';

/** Часть multipart-запроса: файл или текстовое поле (параметр распознавания). */
export type UploadPart =
  | { kind: 'file'; filename: string; stream: Readable }
  | { kind: 'field'; name: string; value: string };

/** Поля multipart, которые становятся OmrJobOptions. Остальные поля игнорируются. */
const OPTION_FIELDS = new Set<string>(OmrJobOptions.keyof().options);

export type DownloadKind = 'musicxml' | 'report';

const DOWNLOADS: Record<DownloadKind, { path: string; contentType: string; ext: string }> = {
  musicxml: {
    path: 'result.musicxml',
    contentType: 'application/vnd.recordare.musicxml+xml',
    ext: 'musicxml',
  },
  report: { path: 'report.json', contentType: 'application/json; charset=utf-8', ext: 'json' },
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

@Injectable()
export class OmrService implements OnModuleInit, OnModuleDestroy {
  private readonly log = new Logger(OmrService.name);
  private purgeTimer?: NodeJS.Timeout;

  constructor(
    // Токены указаны явно: Vitest не генерирует метаданные типов для DI.
    @Inject(OMR_CONFIG) private readonly config: OmrConfig,
    @Inject(JobRepository) private readonly jobs: JobRepository,
    @Inject(JOB_FILES) private readonly files: FileStorage,
    @Inject(JobQueue) private readonly queue: JobQueue,
  ) {}

  onModuleInit() {
    void this.purgeOld();
    this.purgeTimer = setInterval(() => void this.purgeOld(), 60 * 60 * 1000);
    this.purgeTimer.unref();
  }

  onModuleDestroy() {
    clearInterval(this.purgeTimer);
  }

  async create(deviceId: string, parts: AsyncIterable<UploadPart>): Promise<OmrJob> {
    const id = uuidv7();
    const stored: (StoredSourceFile & { type: SniffedType })[] = [];
    const fields: Record<string, string> = {};
    let options: OmrJobOptions;
    try {
      for await (const upload of parts) {
        if (upload.kind === 'field') {
          if (OPTION_FIELDS.has(upload.name)) fields[upload.name] = upload.value;
          continue;
        }
        if (stored.length >= this.config.maxImages) {
          upload.stream.resume();
          throw tooManyFiles(this.config.maxImages);
        }
        const path = `source/${String(stored.length + 1).padStart(2, '0')}`;
        let size: number;
        try {
          size = await this.files.write(id, path, upload.stream);
        } catch (e) {
          if ((e as { code?: string }).code === 'FST_REQ_FILE_TOO_LARGE') {
            throw new ApiException(
              HttpStatus.PAYLOAD_TOO_LARGE,
              'file_too_large',
              `Файл ${upload.filename} больше ${Math.round(this.config.maxFileBytes / 2 ** 20)} МБ`,
            );
          }
          throw e;
        }
        const type = size > 0 ? sniffFileType(await this.files.readHead(id, path, 16)) : null;
        if (!type) {
          throw new ApiException(
            HttpStatus.UNSUPPORTED_MEDIA_TYPE,
            'unsupported_file_type',
            `Файл ${upload.filename}: поддерживаются PDF, JPEG, PNG и HEIC`,
          );
        }
        stored.push({ name: upload.filename, size, contentType: type.contentType, path, type });
      }
      if (stored.length === 0) {
        throw new ApiException(
          HttpStatus.BAD_REQUEST,
          'no_files',
          'Добавьте файлы в поле files: 1 PDF или от 1 до 10 фото',
        );
      }
      const pdfs = stored.filter((f) => f.type.kind === 'pdf').length;
      if (pdfs > 0 && stored.length > 1) {
        throw new ApiException(
          HttpStatus.BAD_REQUEST,
          'mixed_sources',
          'Можно загрузить либо один PDF, либо фото — не вместе и не несколько PDF',
        );
      }
      options = parseOptions(fields);
    } catch (e) {
      await this.files.remove(id);
      throw e;
    }

    const record = this.jobs.insert({
      id,
      deviceId,
      sourceKind: stored[0]!.type.kind === 'pdf' ? 'pdf' : 'images',
      sourceFiles: stored.map(({ type: _type, ...file }) => file),
      options,
      hue: randomInt(360),
    });
    await this.queue.enqueue(id);
    this.log.log(`${id}: создана, файлов ${stored.length}`);
    return this.toJob(record);
  }

  get(deviceId: string, id: string): OmrJob {
    return this.toJob(this.record(deviceId, id));
  }

  /**
   * Ревизия задачи без полного чтения; null — задачи нет. Владельца не проверяет:
   * SSE вызывает её после get(), который уже проверил.
   */
  revision(id: string): number | null {
    return UUID.test(id) ? this.jobs.revision(id) : null;
  }

  list(deviceId: string, limit: number, inbox = false): OmrJob[] {
    return this.jobs.list(deviceId, limit, inbox).map((r) => this.toJob(r));
  }

  /**
   * Убрать карточку задачи с экрана библиотеки. Только у завершённой задачи: в работе её
   * сначала отменяют. Повторный вызов — без ошибки.
   */
  dismiss(deviceId: string, id: string): OmrJob {
    const record = this.record(deviceId, id);
    if (record.status === 'queued' || record.status === 'processing') {
      throw new ApiException(
        HttpStatus.CONFLICT,
        'not_finished',
        'Задача ещё распознаётся: сначала отмените её (POST …/cancel)',
      );
    }
    this.jobs.dismiss(id);
    return this.get(deviceId, id);
  }

  cancel(deviceId: string, id: string): OmrJob {
    const record = this.record(deviceId, id);
    if (record.status === 'queued' && this.jobs.cancelQueued(id)) return this.get(deviceId, id);
    if (record.status === 'processing') {
      this.jobs.requestCancel(id);
      return this.get(deviceId, id);
    }
    const fresh = this.record(deviceId, id);
    if (fresh.status === 'processing') return this.cancel(deviceId, id);
    throw new ApiException(
      HttpStatus.CONFLICT,
      'already_finished',
      `Задача уже завершена (${fresh.status})`,
    );
  }

  async download(deviceId: string, id: string, kind: DownloadKind) {
    const record = this.record(deviceId, id);
    const file = DOWNLOADS[kind];
    if (!record.result) throw notReady(record);
    const data = await this.files.read(id, file.path);
    if (!data) throw notReady(record);
    return { ...data, contentType: file.contentType, fileName: `omr-${id}.${file.ext}` };
  }

  /**
   * Результат задачи для библиотеки: отчёт и поток MusicXML. Есть при done и при failed с
   * low_quality, иначе — 409 result_not_ready.
   */
  async result(
    deviceId: string,
    id: string,
  ): Promise<{ report: OmrReport; hue: number; musicXml: Readable; size: number }> {
    const record = this.record(deviceId, id);
    if (!record.result) throw notReady(record);
    const data = await this.files.read(id, DOWNLOADS.musicxml.path);
    if (!data) throw notReady(record);
    return {
      report: record.result,
      hue: jobHue(record),
      musicXml: data.stream,
      size: data.size,
    };
  }

  async page(deviceId: string, id: string, page: number) {
    const record = this.record(deviceId, id);
    if (!Number.isInteger(page) || page < 1 || page > record.pages.length) {
      throw notFound(`Страницы ${page} нет, всего страниц: ${record.pages.length}`);
    }
    const data = await this.files.read(id, `pages/${page}.png`);
    if (!data) throw notFound(`Страница ${page} ещё не подготовлена`);
    return { ...data, contentType: 'image/png', fileName: `omr-${id}-page-${page}.png` };
  }

  /** Задача устройства. Чужая задача неотличима от несуществующей: 404. */
  private record(deviceId: string, id: string): JobRecord {
    const record = UUID.test(id) ? this.jobs.get(id) : null;
    if (!record || record.deviceId !== deviceId) throw notFound();
    return record;
  }

  private toJob(record: JobRecord): OmrJob {
    const base = `/v1/omr/jobs/${record.id}`;
    return OmrJob.parse({
      id: record.id,
      status: record.status,
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
      startedAt: record.startedAt,
      finishedAt: record.finishedAt,
      revision: record.revision,
      source: {
        kind: record.sourceKind,
        files: record.sourceFiles.map(({ name, size, contentType }) => ({
          name,
          size,
          contentType,
        })),
      },
      options: record.options,
      hue: jobHue(record),
      dismissedAt: record.dismissedAt,
      progress: record.progress,
      pages: record.pages,
      result: record.result
        ? {
            ...record.result,
            musicXmlUrl: `${base}/result.musicxml`,
            reportUrl: `${base}/report.json`,
          }
        : null,
      error: record.error,
      cancelRequested: record.cancelRequested,
    });
  }

  private async purgeOld() {
    const before = new Date(Date.now() - this.config.retentionDays * 86_400_000).toISOString();
    try {
      const ids = this.jobs.deleteFinishedBefore(before);
      await Promise.all(ids.map((id) => this.files.remove(id)));
      if (ids.length) this.log.log(`Удалено старых задач: ${ids.length}`);
    } catch (e) {
      this.log.warn(`Не удалось удалить старые задачи: ${String(e)}`);
    }
  }
}

/** Оттенок задачи; у задач до миграции omr_003 его нет — постоянный, из id. */
function jobHue(record: JobRecord): number {
  return record.hue ?? createHash('sha256').update(record.id).digest().readUInt16BE(0) % 360;
}

function parseOptions(fields: Record<string, string>): OmrJobOptions {
  // Пустое поле формы — то же, что не заданное (Swagger отправляет пустую строку).
  const given = Object.fromEntries(Object.entries(fields).filter(([, v]) => v.trim() !== ''));
  const parsed = OmrJobOptions.safeParse(
    Object.fromEntries(Object.entries(given).map(([k, v]) => [k, v.trim()])),
  );
  if (parsed.success) return parsed.data;
  const issue = parsed.error.issues[0]!;
  const field = String(issue.path[0] ?? '');
  const allowed = 'values' in issue ? ` Допустимо: ${issue.values.join(', ')}` : '';
  throw new ApiException(
    HttpStatus.BAD_REQUEST,
    'invalid_option',
    `Поле ${field}: недопустимое значение «${given[field] ?? ''}».${allowed}`,
  );
}

function tooManyFiles(max: number) {
  return new ApiException(HttpStatus.BAD_REQUEST, 'too_many_files', `Можно не больше ${max} фото`);
}

function notReady(record: JobRecord) {
  return new ApiException(
    HttpStatus.CONFLICT,
    'result_not_ready',
    record.status === 'queued' || record.status === 'processing'
      ? `Результата ещё нет: задача ${record.status === 'queued' ? 'в очереди' : 'в работе'}`
      : `Результата нет: задача ${record.status}${record.error ? ` (${record.error.code})` : ''}`,
  );
}
