import type { DatabaseSync } from 'node:sqlite';
import { z } from 'zod';

export interface DeviceRecord {
  id: string;
  createdAt: string;
  lastSeenAt: string;
}

/** Устройства. Локально — app.sqlite, на сервере — Postgres. Класс — и интерфейс, и токен DI. */
export abstract class DeviceRepository {
  abstract insert(id: string, tokenHash: string, at: string): DeviceRecord;
  abstract findByTokenHash(tokenHash: string): DeviceRecord | null;
  /** Обновляет last_seen_at, если прошлая отметка старше `staleBefore`. */
  abstract touch(id: string, at: string, staleBefore: string): void;
}

const Row = z.object({ id: z.string(), created_at: z.string(), last_seen_at: z.string() });

const toRecord = (raw: unknown): DeviceRecord => {
  const row = Row.parse(raw);
  return { id: row.id, createdAt: row.created_at, lastSeenAt: row.last_seen_at };
};

export class SqliteDeviceRepository extends DeviceRepository {
  constructor(private readonly db: DatabaseSync) {
    super();
  }

  insert(id: string, tokenHash: string, at: string): DeviceRecord {
    this.db
      .prepare('INSERT INTO devices (id, token_hash, created_at, last_seen_at) VALUES (?, ?, ?, ?)')
      .run(id, tokenHash, at, at);
    return { id, createdAt: at, lastSeenAt: at };
  }

  findByTokenHash(tokenHash: string): DeviceRecord | null {
    const row = this.db
      .prepare('SELECT id, created_at, last_seen_at FROM devices WHERE token_hash = ?')
      .get(tokenHash);
    return row ? toRecord(row) : null;
  }

  touch(id: string, at: string, staleBefore: string): void {
    this.db
      .prepare('UPDATE devices SET last_seen_at = ? WHERE id = ? AND last_seen_at < ?')
      .run(at, id, staleBefore);
  }
}
