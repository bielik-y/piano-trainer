import { Module } from '@nestjs/common';
import { OmrController } from './omr.controller.js';

// Фаза 7 (docs/ROADMAP.md): Postgres (omr_jobs), S3 presigned upload, BullMQ-продюсер очереди «omr».
@Module({
  controllers: [OmrController],
})
export class OmrModule {}
