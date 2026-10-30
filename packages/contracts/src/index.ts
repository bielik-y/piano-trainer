/**
 * contracts: zod-схемы API, общие для apps/api и apps/mobile.
 * См. docs/ARCHITECTURE.md §8.
 */
import { z } from 'zod';

export const OmrSourceKind = z.enum(['pdf', 'image']);
export type OmrSourceKind = z.infer<typeof OmrSourceKind>;

export const OmrJobStatus = z.enum(['awaiting_upload', 'queued', 'processing', 'done', 'failed']);
export type OmrJobStatus = z.infer<typeof OmrJobStatus>;

export const CreateOmrJobRequest = z.object({
  sourceKind: OmrSourceKind,
  fileName: z.string().min(1).max(255),
  contentType: z.string(),
  pageCount: z.number().int().positive().optional(),
});
export type CreateOmrJobRequest = z.infer<typeof CreateOmrJobRequest>;

export const CreateOmrJobResponse = z.object({
  jobId: z.uuid(),
  uploadUrl: z.url(),
});
export type CreateOmrJobResponse = z.infer<typeof CreateOmrJobResponse>;

export const OmrJob = z.object({
  id: z.uuid(),
  status: OmrJobStatus,
  createdAt: z.iso.datetime(),
  /** Ссылки появляются при status = done. */
  result: z
    .object({
      musicXmlUrl: z.url(),
      measuresUrl: z.url(),
    })
    .optional(),
  error: z.string().optional(),
});
export type OmrJob = z.infer<typeof OmrJob>;

export const HealthResponse = z.object({
  status: z.literal('ok'),
  version: z.string(),
});
export type HealthResponse = z.infer<typeof HealthResponse>;
