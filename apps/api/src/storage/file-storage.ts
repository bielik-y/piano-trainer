import { createReadStream, createWriteStream, existsSync } from 'node:fs';
import { mkdir, open, rm, stat } from 'node:fs/promises';
import { dirname, join, normalize, sep } from 'node:path';
import type { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

/**
 * Файлы, сгруппированные по владельцу (`key`): задаче распознавания или пьесе. Пути —
 * относительно папки владельца (`source/01`, `pages/1.png`, `score.musicxml`).
 * Локально — диск, на сервере — S3 (key станет префиксом).
 */
export abstract class FileStorage {
  abstract write(key: string, path: string, data: Readable): Promise<number>;
  abstract readHead(key: string, path: string, bytes: number): Promise<Uint8Array>;
  abstract exists(key: string, path: string): boolean;
  abstract read(key: string, path: string): Promise<{ stream: Readable; size: number } | null>;
  /** Удаляет все файлы владельца. */
  abstract remove(key: string): Promise<void>;
}

/** Файлы задач распознавания: `<OMR_DATA_DIR>/jobs/<jobId>/`. */
export const JOB_FILES = Symbol('JOB_FILES');
/** Файлы пьес библиотеки: `<DATA_DIR>/library/<pieceId>/`. */
export const PIECE_FILES = Symbol('PIECE_FILES');

/** Папка `<rootDir>/<key>/` на диске. */
export class LocalFileStorage extends FileStorage {
  constructor(private readonly rootDir: string) {
    super();
  }

  private resolve(key: string, path = ''): string {
    const root = normalize(this.rootDir);
    const dir = normalize(join(root, key));
    const full = normalize(join(dir, path));
    if (!dir.startsWith(root + sep) || (full !== dir && !full.startsWith(dir + sep))) {
      throw new Error('путь вне папки хранилища');
    }
    return full;
  }

  async write(key: string, path: string, data: Readable): Promise<number> {
    const target = this.resolve(key, path);
    await mkdir(dirname(target), { recursive: true });
    await pipeline(data, createWriteStream(target));
    return (await stat(target)).size;
  }

  async readHead(key: string, path: string, bytes: number): Promise<Uint8Array> {
    const file = await open(this.resolve(key, path), 'r');
    try {
      const buffer = Buffer.alloc(bytes);
      const { bytesRead } = await file.read(buffer, 0, bytes, 0);
      return buffer.subarray(0, bytesRead);
    } finally {
      await file.close();
    }
  }

  exists(key: string, path: string): boolean {
    return existsSync(this.resolve(key, path));
  }

  async read(key: string, path: string) {
    const full = this.resolve(key, path);
    if (!existsSync(full)) return null;
    return { stream: createReadStream(full), size: (await stat(full)).size };
  }

  async remove(key: string): Promise<void> {
    await rm(this.resolve(key), { recursive: true, force: true });
  }
}
