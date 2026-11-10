import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { OmrJob } from '@piano/contracts';
import {
  JPEG,
  PDF,
  PNG,
  createTestApp,
  finishJob as finish,
  jobDirs,
  multipart,
  registerDevice,
  type Part,
  type TestApp,
} from './helpers.js';

describe('OMR API (e2e)', () => {
  let app: NestFastifyApplication;
  let dataDir: string;

  const upload = (parts: Part[], fields: Record<string, string> = {}) =>
    app.inject({ method: 'POST', url: '/v1/omr/jobs', ...multipart(parts, fields, auth) });
  const finishJob = (id: string, status: 'done' | 'failed', errorCode: string | null = null) =>
    finish(dataDir, id, status, errorCode);

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

  it('создаёт задачу из фото и отдаёт её', async () => {
    const res = await upload([
      { name: 'стр1.jpg', data: JPEG },
      { name: 'стр2.png', data: PNG },
    ]);
    expect(res.statusCode).toBe(201);
    const job = OmrJob.parse(res.json());
    expect(job).toMatchObject({
      status: 'queued',
      source: { kind: 'images' },
      options: { timeSignature: 'auto' },
      result: null,
    });
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

  it('сохраняет размер, выбранный при загрузке', async () => {
    const res = await upload([{ name: 'a.png', data: PNG }], { timeSignature: '3/4' });
    expect(res.statusCode).toBe(201);
    expect(res.json().options).toEqual({ timeSignature: '3/4' });
    const got = await app.inject({
      method: 'GET',
      headers: auth,
      url: `/v1/omr/jobs/${res.json().id}`,
    });
    expect(got.json().options.timeSignature).toBe('3/4');
    // Пустое поле (так шлёт Swagger) — значение по умолчанию.
    const empty = await upload([{ name: 'a.png', data: PNG }], { timeSignature: '' });
    expect(empty.json().options.timeSignature).toBe('auto');
  });

  it('отклоняет неизвестный размер и не оставляет файлов', async () => {
    const res = await upload([{ name: 'a.png', data: PNG }], { timeSignature: '7/4' });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toMatchObject({ code: 'invalid_option' });
    expect(res.json().message).toContain('3/4');
    const list = await app.inject({ method: 'GET', headers: auth, url: '/v1/omr/jobs' });
    expect(list.json().items).toEqual([]);
    expect(jobDirs(dataDir)).toEqual([]);
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

  it('задаёт задаче постоянный оттенок сферы', async () => {
    const { id, hue } = (await upload([{ name: 'a.png', data: PNG }])).json();
    expect(Number.isInteger(hue) && hue >= 0 && hue < 360).toBe(true);
    const again = await app.inject({ method: 'GET', headers: auth, url: `/v1/omr/jobs/${id}` });
    expect(again.json().hue).toBe(hue);
  });

  it('inbox: карточки для библиотеки до скрытия', async () => {
    const working = (await upload([{ name: 'a.png', data: PNG }])).json().id;
    const failed = (await upload([{ name: 'b.png', data: PNG }])).json().id;
    const cancelled = (await upload([{ name: 'c.png', data: PNG }])).json().id;
    finishJob(failed, 'failed', 'no_music_found');
    await app.inject({ method: 'POST', headers: auth, url: `/v1/omr/jobs/${cancelled}/cancel` });
    const inbox = async () =>
      (await app.inject({ method: 'GET', headers: auth, url: '/v1/omr/jobs?inbox=true' }))
        .json()
        .items.map((j: { id: string }) => j.id)
        .sort();

    expect(await inbox()).toEqual([working, failed].sort());

    const busy = await app.inject({
      method: 'POST',
      headers: auth,
      url: `/v1/omr/jobs/${working}/dismiss`,
    });
    expect(busy.statusCode).toBe(409);
    expect(busy.json().code).toBe('not_finished');

    for (let i = 0; i < 2; i++) {
      const res = await app.inject({
        method: 'POST',
        headers: auth,
        url: `/v1/omr/jobs/${failed}/dismiss`,
      });
      expect(res.statusCode).toBe(200);
      expect(res.json().dismissedAt).not.toBeNull();
    }
    expect(await inbox()).toEqual([working]);
    const all = await app.inject({ method: 'GET', headers: auth, url: '/v1/omr/jobs' });
    expect(all.json().items).toHaveLength(3);
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
