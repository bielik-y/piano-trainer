/**
 * contracts: zod-схемы API, общие для apps/api и apps/mobile.
 * См. docs/ARCHITECTURE.md §7–8. Те же данные воркер описывает pydantic-моделями
 * (services/omr-worker/src/omr_worker/models.py) — при изменении правь оба места.
 */
import { z } from 'zod';

// --- Задача распознавания ---

export const OmrSourceKind = z.enum(['pdf', 'images']).meta({
  description: 'pdf — один PDF; images — 1–10 фото одной композиции по порядку страниц',
});
export type OmrSourceKind = z.infer<typeof OmrSourceKind>;

export const OmrJobStatus = z.enum(['queued', 'processing', 'done', 'failed', 'cancelled']).meta({
  description: 'queued → processing → done | failed | cancelled',
});
export type OmrJobStatus = z.infer<typeof OmrJobStatus>;

export const OMR_TERMINAL_STATUSES: readonly OmrJobStatus[] = ['done', 'failed', 'cancelled'];

/** Размер, который пользователь выбрал при загрузке; auto — определить по нотам. */
export const TimeSignatureChoice = z.enum(['auto', '2/4', '3/4', '4/4', '6/8', '12/8']);
export type TimeSignatureChoice = z.infer<typeof TimeSignatureChoice>;

/** Параметры распознавания: multipart-поля `POST /v1/omr/jobs` рядом с файлами. */
export const OmrJobOptions = z
  .object({
    /**
     * Не auto — размер ставится на всю пьесу вместо найденного движком, такты проверяются по
     * нему, смены размера посреди пьесы не ищутся. В отчёте timeSignatureSource = user.
     */
    timeSignature: TimeSignatureChoice.default('auto'),
  })
  .meta({ id: 'OmrJobOptions' });
export type OmrJobOptions = z.infer<typeof OmrJobOptions>;

export const OmrStage = z.enum(['preprocessing', 'recognizing', 'merging', 'validating']);
export type OmrStage = z.infer<typeof OmrStage>;

export const OmrProgress = z.object({
  stage: OmrStage,
  /** Страница, которая сейчас распознаётся (с 1). */
  page: z.number().int().positive().nullable(),
  pageCount: z.number().int().nonnegative(),
  percent: z.number().int().min(0).max(100),
  /** Оценка оставшегося времени; null — неизвестно. */
  etaSeconds: z.number().int().nonnegative().nullable(),
});
export type OmrProgress = z.infer<typeof OmrProgress>;

export const OmrPage = z.object({
  index: z.number().int().positive(),
  status: z.enum(['pending', 'processing', 'done', 'failed']),
  width: z.number().int().nullable(),
  height: z.number().int().nullable(),
  measureCount: z.number().int().nonnegative().nullable(),
  seconds: z.number().nullable(),
  error: z.string().nullable(),
});
export type OmrPage = z.infer<typeof OmrPage>;

export const MeasureIssueReason = z.enum([
  'missing_on_staff',
  'empty',
  'no_time_signature',
  'overflow',
  'duration_mismatch',
]);
export type MeasureIssueReason = z.infer<typeof MeasureIssueReason>;

export const SuspiciousMeasure = z.object({
  /** Индекс такта в партитуре, с 0. */
  index: z.number().int().nonnegative(),
  /** Номер такта в MusicXML. */
  number: z.string(),
  page: z.number().int().positive(),
  reasons: z.array(MeasureIssueReason),
});
export type SuspiciousMeasure = z.infer<typeof SuspiciousMeasure>;

/**
 * Откуда размер: engine — знак размера нашёл движок, inferred — вычислен по длинам тактов
 * (предположение), user — задан при загрузке (OmrJobOptions.timeSignature).
 */
export const TimeSignatureSource = z.enum(['engine', 'inferred', 'user']);
export type TimeSignatureSource = z.infer<typeof TimeSignatureSource>;

