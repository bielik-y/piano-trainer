import { mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
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

export const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');
export const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46]);
export const PDF = Buffer.from('%PDF-1.7\n%test');

export type Part = { name: string; data: Buffer; type?: string };

/** Тело multipart/form-data: файлы в поле files и текстовые поля. */
export function multipart(
  parts: Part[],
  fields: Record<string, string> = {},
  extraHeaders: Record<string, string> = {},
) {
  const boundary = '----piano-test-boundary';
  const fieldChunks = Object.entries(fields).map(([name, value]) =>
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`,
    ),
  );
  const fileChunks = parts.flatMap((p) => [
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${p.name}"\r\n` +
        `Content-Type: ${p.type ?? 'application/octet-stream'}\r\n\r\n`,
    ),
    p.data,
    Buffer.from('\r\n'),
  ]);
  return {
    payload: Buffer.concat([...fileChunks, ...fieldChunks, Buffer.from(`--${boundary}--\r\n`)]),
    headers: { ...extraHeaders, 'content-type': `multipart/form-data; boundary=${boundary}` },
  };
}

/** Что пишет воркер в отчёт; в тестах — два такта, второй подозрительный. */
export const TEST_REPORT = {
  measureCount: 2,
  okMeasureCount: 1,
  okRatio: 0.5,
  minOkRatio: 0.4,
  quality: 'ok',
  staffCount: 2,
  timeSignature: '4/4',
  timeSignatureSource: 'engine',
  keyFifths: 0,
  title: 'Лунная соната',
  composer: 'Л. ван Бетховен',
  tempoText: 'Adagio sostenuto',
  tempoBpm: 52,
  timeSignatureChanges: [{ index: 1, number: '2', timeSignature: '5/4' }],
  suspiciousMeasures: [
    { index: 1, number: '2', page: 1, reasons: ['overflow'], length: 4.5, expectedLength: 4 },
  ],
  engine: { name: 'homr', version: '0.7.0' },
};

export const TEST_MUSICXML = '<score-partwise/>';

/** Делает то же, что воркер по окончании распознавания. */
export function finishJob(
  omrDir: string,
  id: string,
  status: 'done' | 'failed',
  errorCode: string | null = null,
  report: object = TEST_REPORT,
) {
  const db = new DatabaseSync(join(omrDir, 'omr.sqlite'));
  const page = {
    index: 1,
    status: 'done',
    width: 10,
    height: 10,
    measureCount: 2,
    seconds: 1.5,
    error: null,
  };
  db.prepare(
    `UPDATE omr_jobs SET status = ?, result = ?, pages = ?, error_code = ?, error_message = ?,
       started_at = updated_at, finished_at = updated_at, revision = revision + 2 WHERE id = ?`,
  ).run(
    status,
    JSON.stringify(report),
    JSON.stringify([page]),
    errorCode,
    errorCode ? 'плохо' : null,
    id,
  );
  db.close();
  writeFileSync(join(omrDir, 'jobs', id, 'result.musicxml'), TEST_MUSICXML);
  writeFileSync(join(omrDir, 'jobs', id, 'report.json'), JSON.stringify(report));
}

/** Папки задач на диске — чтобы проверить, что за отклонённой загрузкой не осталось файлов. */
export function jobDirs(omrDir: string): string[] {
  try {
    return readdirSync(join(omrDir, 'jobs'));
  } catch {
    return [];
  }
}

/** Сравнение строк для sort: без него порядок зависит от реализации. */
export const byText = (a: string, b: string) => a.localeCompare(b);
