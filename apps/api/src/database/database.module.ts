import { Global, Inject, Module, type OnApplicationShutdown } from '@nestjs/common';
import type { DatabaseSync } from 'node:sqlite';
import { APP_CONFIG, loadAppConfig, type AppConfig } from '../config.js';
import { APP_MIGRATIONS } from './migrations.js';
import { openDatabase } from './sqlite.js';

/** База приложения app.sqlite: устройства и библиотека. На сервере здесь будет Postgres. */
export const APP_DB = Symbol('APP_DB');

@Global()
@Module({
  providers: [
    { provide: APP_CONFIG, useFactory: () => loadAppConfig() },
    {
      provide: APP_DB,
      inject: [APP_CONFIG],
      useFactory: (config: AppConfig) => openDatabase(config.appDbPath, APP_MIGRATIONS),
    },
  ],
  exports: [APP_CONFIG, APP_DB],
})
export class DatabaseModule implements OnApplicationShutdown {
  constructor(@Inject(APP_DB) private readonly db: DatabaseSync) {}

  onApplicationShutdown() {
    if (this.db.isOpen) this.db.close();
  }
}
