import { createReadStream, createWriteStream, existsSync } from 'node:fs';
import { mkdir, open, rm, stat } from 'node:fs/promises';
import { dirname, join, normalize, sep } from 'node:path';
import type { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

/**
 * Файлы задач: исходники, страницы, результат. Пути — относительно папки задачи
 * (`source/01.pdf`, `pages/1.png`, `result.musicxml`). Локально — диск, на сервере — S3.
 */
export abstract class FileStorage {
  abstract write(jobId: string, path: string, data: Readable): Promise<number>;
  abstract readHead(jobId: string, path: string, bytes: number): Promise<Uint8Array>;
  abstract exists(jobId: string, path: string): boolean;
  abstract read(jobId: string, path: string): Promise<{ stream: Readable; size: number } | null>;
  abstract removeJob(jobId: string): Promise<void>;
}

export class LocalFileStorage extends FileStorage {
  constructor(private readonly dataDir: string) {
    super();
  }

  private resolve(jobId: string, path = ''): string {
    const jobDir = join(this.dataDir, 'jobs', jobId);
    const full = normalize(join(jobDir, path));
    if (full !== jobDir && !full.startsWith(jobDir + sep)) throw new Error('путь вне папки задачи');
    return full;
  }

  async write(jobId: string, path: string, data: Readable): Promise<number> {
    const target = this.resolve(jobId, path);
    await mkdir(dirname(target), { recursive: true });
    await pipeline(data, createWriteStream(target));
    return (await stat(target)).size;
  }

  async readHead(jobId: string, path: string, bytes: number): Promise<Uint8Array> {
    const file = await open(this.resolve(jobId, path), 'r');
    try {
      const buffer = Buffer.alloc(bytes);
      const { bytesRead } = await file.read(buffer, 0, bytes, 0);
      return buffer.subarray(0, bytesRead);
    } finally {
      await file.close();
    }
  }

  exists(jobId: string, path: string): boolean {
    return existsSync(this.resolve(jobId, path));
  }

  async read(jobId: string, path: string) {
    const full = this.resolve(jobId, path);
    if (!existsSync(full)) return null;
    return { stream: createReadStream(full), size: (await stat(full)).size };
  }

  async removeJob(jobId: string): Promise<void> {
    await rm(this.resolve(jobId), { recursive: true, force: true });
  }
}
