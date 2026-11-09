import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { OMR_LIMITS } from '@piano/contracts';

/** Корень репозитория: и из src/, и из dist/ это три уровня вверх. */
const REPO_ROOT = fileURLToPath(new URL('../../../', import.meta.url));

export interface AppConfig {
  /** Корень данных приложения (DATA_DIR): app.sqlite и library/<pieceId>/. */
  dataDir: string;
  /** Устройства и библиотека пьес. */
  appDbPath: string;
  /** Файлы пьес: library/<pieceId>/score.musicxml. */
  libraryDir: string;
}

export const APP_CONFIG = Symbol('APP_CONFIG');

export function loadAppConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const dataDir = resolve(env.DATA_DIR ?? resolve(REPO_ROOT, '.data'));
  return {
    dataDir,
    appDbPath: join(dataDir, 'app.sqlite'),
    libraryDir: join(dataDir, 'library'),
  };
}

export interface OmrConfig {
  /** Общая с воркером папка: omr.sqlite и jobs/<id>/ (ARCHITECTURE §7.1.1). */
  dataDir: string;
  maxImages: number;
  maxFileBytes: number;
  /** Сколько дней хранить завершённые задачи и их файлы. */
  retentionDays: number;
  /** Как часто SSE перечитывает задачу. */
  eventsPollMs: number;
}

export const OMR_CONFIG = Symbol('OMR_CONFIG');

export function loadOmrConfig(env: NodeJS.ProcessEnv = process.env): OmrConfig {
  return {
    dataDir: resolve(env.OMR_DATA_DIR ?? resolve(REPO_ROOT, '.data', 'omr')),
    maxImages: OMR_LIMITS.maxImages,
    maxFileBytes: Number(env.OMR_MAX_FILE_BYTES ?? OMR_LIMITS.maxFileBytes),
    retentionDays: Number(env.OMR_RETENTION_DAYS ?? 7),
    eventsPollMs: Number(env.OMR_EVENTS_POLL_MS ?? 500),
  };
}
