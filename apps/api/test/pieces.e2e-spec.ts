import { existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import type { NestFastifyApplication } from '@nestjs/platform-fastify';
import { Piece, PieceList } from '@piano/contracts';
import {
  PNG,
  byText,
  TEST_MUSICXML,
  TEST_REPORT,
  createTestApp,
  finishJob,
  multipart,
  registerDevice,
  type TestApp,
} from './helpers.js';

describe('Библиотека (e2e)', () => {
  let t: TestApp;
  let app: NestFastifyApplication;
  let auth: { authorization: string };

  beforeEach(async () => {
    t = await createTestApp();
    app = t.app;
    auth = await registerDevice(app);
  });

  afterEach(async () => {
    await t.close();
  });

  const request = (
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    url: string,
    payload?: object,
    headers: Record<string, string> = auth,
  ) => app.inject({ method, url, headers, ...(payload ? { payload } : {}) });

  /** Задача распознавания, доведённая «воркером» до конца. */
  async function recognizedJob(
    status: 'done' | 'failed' = 'done',
    errorCode: string | null = null,
    report: object = TEST_REPORT,
    headers = auth,
  ): Promise<string> {
    const res = await app.inject({
      method: 'POST',
      url: '/v1/omr/jobs',
      ...multipart([{ name: 'a.png', data: PNG }], {}, headers),
    });
    const { id } = res.json() as { id: string };
    finishJob(t.omrDir, id, status, errorCode, report);
    return id;
  }

  async function addPiece(body: object = {}): Promise<Piece> {
    const jobId = await recognizedJob();
    const res = await request('POST', '/v1/pieces/from-omr', { jobId, ...body });
    expect(res.statusCode).toBe(201);
    return Piece.parse(res.json());
  }

  describe('POST /v1/pieces/from-omr', () => {
    it('создаёт пьесу из распознанной задачи', async () => {
      const jobId = await recognizedJob();
      const res = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(res.statusCode).toBe(201);
      const piece = Piece.parse(res.json());
      expect(piece).toMatchObject({
        title: 'Лунная соната',
        composer: 'Л. ван Бетховен',
        sourceKind: 'omr',
        omrJobId: jobId,
        measureCount: 2,
        unscoredMeasures: [1],
        timeSignature: '4/4',
        timeSignatureSource: 'engine',
        keyFifths: 0,
        tempoText: 'Adagio sostenuto',
        tempoBpm: 52,
        deletedAt: null,
        scoreUrl: `/v1/pieces/${piece.id}/score.musicxml`,
      });
      expect(existsSync(join(t.dataDir, 'library', piece.id, 'score.musicxml'))).toBe(true);
    });

    it('переносит ошибки тактов, смены размера и оттенок; убирает карточку задачи', async () => {
      const jobId = await recognizedJob();
      const job = (await request('GET', `/v1/omr/jobs/${jobId}`)).json();
      const inbox = async () =>
        (await request('GET', '/v1/omr/jobs?inbox=true'))
          .json()
          .items.map((j: { id: string }) => j.id);
      expect(await inbox()).toEqual([jobId]);

      const piece = Piece.parse((await request('POST', '/v1/pieces/from-omr', { jobId })).json());
      expect(piece.hue).toBe(job.hue);
      expect(piece.openedAt).toBeNull();
      expect(piece.timeSignatureChanges).toEqual([{ index: 1, number: '2', timeSignature: '5/4' }]);
      expect(piece.suspiciousMeasures).toEqual([
        {
          index: 1,
          number: '2',
          page: 1,
          reasons: ['overflow'],
          staff: null,
          length: 4.5,
          expectedLength: 4,
        },
      ]);
      expect(await inbox()).toEqual([]);
    });

    it('читает отчёт без подробностей (задачи до обновления воркера)', async () => {
      const { timeSignatureChanges: _changes, ...old } = TEST_REPORT;
      const jobId = await recognizedJob('done', null, {
        ...old,
        suspiciousMeasures: [{ index: 1, number: '2', page: 1, reasons: ['empty'] }],
      });
      const res = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(res.statusCode).toBe(201);
      expect(res.json().timeSignatureChanges).toEqual([]);
      expect(res.json().suspiciousMeasures[0]).toMatchObject({ staff: null, length: null });
    });

    it('берёт название и автора из запроса, без названия — «Без названия»', async () => {
      const named = await addPiece({ title: '  Своё  ', composer: '' });
      expect(named).toMatchObject({ title: 'Своё', composer: null });

      const jobId = await recognizedJob('done', null, { ...TEST_REPORT, title: null });
      const res = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(res.json().title).toBe('Без названия');
    });

    it('повторный вызов возвращает ту же пьесу, удалённую — восстанавливает', async () => {
      const jobId = await recognizedJob();
      const first = (await request('POST', '/v1/pieces/from-omr', { jobId })).json();
      const again = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(again.statusCode).toBe(200);
      expect(again.json().id).toBe(first.id);

      await request('DELETE', `/v1/pieces/${first.id}`);
      const restored = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(restored.statusCode).toBe(200);
      expect(restored.json()).toMatchObject({ id: first.id, deletedAt: null });
    });

    it('параллельные вызовы создают одну пьесу', async () => {
      const jobId = await recognizedJob();
      const results = await Promise.all(
        [1, 2, 3].map(() => request('POST', '/v1/pieces/from-omr', { jobId })),
      );
      expect(new Set(results.map((r) => r.json().id)).size).toBe(1);
      expect(results.map((r) => r.statusCode).sort((a, b) => a - b)).toEqual([200, 200, 201]);
      const list = PieceList.parse((await request('GET', '/v1/pieces')).json());
      expect(list.items).toHaveLength(1);
    });

    it('при low_quality пьеса создаётся с подозрительными тактами', async () => {
      const jobId = await recognizedJob('failed', 'low_quality');
      const res = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(res.statusCode).toBe(201);
      expect(res.json().unscoredMeasures).toEqual([1]);
    });

    it('409, пока результата нет', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/v1/omr/jobs',
        ...multipart([{ name: 'a.png', data: PNG }], {}, auth),
      });
      const created = await request('POST', '/v1/pieces/from-omr', { jobId: res.json().id });
      expect(created.statusCode).toBe(409);
      expect(created.json().code).toBe('result_not_ready');
    });

    it('чужая задача — 404', async () => {
      const other = await registerDevice(app);
      const jobId = await recognizedJob('done', null, TEST_REPORT, other);
      const res = await request('POST', '/v1/pieces/from-omr', { jobId });
      expect(res.statusCode).toBe(404);
    });

    it.each([
      ['без jobId', {}],
      ['jobId не uuid', { jobId: 'nope' }],
      ['пустое название', { jobId: '01900000-0000-7000-8000-000000000000', title: '  ' }],
    ])('400 invalid_request: %s', async (_name, body) => {
      const res = await request('POST', '/v1/pieces/from-omr', body);
      expect(res.statusCode).toBe(400);
      expect(res.json().code).toBe('invalid_request');
    });
  });

  it('GET, PATCH, DELETE пьесы', async () => {
    const piece = await addPiece();
    const got = await request('GET', `/v1/pieces/${piece.id}`);
    expect(got.json()).toEqual(piece);

    const renamed = await request('PATCH', `/v1/pieces/${piece.id}`, { title: 'Соната №14' });
    expect(renamed.json()).toMatchObject({ title: 'Соната №14', composer: 'Л. ван Бетховен' });
    expect(renamed.json().updatedAt >= piece.updatedAt).toBe(true);
    const noComposer = await request('PATCH', `/v1/pieces/${piece.id}`, { composer: null });
    expect(noComposer.json()).toMatchObject({ title: 'Соната №14', composer: null });
    const empty = await request('PATCH', `/v1/pieces/${piece.id}`, {});
    expect(empty.statusCode).toBe(400);

    expect((await request('DELETE', `/v1/pieces/${piece.id}`)).statusCode).toBe(204);
    expect((await request('DELETE', `/v1/pieces/${piece.id}`)).statusCode).toBe(204);
    expect((await request('GET', `/v1/pieces/${piece.id}`)).statusCode).toBe(404);
    expect((await request('PATCH', `/v1/pieces/${piece.id}`, { title: 'x' })).statusCode).toBe(404);
  });

  it('отметка открытия снимает «Новое» один раз', async () => {
    const piece = await addPiece();
    const first = await request('POST', `/v1/pieces/${piece.id}/opened`);
    expect(first.statusCode).toBe(200);
    const openedAt = first.json().openedAt;
    expect(openedAt).not.toBeNull();
    expect(first.json().updatedAt >= piece.updatedAt).toBe(true);
    const again = await request('POST', `/v1/pieces/${piece.id}/opened`);
    expect(again.json().openedAt).toBe(openedAt);
  });

  it('пьесы другого устройства не видны', async () => {
    const piece = await addPiece();
    const other = await registerDevice(app);
    for (const [method, url] of [
      ['GET', `/v1/pieces/${piece.id}`],
      ['GET', `/v1/pieces/${piece.id}/score.musicxml`],
      ['DELETE', `/v1/pieces/${piece.id}`],
    ] as const) {
      expect((await request(method, url, undefined, other)).statusCode).toBe(404);
    }
    const list = await request('GET', '/v1/pieces', undefined, other);
    expect(list.json().items).toEqual([]);
    expect((await request('GET', '/v1/pieces', undefined, {})).statusCode).toBe(401);
  });

  describe('GET /v1/pieces', () => {
    it('ищет по названию и автору без учёта регистра', async () => {
      await addPiece({ title: 'Лунная соната', composer: 'Бетховен' });
      await addPiece({ title: 'К Элизе', composer: 'Бетховен' });
      await addPiece({ title: 'Вальс', composer: 'Шопен' });

      const titles = async (q: string) =>
        PieceList.parse(
          (await request('GET', `/v1/pieces?q=${encodeURIComponent(q)}`)).json(),
        ).items.map((p) => p.title);
      expect(await titles('ЛУННАЯ')).toEqual(['Лунная соната']);
      expect((await titles('бетховен')).sort(byText)).toEqual(['К Элизе', 'Лунная соната']);
      expect(await titles('100%')).toEqual([]);
    });

    it('листает страницами', async () => {
      for (let i = 0; i < 5; i++) await addPiece({ title: `Пьеса ${i}` });
      const seen: string[] = [];
      let cursor: string | null = null;
      do {
        const url: string = `/v1/pieces?limit=2${cursor ? `&cursor=${cursor}` : ''}`;
        const page = PieceList.parse((await request('GET', url)).json());
        expect(page.items.length).toBeLessThanOrEqual(2);
        seen.push(...page.items.map((p) => p.title));
        cursor = page.nextCursor;
      } while (cursor);
      expect(seen.sort(byText)).toEqual(['Пьеса 0', 'Пьеса 1', 'Пьеса 2', 'Пьеса 3', 'Пьеса 4']);

      const bad = await request('GET', '/v1/pieces?cursor=мусор');
      expect(bad.json().code).toBe('invalid_request');
    });

    it('с updatedSince отдаёт изменения, включая удалённые', async () => {
      const kept = await addPiece({ title: 'Останется' });
      const removed = await addPiece({ title: 'Удалится' });
      // updatedSince включительный: разводим время создания и serverTime.
      await new Promise((r) => setTimeout(r, 5));
      const first = PieceList.parse((await request('GET', '/v1/pieces')).json());
      expect(first.items).toHaveLength(2);

      await new Promise((r) => setTimeout(r, 5));
      await request('DELETE', `/v1/pieces/${removed.id}`);
      const changes = PieceList.parse(
        (await request('GET', `/v1/pieces?updatedSince=${first.serverTime}`)).json(),
      );
      expect(changes.items.map((p) => [p.id, p.deletedAt !== null])).toEqual([[removed.id, true]]);

      const live = PieceList.parse((await request('GET', '/v1/pieces')).json());
      expect(live.items.map((p) => p.id)).toEqual([kept.id]);

      const bad = await request('GET', '/v1/pieces?updatedSince=вчера');
      expect(bad.statusCode).toBe(400);
    });
  });

  it('отдаёт MusicXML пьесы с ETag', async () => {
    const piece = await addPiece();
    const res = await request('GET', piece.scoreUrl);
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-type']).toContain('musicxml');
    expect(res.body).toBe(TEST_MUSICXML);
    const etag = res.headers.etag as string;
    expect(etag).toBeTruthy();

    const cached = await app.inject({
      method: 'GET',
      url: piece.scoreUrl,
      headers: { ...auth, 'if-none-match': etag },
    });
    expect(cached.statusCode).toBe(304);
    expect(cached.body).toBe('');
  });

  it('пьеса переживает удаление задачи распознавания', async () => {
    const piece = await addPiece();
    rmSync(join(t.omrDir, 'jobs', piece.omrJobId!), { recursive: true });
    const res = await request('GET', piece.scoreUrl);
    expect(res.body).toBe(TEST_MUSICXML);
  });

  it('Swagger описывает библиотеку', async () => {
    const doc = (await app.inject({ method: 'GET', url: '/docs-json' })).json();
    expect(doc.paths['/v1/pieces/from-omr']).toBeDefined();
    expect(doc.paths['/v1/devices']).toBeDefined();
    expect(doc.components.schemas.Piece.properties.unscoredMeasures).toBeDefined();
    expect(doc.components.schemas.CreatePieceFromOmr.required).toContain('jobId');
    expect(doc.components.securitySchemes.bearer).toBeDefined();
  });
});
