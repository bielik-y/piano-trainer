import {
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Inject,
  Param,
  Post,
  Query,
  Req,
  Res,
  StreamableFile,
  UseGuards,
} from '@nestjs/common';
import {
  ApiBearerAuth,
  ApiBody,
  ApiConsumes,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiProduces,
  ApiQuery,
  ApiResponse,
  ApiTags,
} from '@nestjs/swagger';
import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  OMR_TERMINAL_STATUSES,
  TimeSignatureChoice,
  type OmrJob,
  type OmrJobList,
} from '@piano/contracts';
import { ApiException } from '../common/api-exception.js';
import { schemaRef } from '../swagger.js';
import { OMR_CONFIG, type OmrConfig } from '../config.js';
import type { DeviceRecord } from '../devices/device-repository.js';
import { CurrentDevice, DeviceGuard } from '../devices/device.guard.js';
import { OmrService, type UploadPart } from './omr.service.js';

const ERROR = { schema: schemaRef('ApiError') };
const JOB_ID = ApiParam({ name: 'id', description: 'id задачи (UUIDv7)' });

@ApiTags('omr')
@ApiBearerAuth()
@ApiResponse({ status: 401, description: 'unauthorized — нет токена устройства', ...ERROR })
@UseGuards(DeviceGuard)
@Controller('omr/jobs')
export class OmrController {
  constructor(
    @Inject(OmrService) private readonly omr: OmrService,
    @Inject(OMR_CONFIG) private readonly config: OmrConfig,
  ) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({
    summary: 'Создать задачу распознавания',
    description:
      'Загрузите **один PDF** (до 20 страниц) или **от 1 до 10 фото** одной композиции ' +
      '(JPEG, PNG, HEIC) в порядке страниц, каждый файл до 25 МБ. Тип определяется по ' +
      'содержимому. Необязательное поле `timeSignature` задаёт размер, если автоматически ' +
      'он определяется неверно. Задача сразу встаёт в очередь; дальше следите за ней через ' +
      '`GET /v1/omr/jobs/{id}` или поток `GET /v1/omr/jobs/{id}/events`.',
  })
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      required: ['files'],
      properties: {
        files: {
          type: 'array',
          items: { type: 'string', format: 'binary' },
          description: '1 PDF или 1–10 фото',
        },
        timeSignature: {
          type: 'string',
          enum: TimeSignatureChoice.options,
          default: 'auto',
          description: 'Размер пьесы; auto — определить по нотам',
        },
      },
    },
  })
  @ApiResponse({ status: 201, description: 'Задача создана', schema: schemaRef('OmrJob') })
  @ApiResponse({
    status: 400,
    description: 'no_files, mixed_sources, too_many_files, invalid_option',
    ...ERROR,
  })
  @ApiResponse({ status: 413, description: 'file_too_large', ...ERROR })
  @ApiResponse({ status: 415, description: 'unsupported_file_type', ...ERROR })
  create(@CurrentDevice() device: DeviceRecord, @Req() req: FastifyRequest): Promise<OmrJob> {
    if (!req.isMultipart()) {
      throw new ApiException(
        HttpStatus.BAD_REQUEST,
        'no_files',
        'Ожидается multipart/form-data с файлами в поле files',
      );
    }
    return this.omr.create(device.id, uploadParts(req, this.config.maxImages));
  }

  @Get()
  @ApiOperation({
    summary: 'Последние задачи',
    description:
      'С inbox=true — только карточки для экрана библиотеки: в очереди, в работе и ' +
      'завершённые, которые ещё не скрыты (`POST …/dismiss`, или пьеса добавлена). ' +
      'queued/processing — «Оцифровка», failed — «Ошибка».',
  })
  @ApiQuery({ name: 'limit', required: false, schema: { type: 'integer', default: 20 } })
  @ApiQuery({ name: 'inbox', required: false, schema: { type: 'boolean', default: false } })
  @ApiOkResponse({ schema: schemaRef('OmrJobList') })
  list(
    @CurrentDevice() device: DeviceRecord,
    @Query('limit') limit?: string,
    @Query('inbox') inbox?: string,
  ): OmrJobList {
    const n = Math.min(Math.max(Number(limit ?? 20) || 20, 1), 100);
    return { items: this.omr.list(device.id, n, inbox === 'true' || inbox === '1') };
  }

  @Get(':id')
  @JOB_ID
  @ApiOperation({
    summary: 'Задача: статус, прогресс, страницы, результат или ошибка',
    description:
      'status: queued → processing → done | failed | cancelled. При failed с error.code = ' +
      'low_quality поле result заполнено: MusicXML можно скачать.',
  })
  @ApiOkResponse({ schema: schemaRef('OmrJob') })
  @ApiResponse({ status: 404, ...ERROR })
  get(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): OmrJob {
    return this.omr.get(device.id, id);
  }

  @Get(':id/events')
  @JOB_ID
  @ApiOperation({
    summary: 'Поток событий задачи (SSE)',
    description:
      'Server-Sent Events. Сразу приходит текущее состояние, затем событие при каждом ' +
      'изменении: `progress`, в конце `done`, `failed` или `cancelled`, после чего поток ' +
      'закрывается. В `data` — задача целиком (как в GET /v1/omr/jobs/{id}), в `id` — её ' +
      'revision. Swagger покажет события только после завершения задачи; смотреть вживую — ' +
      '`curl -N -H "Authorization: Bearer <токен>" ' +
      'http://localhost:3000/v1/omr/jobs/{id}/events`.',
  })
  @ApiProduces('text/event-stream')
  @ApiOkResponse({ description: 'Поток text/event-stream' })
  @ApiResponse({ status: 404, ...ERROR })
  events(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
    @Req() req: FastifyRequest,
    @Res() reply: FastifyReply,
  ): void {
    let last = this.omr.get(device.id, id).revision - 1; // 404 до начала потока
    reply.hijack();
    const raw = reply.raw;
    raw.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    raw.write('retry: 2000\n\n');

    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      clearInterval(timer);
      clearInterval(heartbeat);
      raw.end();
    };
    const tick = () => {
      if (closed) return;
      const revision = this.omr.revision(id);
      if (revision === null) return close();
      if (revision === last) return;
      const job = this.omr.get(device.id, id);
      last = job.revision;
      const terminal = OMR_TERMINAL_STATUSES.includes(job.status);
      const event = terminal ? job.status : 'progress';
      raw.write(`id: ${job.revision}\nevent: ${event}\ndata: ${JSON.stringify(job)}\n\n`);
      if (terminal) close();
    };
    const timer = setInterval(tick, this.config.eventsPollMs);
    const heartbeat = setInterval(() => raw.write(': ping\n\n'), 15_000);
    req.raw.on('close', close);
    tick();
  }

  @Post(':id/cancel')
  @HttpCode(HttpStatus.OK)
  @JOB_ID
  @ApiOperation({
    summary: 'Отменить задачу',
    description:
      'Задача в очереди отменяется сразу. У задачи в работе ставится cancelRequested, ' +
      'воркер останавливается в течение секунды и переводит её в cancelled.',
  })
  @ApiOkResponse({ schema: schemaRef('OmrJob') })
  @ApiResponse({ status: 404, ...ERROR })
  @ApiResponse({ status: 409, description: 'already_finished', ...ERROR })
  cancel(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): OmrJob {
    return this.omr.cancel(device.id, id);
  }

  @Post(':id/dismiss')
  @HttpCode(HttpStatus.OK)
  @JOB_ID
  @ApiOperation({
    summary: 'Убрать карточку задачи из библиотеки',
    description:
      'Например, пользователь посмотрел ошибку распознавания. Задача остаётся доступной по id ' +
      'до автоудаления. При добавлении пьесы (`POST /v1/pieces/from-omr`) скрывается сама.',
  })
  @ApiOkResponse({ schema: schemaRef('OmrJob') })
  @ApiResponse({ status: 404, ...ERROR })
  @ApiResponse({ status: 409, description: 'not_finished — задача ещё распознаётся', ...ERROR })
  dismiss(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): OmrJob {
    return this.omr.dismiss(device.id, id);
  }

  @Get(':id/result.musicxml')
  @JOB_ID
  @ApiOperation({
    summary: 'Скачать MusicXML',
    description: 'Есть при status = done и при failed с кодом low_quality.',
  })
  @ApiProduces('application/vnd.recordare.musicxml+xml')
  @ApiOkResponse({ schema: { type: 'string', format: 'binary' } })
  @ApiResponse({ status: 409, description: 'result_not_ready', ...ERROR })
  async musicXml(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
  ): Promise<StreamableFile> {
    return toStreamable(await this.omr.download(device.id, id, 'musicxml'), 'attachment');
  }

  @Get(':id/report.json')
  @JOB_ID
  @ApiOperation({
    summary: 'Скачать отчёт по тактам',
    description: 'OmrReport + список страниц: какие такты подозрительны и почему.',
  })
  @ApiProduces('application/json')
  @ApiOkResponse({ schema: { type: 'string', format: 'binary' } })
  @ApiResponse({ status: 409, description: 'result_not_ready', ...ERROR })
  async report(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
  ): Promise<StreamableFile> {
    return toStreamable(await this.omr.download(device.id, id, 'report'), 'attachment');
  }

  @Get(':id/pages/:page')
  @JOB_ID
  @ApiParam({ name: 'page', description: 'Номер страницы с 1', schema: { type: 'integer' } })
  @ApiOperation({ summary: 'Страница после предобработки (PNG) — то, что получил движок' })
  @ApiProduces('image/png')
  @ApiOkResponse({ schema: { type: 'string', format: 'binary' } })
  @ApiResponse({ status: 404, ...ERROR })
  async page(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
    @Param('page') page: string,
  ): Promise<StreamableFile> {
    return toStreamable(await this.omr.page(device.id, id, Number(page)), 'inline');
  }
}

async function* uploadParts(req: FastifyRequest, maxImages: number): AsyncIterable<UploadPart> {
  try {
    for await (const part of req.parts()) {
      if (part.type === 'file') {
        yield { kind: 'file', filename: part.filename, stream: part.file };
      } else {
        const value = typeof part.value === 'string' ? part.value : '';
        yield { kind: 'field', name: part.fieldname, value };
      }
    }
  } catch (e) {
    if ((e as { code?: string }).code === 'FST_FILES_LIMIT') {
      throw new ApiException(
        HttpStatus.BAD_REQUEST,
        'too_many_files',
        `Можно не больше ${maxImages} фото`,
      );
    }
    throw e;
  }
}

function toStreamable(
  file: { stream: NodeJS.ReadableStream; size: number; contentType: string; fileName: string },
  disposition: 'attachment' | 'inline',
): StreamableFile {
  return new StreamableFile(file.stream as never, {
    type: file.contentType,
    length: file.size,
    disposition: `${disposition}; filename="${file.fileName}"`,
  });
}
