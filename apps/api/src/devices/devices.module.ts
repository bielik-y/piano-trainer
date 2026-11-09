import { Module } from '@nestjs/common';
import type { DatabaseSync } from 'node:sqlite';
import { APP_DB } from '../database/database.module.js';
import { DeviceGuard } from './device.guard.js';
import { DeviceRepository, SqliteDeviceRepository } from './device-repository.js';
import { DevicesController } from './devices.controller.js';
import { DevicesService } from './devices.service.js';

@Module({
  controllers: [DevicesController],
  providers: [
    {
      provide: DeviceRepository,
      inject: [APP_DB],
      useFactory: (db: DatabaseSync) => new SqliteDeviceRepository(db),
    },
    DevicesService,
    DeviceGuard,
  ],
  exports: [DevicesService, DeviceGuard],
})
export class DevicesModule {}
