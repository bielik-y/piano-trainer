import type { INestApplication } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { z } from 'zod';
// Импорт регистрирует схемы контракта (.meta({id})) в z.globalRegistry.
import '@piano/contracts';

/** Ссылка на схему контракта в components.schemas (OmrJob, OmrJobList, ApiError). */
export const schemaRef = (name: 'OmrJob' | 'OmrJobList' | 'ApiError') => ({
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
      'Распознавание нот (OMR): загрузите PDF или фото, следите за прогрессом, скачайте ' +
      'MusicXML. Сначала запустите воркер: `pnpm dev:omr-worker`.',
    )
    .setVersion(process.env.npm_package_version ?? 'dev')
    .build();
  const document = SwaggerModule.createDocument(app, config);
  document.components = {
    ...document.components,
    schemas: { ...document.components?.schemas, ...contractSchemas() },
  };
  SwaggerModule.setup('docs', app, document, {
    jsonDocumentUrl: 'docs-json',
    swaggerOptions: { tryItOutEnabled: true, displayRequestDuration: true },
  });
}
