import type { INestApplication } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { z } from 'zod';
// Импорт регистрирует схемы контракта (.meta({id})) в z.globalRegistry.
import '@piano/contracts';

/** Схемы контракта с `.meta({id})`, которые попадают в components.schemas. */
export type ContractSchema =
  | 'OmrJob'
  | 'OmrJobList'
  | 'ApiError'
  | 'DeviceRegistration'
  | 'Piece'
  | 'PieceList'
  | 'CreatePieceFromOmr'
  | 'UpdatePiece';

/** Ссылка на схему контракта в components.schemas. */
export const schemaRef = (name: ContractSchema) => ({
  $ref: `#/components/schemas/${name}`,
});

/** Схемы ответов берутся из zod-контрактов, а не дублируются DTO-классами. */
function contractSchemas(): Record<string, object> {
  const { schemas } = z.toJSONSchema(z.globalRegistry, {
    target: 'openapi-3.0',
    io: 'output',
    uri: (id) => `#/components/schemas/${id}`,
  });
  return Object.fromEntries(
    Object.entries(schemas).map(([name, { $id: _id, $schema: _schema, ...schema }]) => [
      name,
      schema,
    ]),
  );
}

export function setupSwagger(app: INestApplication): void {
  const config = new DocumentBuilder()
    .setTitle('piano-trainer API')
    .setDescription(
      'Распознавание нот (OMR) и библиотека пьес. Сначала получите токен устройства: ' +
        '`POST /v1/devices`, затем **Authorize** и вставьте token. Для распознавания запустите ' +
        'воркер: `pnpm dev:omr-worker`.',
    )
    .setVersion(process.env.npm_package_version ?? 'dev')
    .addBearerAuth({ type: 'http', scheme: 'bearer', description: 'Токен из POST /v1/devices' })
    .build();
  const document = SwaggerModule.createDocument(app, config);
  document.components = {
    ...document.components,
    schemas: { ...document.components?.schemas, ...contractSchemas() },
  };
  SwaggerModule.setup('docs', app, document, {
    jsonDocumentUrl: 'docs-json',
    swaggerOptions: {
      tryItOutEnabled: true,
      displayRequestDuration: true,
      persistAuthorization: true,
    },
  });
}
