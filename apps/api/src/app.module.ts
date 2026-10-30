import { Module } from '@nestjs/common';
import { HealthModule } from './health/health.module.js';
import { OmrModule } from './omr/omr.module.js';

@Module({
  imports: [HealthModule, OmrModule],
})
export class AppModule {}
