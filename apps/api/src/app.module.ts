import { Module } from '@nestjs/common';
import { DatabaseModule } from './database/database.module.js';
import { DevicesModule } from './devices/devices.module.js';
import { HealthModule } from './health/health.module.js';
import { OmrModule } from './omr/omr.module.js';

@Module({
  imports: [DatabaseModule, HealthModule, DevicesModule, OmrModule],
})
export class AppModule {}