/** Отчёт воркера по распознанной партитуре (report.json без списка страниц). */
export const OmrReport = z.object({
  measureCount: z.number().int().nonnegative(),
  okMeasureCount: z.number().int().nonnegative(),
  /** Доля тактов без замечаний, 0–1. */
  okRatio: z.number().min(0).max(1),
  /** Порог: при okRatio ниже него задача завершается с low_quality. */
  minOkRatio: z.number().min(0).max(1),
  quality: z.enum(['ok', 'low']),
  staffCount: z.number().int().nonnegative(),
  timeSignature: z.string().nullable(),
  timeSignatureSource: TimeSignatureSource.nullable().default(null),
  /** Знаки при ключе: > 0 — диезы, < 0 — бемоли. */
  keyFifths: z.number().int().nullable(),
  title: z.string().nullable().default(null),
  composer: z.string().nullable().default(null),
  /** Темп словами, как напечатан: Allegro, Moderately. */
  tempoText: z.string().nullable().default(null),
  /** Темп числом; значок ноты не читается, долей считается четверть. */
  tempoBpm: z.number().int().positive().nullable().default(null),
  /** Номера тактов, исправленных повторным распознаванием отдельной строки. */
  rerecognizedMeasures: z.array(z.string()).default([]),
  suspiciousMeasures: z.array(SuspiciousMeasure),
  engine: z.object({ name: z.string(), version: z.string().nullable() }),
});
export type OmrReport = z.infer<typeof OmrReport>;

export const OmrErrorCode = z
  .enum([
    'low_quality',
    'unreadable_file',
    'too_many_pages',
    'no_music_found',
    'engine_failed',
    'timeout',
    'interrupted',
  ])
  .meta({
    description:
      'low_quality — нормальных тактов меньше порога (результат всё равно можно скачать); ' +
      'unreadable_file — файл не открылся; too_many_pages — PDF длиннее 20 страниц; ' +
      'no_music_found — нот не найдено; engine_failed — сбой движка; timeout — таймаут; ' +
      'interrupted — воркер перезапустился во время задачи',
  });
export type OmrErrorCode = z.infer<typeof OmrErrorCode>;

export const OmrSourceFile = z.object({
  name: z.string(),
  size: z.number().int().nonnegative(),
  contentType: z.string(),
});
export type OmrSourceFile = z.infer<typeof OmrSourceFile>;

/** Как исходный файл хранится в базе: плюс путь внутри папки задачи. */
export const StoredSourceFile = OmrSourceFile.extend({ path: z.string() });
export type StoredSourceFile = z.infer<typeof StoredSourceFile>;

export const OmrJob = z
  .object({
    id: z.uuid(),
    status: OmrJobStatus,
    createdAt: z.iso.datetime(),
    updatedAt: z.iso.datetime(),
    startedAt: z.iso.datetime().nullable(),
    finishedAt: z.iso.datetime().nullable(),
    /** Растёт при каждом изменении задачи. */
    revision: z.number().int().nonnegative(),
    source: z.object({
      kind: OmrSourceKind,
      files: z.array(OmrSourceFile),
    }),
    options: OmrJobOptions,
    progress: OmrProgress.nullable(),
    pages: z.array(OmrPage),
    /** Есть при done, а также при failed с кодом low_quality. */
    result: OmrReport.extend({
      musicXmlUrl: z.string(),
      reportUrl: z.string(),
    }).nullable(),
    error: z.object({ code: OmrErrorCode, message: z.string() }).nullable(),
    cancelRequested: z.boolean(),
  })
  .meta({ id: 'OmrJob' });
export type OmrJob = z.infer<typeof OmrJob>;

export const OmrJobList = z.object({ items: z.array(OmrJob) }).meta({ id: 'OmrJobList' });
export type OmrJobList = z.infer<typeof OmrJobList>;

/** Типы событий SSE `GET /v1/omr/jobs/:id/events`; в data — OmrJob целиком. */
export const OmrJobEventType = z.enum(['progress', 'done', 'failed', 'cancelled']);
export type OmrJobEventType = z.infer<typeof OmrJobEventType>;

// --- Ошибки запроса ---

export const ApiErrorCode = z.enum([
  'no_files',
  'unsupported_file_type',
  'mixed_sources',
  'too_many_files',
  'file_too_large',
  'not_found',
  'result_not_ready',
  'already_finished',
  'bad_request',
  'unauthorized',
  'invalid_option',
  'invalid_request',
]);
export type ApiErrorCode = z.infer<typeof ApiErrorCode>;

export const ApiError = z
  .object({ code: ApiErrorCode, message: z.string() })
  .meta({ id: 'ApiError' });
