import { Module } from '@nestjs/common';
import { DatabaseModule } from './database/database.module.js';
import { DevicesModule } from './devices/devices.module.js';
import { HealthModule } from './health/health.module.js';
import { OmrModule } from './omr/omr.module.js';
import { PiecesModule } from './pieces/pieces.module.js';

@Module({
  imports: [DatabaseModule, HealthModule, DevicesModule, OmrModule, PiecesModule],
})
export class AppModule {}
