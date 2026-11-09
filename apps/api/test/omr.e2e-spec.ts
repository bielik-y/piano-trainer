import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { OmrJob } from '@piano/contracts';
import { createTestApp, registerDevice, type TestApp } from './helpers.js';

const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46]);
const PDF = Buffer.from('%PDF-1.7\n%test');

type Part = { name: string; data: Buffer; type?: string };

function multipart(parts: Part[], extraHeaders: Record<string, string> = {}) {
  const boundary = '----piano-test-boundary';
  const chunks = parts.flatMap((p) => [
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${p.name}"\r\n` +
        `Content-Type: ${p.type ?? 'application/octet-stream'}\r\n\r\n`,
    ),
    p.data,
    Buffer.from('\r\n'),
  ]);
  return {
    payload: Buffer.concat([...chunks, Buffer.from(`--${boundary}--\r\n`)]),
    headers: { ...extraHeaders, 'content-type': `multipart/form-data; boundary=${boundary}` },
  };
}

describe('OMR API (e2e)', () => {
  let app: NestFastifyApplication;
  let dataDir: string;

  const upload = (parts: Part[]) =>
    app.inject({ method: 'POST', url: '/v1/omr/jobs', ...multipart(parts, auth) });

  let t: TestApp;
  let auth: { authorization: string };

  beforeEach(async () => {
    t = await createTestApp();
    app = t.app;
    dataDir = t.omrDir;
    auth = await registerDevice(app);
  });

  afterEach(async () => {
    await t.close();
  });

  /** Делает то же, что воркер по окончании распознавания. */
  function finishJob(id: string, status: 'done' | 'failed', errorCode: string | null = null) {
    const db = new DatabaseSync(join(dataDir, 'omr.sqlite'));
    const report = {
      measureCount: 2,
      okMeasureCount: 1,
      okRatio: 0.5,
      minOkRatio: 0.4,
      quality: 'ok',
      staffCount: 2,
      timeSignature: '4/4',
      keyFifths: 0,
      suspiciousMeasures: [{ index: 1, number: '2', page: 1, reasons: ['overflow'] }],
      engine: { name: 'homr', version: '0.7.0' },
    };
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
    writeFileSync(join(dataDir, 'jobs', id, 'result.musicxml'), '<score-partwise/>');
    writeFileSync(join(dataDir, 'jobs', id, 'report.json'), JSON.stringify(report));
  }

  it('создаёт задачу из фото и отдаёт её', async () => {
    const res = await upload([
      { name: 'стр1.jpg', data: JPEG },
      { name: 'стр2.png', data: PNG },
    ]);
    expect(res.statusCode).toBe(201);
    const job = OmrJob.parse(res.json());
    expect(job).toMatchObject({ status: 'queued', source: { kind: 'images' }, result: null });
    expect(job.source.files.map((f) => [f.name, f.contentType])).toEqual([
      ['стр1.jpg', 'image/jpeg'],
      ['стр2.png', 'image/png'],
    ]);

    const got = await app.inject({ method: 'GET', headers: auth, url: `/v1/omr/jobs/${job.id}` });
    expect(got.json()).toMatchObject({ id: job.id, status: 'queued' });
    const list = await app.inject({ method: 'GET', headers: auth, url: '/v1/omr/jobs' });
    expect(list.json().items).toHaveLength(1);
  });

  it('принимает один PDF', async () => {
    const res = await upload([{ name: 'ноты.pdf', data: PDF }]);
    expect(res.statusCode).toBe(201);
    expect(res.json().source.kind).toBe('pdf');
  });

  it.each<[string, Part[], number, string]>([
    ['без файлов', [], 400, 'no_files'],
    ['не ноты', [{ name: 'a.txt', data: Buffer.from('hello') }], 415, 'unsupported_file_type'],
    [
      'PDF вместе с фото',
      [
        { name: 'a.pdf', data: PDF },
        { name: 'b.png', data: PNG },
      ],
      400,
      'mixed_sources',
    ],
    [
      '11 фото',
      Array.from({ length: 11 }, (_, i) => ({ name: `${i}.png`, data: PNG })),
      400,
      'too_many_files',
    ],
  ])('отклоняет загрузку: %s', async (_name, parts, status, code) => {
    const res = await upload(parts);
    expect(res.statusCode).toBe(status);
    expect(res.json()).toMatchObject({ code });
  });

  it('отклоняет запрос не multipart', async () => {
    const res = await app.inject({
      method: 'POST',
      headers: auth,
      url: '/v1/omr/jobs',
      payload: {},
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().code).toBe('no_files');
  });

  it('404 для неизвестной задачи', async () => {
    const res = await app.inject({ method: 'GET', headers: auth, url: '/v1/omr/jobs/nope' });
    expect(res.statusCode).toBe(404);
    expect(res.json().code).toBe('not_found');
  });

  it('отменяет задачу в очереди', async () => {
    const { id } = (await upload([{ name: 'a.png', data: PNG }])).json();
    const res = await app.inject({
      method: 'POST',
      headers: auth,
      url: `/v1/omr/jobs/${id}/cancel`,
    });
    expect(res.json()).toMatchObject({ status: 'cancelled', cancelRequested: true });
    const again = await app.inject({
      method: 'POST',
      headers: auth,
      url: `/v1/omr/jobs/${id}/cancel`,
    });
    expect(again.statusCode).toBe(409);
    expect(again.json().code).toBe('already_finished');
  });

  it('отдаёт результат только когда он готов', async () => {
    const { id } = (await upload([{ name: 'a.png', data: PNG }])).json();
    const early = await app.inject({
      method: 'GET',
      headers: auth,
      url: `/v1/omr/jobs/${id}/result.musicxml`,
    });
    expect(early.statusCode).toBe(409);
    expect(early.json().code).toBe('result_not_ready');

    finishJob(id, 'done');
    const job = OmrJob.parse(
      (await app.inject({ method: 'GET', headers: auth, url: `/v1/omr/jobs/${id}` })).json(),
    );
    expect(job.result?.musicXmlUrl).toBe(`/v1/omr/jobs/${id}/result.musicxml`);
    const file = await app.inject({ method: 'GET', headers: auth, url: job.result!.musicXmlUrl });
    expect(file.statusCode).toBe(200);
    expect(file.headers['content-type']).toContain('musicxml');
    expect(file.headers['content-disposition']).toContain('attachment');
    expect(file.body).toBe('<score-partwise/>');
    const report = await app.inject({ method: 'GET', headers: auth, url: job.result!.reportUrl });
    expect(report.json().okRatio).toBe(0.5);
  });

  it('при low_quality результат всё равно можно скачать', async () => {
    const { id } = (await upload([{ name: 'a.png', data: PNG }])).json();
    finishJob(id, 'failed', 'low_quality');
    const job = (
      await app.inject({ method: 'GET', headers: auth, url: `/v1/omr/jobs/${id}` })
    ).json();
    expect(job).toMatchObject({ status: 'failed', error: { code: 'low_quality' } });
    const file = await app.inject({
      method: 'GET',
      headers: auth,
      url: `/v1/omr/jobs/${id}/result.musicxml`,
    });
    expect(file.statusCode).toBe(200);
  });

  it('SSE отдаёт состояние и закрывается на завершённой задаче', async () => {
    const { id } = (await upload([{ name: 'a.png', data: PNG }])).json();
    finishJob(id, 'done');
    const res = await app.inject({
      method: 'GET',
      headers: auth,
      url: `/v1/omr/jobs/${id}/events`,
    });
    expect(res.headers['content-type']).toContain('text/event-stream');
    expect(res.body).toContain('event: done');
    const data = res.body.split('\n').find((l) => l.startsWith('data: '))!;
    expect(OmrJob.parse(JSON.parse(data.slice(6))).status).toBe('done');
  });

  it('без токена устройства — 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/v1/omr/jobs' });
    expect(res.statusCode).toBe(401);
    expect(res.json().code).toBe('unauthorized');
    const bad = await app.inject({
      method: 'GET',
      url: '/v1/omr/jobs',
      headers: { authorization: 'Bearer pt_неизвестный' },
    });
    expect(bad.statusCode).toBe(401);
  });

  it('задачи другого устройства не видны', async () => {
    const { id } = (await upload([{ name: 'a.png', data: PNG }])).json();
    const other = await registerDevice(app);
    for (const url of [`/v1/omr/jobs/${id}`, `/v1/omr/jobs/${id}/events`]) {
      const res = await app.inject({ method: 'GET', url, headers: other });
      expect(res.statusCode).toBe(404);
    }
    const cancel = await app.inject({
      method: 'POST',
      url: `/v1/omr/jobs/${id}/cancel`,
      headers: other,
    });
    expect(cancel.statusCode).toBe(404);
    const list = await app.inject({ method: 'GET', url: '/v1/omr/jobs', headers: other });
    expect(list.json().items).toEqual([]);
  });

  it('Swagger описывает схемы контракта', async () => {
    const res = await app.inject({ method: 'GET', url: '/docs-json' });
    const doc = res.json();
    expect(doc.paths['/v1/omr/jobs']).toBeDefined();
    expect(doc.components.schemas.OmrJob.properties.status.enum).toContain('processing');
  });
});
