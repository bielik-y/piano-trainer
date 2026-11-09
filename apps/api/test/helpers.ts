import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Test } from '@nestjs/testing';
import { FastifyAdapter, type NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from '../src/app.module.js';
import { configureApp } from '../src/app.setup.js';
import { loadOmrConfig } from '../src/config.js';
import { setupSwagger } from '../src/swagger.js';

export interface TestApp {
  app: NestFastifyApplication;
  /** OMR_DATA_DIR: omr.sqlite и jobs/<id>/. */
  omrDir: string;
  /** DATA_DIR: app.sqlite и library/<id>/. */
  dataDir: string;
  close(): Promise<void>;
}

/** Приложение целиком, как в main.ts, но с данными во временной папке. */
export async function createTestApp(): Promise<TestApp> {
  const root = mkdtempSync(join(tmpdir(), 'piano-api-'));
  const omrDir = join(root, 'omr');
  const dataDir = join(root, 'app');
  process.env.OMR_DATA_DIR = omrDir;
  process.env.DATA_DIR = dataDir;
  process.env.OMR_EVENTS_POLL_MS = '20';
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
  const app = moduleRef.createNestApplication<NestFastifyApplication>(new FastifyAdapter());
  await configureApp(app, loadOmrConfig());
  setupSwagger(app);
  await app.init();
  await app.getHttpAdapter().getInstance().ready();
  return {
    app,
    omrDir,
    dataDir,
    async close() {
      await app.close();
      delete process.env.OMR_DATA_DIR;
      delete process.env.DATA_DIR;
      delete process.env.OMR_EVENTS_POLL_MS;
      rmSync(root, { recursive: true, force: true });
    },
  };
}

/** Регистрирует устройство и возвращает заголовок с его токеном. */
export async function registerDevice(
  app: NestFastifyApplication,
): Promise<{ authorization: string }> {
  const res = await app.inject({ method: 'POST', url: '/v1/devices' });
  if (res.statusCode !== 201) throw new Error(`POST /v1/devices: ${res.statusCode} ${res.body}`);
  return { authorization: `Bearer ${(res.json() as { token: string }).token}` };
}
