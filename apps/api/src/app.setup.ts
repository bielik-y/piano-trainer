import multipart from '@fastify/multipart';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import type { OmrConfig } from './config.js';

/** Общая настройка приложения для main.ts и e2e-тестов. */
export async function configureApp(app: NestFastifyApplication, config: OmrConfig): Promise<void> {
  app.setGlobalPrefix('v1');
  await app.register(multipart, {
    limits: {
      fileSize: config.maxFileBytes,
      // На один больше лимита: лишний файл сервис отклонит понятной ошибкой too_many_files.
      files: config.maxImages + 1,
      fields: 10,
    },
  });
}
