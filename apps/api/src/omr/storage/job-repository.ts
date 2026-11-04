import type {
  OmrErrorCode,
  OmrJobStatus,
  OmrPage,
  OmrProgress,
  OmrReport,
  OmrSourceKind,
  StoredSourceFile,
} from '@piano/contracts';

/** Запись задачи в хранилище (без ссылок — их добавляет сервис). */
export interface JobRecord {
  id: string;
  status: OmrJobStatus;
  revision: number;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  sourceKind: OmrSourceKind;
  sourceFiles: StoredSourceFile[];
  progress: OmrProgress | null;
  pages: OmrPage[];
  result: OmrReport | null;
  error: { code: OmrErrorCode; message: string } | null;
  cancelRequested: boolean;
}

export interface NewJob {
  id: string;
  sourceKind: OmrSourceKind;
  sourceFiles: StoredSourceFile[];
}

/**
 * Хранилище задач. Локально — SQLite (общий файл с воркером), на сервере — Postgres.
 * Абстрактный класс служит и интерфейсом, и токеном DI.
 */
export abstract class JobRepository {
  abstract insert(job: NewJob): JobRecord;
  abstract get(id: string): JobRecord | null;
  /** Ревизия без чтения всей записи — для SSE. */
  abstract revision(id: string): number | null;
  abstract list(limit: number): JobRecord[];
  /** queued → cancelled. true, если задача ещё ждала в очереди. */
  abstract cancelQueued(id: string): boolean;
  /** Для задачи в работе: попросить воркер остановиться. */
  abstract requestCancel(id: string): boolean;
  /** Удаляет завершённые задачи старше `before`, возвращает их id. */
  abstract deleteFinishedBefore(before: string): string[];
}
