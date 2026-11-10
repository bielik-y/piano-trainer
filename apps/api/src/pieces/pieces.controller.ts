import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Inject,
  Param,
  Patch,
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
  ApiNoContentResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiProduces,
  ApiQuery,
  ApiResponse,
  ApiTags,
} from '@nestjs/swagger';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { CreatePieceFromOmr, UpdatePiece, type Piece, type PieceList } from '@piano/contracts';
import { ApiException } from '../common/api-exception.js';
import type { DeviceRecord } from '../devices/device-repository.js';
import { CurrentDevice, DeviceGuard } from '../devices/device.guard.js';
import { schemaRef } from '../swagger.js';
import { PiecesService } from './pieces.service.js';

const ERROR = { schema: schemaRef('ApiError') };
const PIECE_ID = ApiParam({ name: 'id', description: 'id пьесы (UUIDv7)' });

const ListQuery = z.object({
  q: z.string().max(200).optional(),
  updatedSince: z.iso.datetime().optional(),
  cursor: z.string().max(500).optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
});

/** Тело или query по схеме контракта; ошибка — 400 invalid_request с полем и причиной. */
function parse<T extends z.ZodType>(schema: T, value: unknown): z.infer<T> {
  const result = schema.safeParse(value ?? {});
  if (result.success) return result.data;
  const issue = result.error.issues[0]!;
  const field = issue.path.join('.') || 'тело запроса';
  throw new ApiException(HttpStatus.BAD_REQUEST, 'invalid_request', `${field}: ${issue.message}`);
}

@ApiTags('pieces')
@ApiBearerAuth()
@ApiResponse({ status: 401, description: 'unauthorized — нет токена устройства', ...ERROR })
@UseGuards(DeviceGuard)
@Controller('pieces')
export class PiecesController {
  constructor(@Inject(PiecesService) private readonly pieces: PiecesService) {}

