import { mkdirSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

const require = createRequire(import.meta.url);

/**
 * Открывает базу SQLite и доводит схему до последней версии.
 *
 * Миграции — SQL-файлы из `@piano/contracts/sql`, применяются по порядку; номер последней
 * применённой хранится в `PRAGMA user_version`. Каждая миграция идёт в своей транзакции,
 * поэтому упавшая не оставляет схему наполовину изменённой. Уже применённые файлы не менять:
 * новое изменение схемы — новый файл в конце списка.
 */
export function openDatabase(path: string, migrations: readonly string[]): DatabaseSync {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path, { timeout: 10_000 });
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  migrate(db, migrations);
  return db;
}

export function migrate(db: DatabaseSync, migrations: readonly string[]): void {
  const { user_version: version } = db.prepare('PRAGMA user_version').get() as {
    user_version: number;
  };
  if (version > migrations.length) {
    throw new Error(
      `Схема базы новее кода: версия ${version}, миграций ${migrations.length}. Обновите API`,
    );
  }
  for (let i = version; i < migrations.length; i++) {
    const sql = readFileSync(require.resolve(`@piano/contracts/sql/${migrations[i]}`), 'utf8');
    db.exec('BEGIN IMMEDIATE');
    try {
      db.exec(sql);
      db.exec(`PRAGMA user_version = ${i + 1}`);
      db.exec('COMMIT');
    } catch (e) {
      db.exec('ROLLBACK');
      throw new Error(`Миграция ${migrations[i]} не применилась: ${String(e)}`, { cause: e });
    }
  }
}