export type ApiError = z.infer<typeof ApiError>;

export const OMR_LIMITS = {
  maxImages: 10,
  maxFileBytes: 25 * 1024 * 1024,
  maxPdfPages: 20,
} as const;

// --- Библиотека ---

export const PieceSourceKind = z.enum(['musicxml', 'mxl', 'omr']).meta({
  description: 'musicxml/mxl — файл загружен как есть; omr — распознан из PDF или фото',
});
export type PieceSourceKind = z.infer<typeof PieceSourceKind>;

/**
 * Пьеса в библиотеке (ARCHITECTURE §5.2). Источник правды — сервер; приложение держит кэш и
 * подтягивает изменения через `GET /v1/pieces?updatedSince=…`.
 */
export const Piece = z
  .object({
    id: z.uuid(),
    title: z.string(),
    composer: z.string().nullable(),
    sourceKind: PieceSourceKind,
    /** Задача распознавания, из которой создана пьеса. */
    omrJobId: z.uuid().nullable(),
    measureCount: z.number().int().nonnegative(),
    /** Индексы тактов (с 0), которые не оцениваются при игре: подозрительные после OMR. */
    unscoredMeasures: z.array(z.number().int().nonnegative()),
    timeSignature: z.string().nullable(),
    timeSignatureSource: TimeSignatureSource.nullable(),
    keyFifths: z.number().int().nullable(),
    tempoText: z.string().nullable(),
    tempoBpm: z.number().int().positive().nullable(),
    /** MusicXML партитуры. */
    scoreUrl: z.string(),
    createdAt: z.iso.datetime(),
    updatedAt: z.iso.datetime(),
    /** Не null — пьеса удалена; такие приходят только в списке с updatedSince. */
    deletedAt: z.iso.datetime().nullable(),
    lastPracticedAt: z.iso.datetime().nullable(),
  })
  .meta({ id: 'Piece' });
export type Piece = z.infer<typeof Piece>;

export const PieceList = z
  .object({
    /** По возрастанию updatedAt. */
    items: z.array(Piece),
    /** Передайте в cursor, чтобы получить следующую страницу; null — это последняя. */
    nextCursor: z.string().nullable(),
    /** Время сервера на момент запроса: следующий updatedSince для синхронизации кэша. */
    serverTime: z.iso.datetime(),
  })
  .meta({ id: 'PieceList' });
export type PieceList = z.infer<typeof PieceList>;

const PieceTitle = z.string().trim().min(1).max(200);
/** Пустая строка — автора нет. */
const PieceComposer = z.string().trim().max(200).nullable();

/** Тело `POST /v1/pieces/from-omr`: «Добавить в библиотеку» на экране результата. */
export const CreatePieceFromOmr = z
  .object({
    jobId: z.uuid(),
    /** По умолчанию — название, распознанное с первой страницы, или «Без названия». */
    title: PieceTitle.optional(),
    /** По умолчанию — распознанный автор. */
    composer: PieceComposer.optional(),
  })
  .meta({ id: 'CreatePieceFromOmr' });
export type CreatePieceFromOmr = z.infer<typeof CreatePieceFromOmr>;

/** Тело `PATCH /v1/pieces/:id`: меняются только переданные поля. */
export const UpdatePiece = z
  .object({ title: PieceTitle.optional(), composer: PieceComposer.optional() })
  .refine((v) => v.title !== undefined || v.composer !== undefined, {
    message: 'Передайте title или composer',
  })
  .meta({ id: 'UpdatePiece' });
export type UpdatePiece = z.infer<typeof UpdatePiece>;

// --- Устройство ---

/**
 * Ответ `POST /v1/devices`: анонимное устройство. Токен показывается один раз; дальше он идёт
 * в каждом запросе как `Authorization: Bearer <token>`. Задачи и пьесы принадлежат устройству.
 */
export const DeviceRegistration = z
  .object({
    deviceId: z.uuid(),
    token: z.string(),
  })
  .meta({ id: 'DeviceRegistration' });
export type DeviceRegistration = z.infer<typeof DeviceRegistration>;

// --- Health ---

export const HealthResponse = z.object({
  status: z.literal('ok'),
  version: z.string(),
});
export type HealthResponse = z.infer<typeof HealthResponse>;