  @Post('from-omr')
  @ApiOperation({
    summary: 'Добавить в библиотеку результат распознавания',
    description:
      'Создаёт пьесу из задачи со статусом done или failed/low_quality: MusicXML копируется ' +
      'к пьесе, название, автор, размер и темп берутся из отчёта, подозрительные такты ' +
      'попадают в unscoredMeasures. Повторный вызов для той же задачи вернёт ту же пьесу ' +
      '(200), удалённую — восстановит.',
  })
  @ApiBody({ schema: schemaRef('CreatePieceFromOmr') })
  @ApiResponse({ status: 201, description: 'Пьеса создана', schema: schemaRef('Piece') })
  @ApiResponse({ status: 200, description: 'Пьеса уже была', schema: schemaRef('Piece') })
  @ApiResponse({ status: 400, description: 'invalid_request', ...ERROR })
  @ApiResponse({ status: 404, description: 'Задачи нет', ...ERROR })
  @ApiResponse({ status: 409, description: 'result_not_ready', ...ERROR })
  async createFromOmr(
    @CurrentDevice() device: DeviceRecord,
    @Body() body: unknown,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<Piece> {
    const { piece, created } = await this.pieces.createFromOmr(
      device.id,
      parse(CreatePieceFromOmr, body),
    );
    reply.status(created ? HttpStatus.CREATED : HttpStatus.OK);
    return piece;
  }

  @Get()
  @ApiOperation({
    summary: 'Пьесы устройства',
    description:
      'Порядок — по возрастанию updatedAt. Без updatedSince — только неудалённые. ' +
      '**Синхронизация кэша**: передайте updatedSince = serverTime прошлого ответа — придут ' +
      'все изменённые с того момента, включая удалённые (deletedAt не null). Страницы — ' +
      'через cursor = nextCursor.',
  })
  @ApiQuery({ name: 'q', required: false, description: 'Поиск по названию и автору' })
  @ApiQuery({
    name: 'updatedSince',
    required: false,
    description: 'ISO-время: изменённые не раньше него, включая удалённые',
  })
  @ApiQuery({ name: 'cursor', required: false, description: 'nextCursor прошлого ответа' })
  @ApiQuery({ name: 'limit', required: false, schema: { type: 'integer', default: 50 } })
  @ApiOkResponse({ schema: schemaRef('PieceList') })
  @ApiResponse({ status: 400, description: 'invalid_request', ...ERROR })
  list(@CurrentDevice() device: DeviceRecord, @Query() query: unknown): PieceList {
    return this.pieces.list(device.id, parse(ListQuery, query));
  }

  @Get(':id')
  @PIECE_ID
  @ApiOperation({ summary: 'Пьеса' })
  @ApiOkResponse({ schema: schemaRef('Piece') })
  @ApiResponse({ status: 404, ...ERROR })
  get(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): Piece {
    return this.pieces.get(device.id, id);
  }

  @Patch(':id')
  @PIECE_ID
  @ApiOperation({
    summary: 'Переименовать',
    description: 'Меняет title и/или composer. composer = null или пустая строка — без автора.',
  })
  @ApiBody({ schema: schemaRef('UpdatePiece') })
  @ApiOkResponse({ schema: schemaRef('Piece') })
  @ApiResponse({ status: 400, description: 'invalid_request', ...ERROR })
  @ApiResponse({ status: 404, ...ERROR })
  update(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
    @Body() body: unknown,
  ): Piece {
    return this.pieces.update(device.id, id, parse(UpdatePiece, body));
  }

  @Post(':id/opened')
  @HttpCode(HttpStatus.OK)
  @PIECE_ID
  @ApiOperation({
    summary: 'Отметить, что пьесу открыли',
    description:
      'Вызывается при первом открытии страницы произведения: openedAt перестаёт быть null, ' +
      'и у карточки пропадает тег «Новое». Повторный вызов ничего не меняет.',
  })
  @ApiOkResponse({ schema: schemaRef('Piece') })
  @ApiResponse({ status: 404, ...ERROR })
  opened(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): Piece {
    return this.pieces.markOpened(device.id, id);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @PIECE_ID
  @ApiOperation({
    summary: 'Удалить',
    description:
      'Мягкое удаление: пьеса пропадает из списка и GET, но в синхронизации приходит с ' +
      'deletedAt, чтобы кэш на телефоне её убрал. Повторное удаление — тоже 204.',
  })
  @ApiNoContentResponse()
  @ApiResponse({ status: 404, ...ERROR })
  remove(@CurrentDevice() device: DeviceRecord, @Param('id') id: string): void {
    this.pieces.remove(device.id, id);
  }

  @Get(':id/score.musicxml')
  @PIECE_ID
  @ApiOperation({
    summary: 'Скачать MusicXML пьесы',
    description: 'Поддерживает ETag / If-None-Match: неизменившийся файл — 304 без тела.',
  })
  @ApiProduces('application/vnd.recordare.musicxml+xml')
  @ApiOkResponse({ schema: { type: 'string', format: 'binary' } })
  @ApiResponse({ status: 304, description: 'Файл не изменился' })
  @ApiResponse({ status: 404, ...ERROR })
  async score(
    @CurrentDevice() device: DeviceRecord,
    @Param('id') id: string,
    @Req() req: FastifyRequest,
    @Res({ passthrough: true }) reply: FastifyReply,
  ): Promise<StreamableFile | undefined> {
    const file = await this.pieces.score(device.id, id);
    reply.header('ETag', file.etag).header('Cache-Control', 'private, no-cache');
    if (req.headers['if-none-match'] === file.etag) {
      file.stream.destroy();
      reply.status(HttpStatus.NOT_MODIFIED);
      return undefined;
    }
    return new StreamableFile(file.stream, {
      type: file.contentType,
      length: file.size,
      disposition: `attachment; filename="${file.fileName}"`,
    });
  }
}
