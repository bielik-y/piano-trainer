import { Inject, Module, type OnApplicationShutdown } from '@nestjs/common';
import { join } from 'node:path';
import { OMR_CONFIG, loadOmrConfig, type OmrConfig } from '../config.js';
import { DevicesModule } from '../devices/devices.module.js';
import { OmrController } from './omr.controller.js';
import { OmrService } from './omr.service.js';
import { JOB_FILES, LocalFileStorage } from '../storage/file-storage.js';
import { JobQueue, SqliteJobQueue } from './storage/job-queue.js';
import { JobRepository } from './storage/job-repository.js';
import { SqliteJobRepository } from './storage/sqlite-job-repository.js';

// Локальный режим (ARCHITECTURE §7.1.1): SQLite + диск. На сервере здесь будут Postgres, S3, BullMQ.
@Module({
  imports: [DevicesModule],
  controllers: [OmrController],
  providers: [
    { provide: OMR_CONFIG, useFactory: () => loadOmrConfig() },
    {
      provide: JobRepository,
      inject: [OMR_CONFIG],
      useFactory: (config: OmrConfig) =>
        new SqliteJobRepository(join(config.dataDir, 'omr.sqlite')),
    },
    {
      provide: JOB_FILES,
      inject: [OMR_CONFIG],
      useFactory: (config: OmrConfig) => new LocalFileStorage(join(config.dataDir, 'jobs')),
    },
    { provide: JobQueue, useClass: SqliteJobQueue },
    OmrService,
  ],
  exports: [OMR_CONFIG, OmrService],
})
export class OmrModule implements OnApplicationShutdown {
  constructor(@Inject(JobRepository) private readonly jobs: JobRepository) {}

  onApplicationShutdown() {
    if (this.jobs instanceof SqliteJobRepository) this.jobs.close();
  }
}
