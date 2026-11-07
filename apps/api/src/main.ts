import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from './app.module.js';
import { configureApp } from './app.setup.js';
import { loadOmrConfig } from './config.js';
import { setupSwagger } from './swagger.js';

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter());
  await configureApp(app, loadOmrConfig());
  setupSwagger(app);
  app.enableShutdownHooks();
  const port = Number(process.env.PORT ?? 3000);
  await app.listen(port, '0.0.0.0');
  const log = new Logger('Bootstrap');
  log.log(`API: http://localhost:${port}/v1`);
  log.log(`Swagger: http://localhost:${port}/docs`);
  log.log(`Данные OMR: ${loadOmrConfig().dataDir}`);
}
await bootstrap();
