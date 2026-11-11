import {
  OmrJob,
  OmrJobList,
  Piece,
  PieceList,
  type CreatePieceFromOmr,
  type TimeSignatureChoice,
  type UpdatePiece,
} from '@piano/contracts';

import { apiForm, apiJson, apiSend } from './client';

/** Файл с телефона для загрузки: uri из пикера. */
export type LocalFile = { uri: string; name: string; type: string; size?: number };

/** POST /v1/omr/jobs: один PDF или до 10 фото по порядку страниц. */
export function uploadOmr(files: LocalFile[], timeSignature: TimeSignatureChoice): Promise<OmrJob> {
  const form = new FormData();
  for (const file of files) {
    // React Native отправляет часть формы с файлом по объекту { uri, name, type }.
    form.append('files', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
  }
  form.append('timeSignature', timeSignature);
  return apiForm(OmrJob, '/omr/jobs', form);
}

/** Карточки задач для экрана библиотеки: в очереди, в работе, с ошибкой (не убранные). */
export async function listInbox(): Promise<OmrJob[]> {
  return (await apiJson(OmrJobList, '/omr/jobs?inbox=true&limit=50')).items;
}

export function dismissJob(id: string): Promise<void> {
  return apiSend(`/omr/jobs/${id}/dismiss`, { method: 'POST' });
}

/** Все неудалённые пьесы, страница за страницей. */
export async function listPieces(): Promise<Piece[]> {
  const items: Piece[] = [];
  let cursor: string | null = null;
  do {
    const query: string = cursor ? `?limit=200&cursor=${encodeURIComponent(cursor)}` : '?limit=200';
    const page: PieceList = await apiJson(PieceList, `/pieces${query}`);
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor);
  return items;
}

export function createPieceFromOmr(body: CreatePieceFromOmr): Promise<Piece> {
  return apiJson(Piece, '/pieces/from-omr', { method: 'POST', body });
}

export function updatePiece(id: string, body: UpdatePiece): Promise<Piece> {
  return apiJson(Piece, `/pieces/${id}`, { method: 'PATCH', body });
}

export function deletePiece(id: string): Promise<void> {
  return apiSend(`/pieces/${id}`, { method: 'DELETE' });
}

export function markPieceOpened(id: string): Promise<Piece> {
  return apiJson(Piece, `/pieces/${id}/opened`, { method: 'POST' });
}
