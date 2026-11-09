import { Module } from '@nestjs/common';
import type { DatabaseSync } from 'node:sqlite';
import { APP_CONFIG, type AppConfig } from '../config.js';
import { APP_DB } from '../database/database.module.js';
import { DevicesModule } from '../devices/devices.module.js';
import { OmrModule } from '../omr/omr.module.js';
import { LocalFileStorage, PIECE_FILES } from '../storage/file-storage.js';
import { PieceRepository, SqlitePieceRepository } from './piece-repository.js';
import { PiecesController } from './pieces.controller.js';
import { PiecesService } from './pieces.service.js';

// Библиотека пьес: app.sqlite + файлы на диске. На сервере — Postgres и S3.
@Module({
  imports: [DevicesModule, OmrModule],
  controllers: [PiecesController],
  providers: [
    {
      provide: PieceRepository,
      inject: [APP_DB],
      useFactory: (db: DatabaseSync) => new SqlitePieceRepository(db),
    },
    {
      provide: PIECE_FILES,
      inject: [APP_CONFIG],
      useFactory: (config: AppConfig) => new LocalFileStorage(config.libraryDir),
    },
    PiecesService,
  ],
})
export class PiecesModule {}
