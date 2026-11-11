import type { OmrJob, Piece, TimeSignatureChoice, UpdatePiece } from '@piano/contracts';
import { useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';

import {
  createPieceFromOmr,
  deletePiece,
  dismissJob,
  listInbox,
  listPieces,
  markPieceOpened,
  updatePiece,
  uploadOmr,
  type LocalFile,
} from '@/services/api/library';

import { failureText, jobProgress, jobTitle, pl } from './text';

export const keys = {
  pieces: ['pieces'] as const,
  inbox: ['inbox'] as const,
  upload: ['upload'] as const,
};

const isActive = (job: OmrJob) => job.status === 'queued' || job.status === 'processing';

export function usePieces() {
  return useQuery({ queryKey: keys.pieces, queryFn: listPieces });
}

/** Задачи распознавания для экрана библиотеки; пока есть задачи в работе — опрос каждые 2 с. */
export function useInbox() {
  return useQuery({
    queryKey: keys.inbox,
    queryFn: listInbox,
    refetchInterval: (query) => (query.state.data?.some(isActive) ? 2000 : false),
  });
}

/** Готовые задачи сами становятся пьесами: карточка «Оцифровка» сменяется пьесой с тегом «Новое». */
function useAutoAddDone(jobs: OmrJob[] | undefined) {
  const client = useQueryClient();
  const started = useRef(new Set<string>());
  useEffect(() => {
    for (const job of jobs ?? []) {
      if (job.status !== 'done' || started.current.has(job.id)) continue;
      started.current.add(job.id);
      createPieceFromOmr({ jobId: job.id })
        .then((piece) => {
          client.setQueryData<Piece[]>(keys.pieces, (old) => [
            piece,
            ...(old ?? []).filter((p) => p.id !== piece.id),
          ]);
          client.setQueryData<OmrJob[]>(keys.inbox, (old) => old?.filter((j) => j.id !== job.id));
        })
        .catch(() => started.current.delete(job.id));
    }
  }, [jobs, client]);
}

export type CardStatus = 'new' | 'digitizing' | 'failed' | null;

/** Карточка библиотеки: пьеса или задача распознавания (ARCHITECTURE §8.1). */
export type LibraryCard = {
  key: string;
  /** Параметр страницы произведения: id пьесы или job:<id>. */
  route: string;
  hue: number;
  title: string;
  composer: string;
  status: CardStatus;
  measureCount: number;
  errorCount: number;
  progress: { text: string; fraction: number } | null;
  failShort: string | null;
};

export function pieceCard(p: Piece): LibraryCard {
  return {
    key: p.id,
    route: p.id,
    hue: p.hue,
    title: p.title,
    composer: p.composer ?? 'Автор не указан',
    status: p.openedAt === null ? 'new' : null,
    measureCount: p.measureCount,
    errorCount: p.suspiciousMeasures.length,
    progress: null,
    failShort: null,
  };
}

export function jobCard(job: OmrJob): LibraryCard {
  const failed = job.status === 'failed';
  return {
    key: job.id,
    route: `job:${job.id}`,
    hue: job.hue,
    title: jobTitle(job),
    composer: failed
      ? (job.result?.composer ?? 'Автор не определён')
      : 'Название и автор определятся при распознавании',
    status: failed ? 'failed' : 'digitizing',
    measureCount: 0,
    errorCount: 0,
    progress: failed ? null : jobProgress(job),
    failShort: failed ? failureText(job.error?.code).short : null,
  };
}

/** Файл ещё отправляется на сервер: задачи пока нет, но карточка «Оцифровка» уже видна. */
function uploadCard(id: number, vars: UploadVars | undefined): LibraryCard {
  const files = vars?.files ?? [];
  const n = files.length;
  const pdf = files[0]?.type === 'application/pdf' ? files[0] : null;
  return {
    key: `upload-${id}`,
    route: '',
    hue: 215,
    title: pdf
      ? pdf.name.replace(/\.pdf$/i, '')
      : `Снимки · ${n} ${pl(n, 'страница', 'страницы', 'страниц')}`,
    composer: 'Название и автор определятся при распознавании',
    status: 'digitizing',
    measureCount: 0,
    errorCount: 0,
    progress: { text: 'Загружаем ноты на сервер', fraction: 0 },
    failShort: null,
  };
}

export function useLibrary() {
  const pieces = usePieces();
  const inbox = useInbox();
  useAutoAddDone(inbox.data);
  const uploading = useMutationState({
    filters: { mutationKey: keys.upload, status: 'pending' },
    select: (m) => ({ id: m.mutationId, vars: m.state.variables as UploadVars | undefined }),
  });

  const cards = useMemo(() => {
    const jobs = (inbox.data ?? [])
      .filter((j) => j.status !== 'cancelled')
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map(jobCard);
    const ready = [...(pieces.data ?? [])]
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map(pieceCard);
    return [...uploading.map((u) => uploadCard(u.id, u.vars)), ...jobs, ...ready];
  }, [pieces.data, inbox.data, uploading]);

  return {
    cards,
    pieceCount: pieces.data?.length ?? 0,
    isLoading: pieces.isPending && !pieces.data,
    error: pieces.error ?? inbox.error,
    refetch: () => Promise.all([pieces.refetch(), inbox.refetch()]),
    isRefetching: pieces.isRefetching || inbox.isRefetching,
  };
}

export type UploadVars = { files: LocalFile[]; timeSignature: TimeSignatureChoice };

/**
 * Загрузка нот. Колбэки заданы в самой мутации, а не в mutate(): шторка закрывается сразу,
 * а ответ приходит позже — карточку и тост об ошибке всё равно нужно показать.
 */
export function useUpload({ onError }: { onError: (error: unknown) => void }) {
  const client = useQueryClient();
  return useMutation({
    mutationKey: keys.upload,
    onError,
    mutationFn: (v: UploadVars) => uploadOmr(v.files, v.timeSignature),
    onSuccess: (job) => {
      client.setQueryData<OmrJob[]>(keys.inbox, (old) => [job, ...(old ?? [])]);
      void client.invalidateQueries({ queryKey: keys.inbox });
    },
  });
}

export function useDismissJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: dismissJob,
    onSuccess: (_, id) =>
      client.setQueryData<OmrJob[]>(keys.inbox, (old) => old?.filter((j) => j.id !== id)),
  });
}

const replacePiece = (piece: Piece) => (old: Piece[] | undefined) =>
  old?.map((p) => (p.id === piece.id ? piece : p));

export function useRenamePiece() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; body: UpdatePiece }) => updatePiece(v.id, v.body),
    onSuccess: (piece) => client.setQueryData<Piece[]>(keys.pieces, replacePiece(piece)),
  });
}

export function useDeletePiece() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: deletePiece,
    onSuccess: (_, id) =>
      client.setQueryData<Piece[]>(keys.pieces, (old) => old?.filter((p) => p.id !== id)),
  });
}

export function useMarkOpened() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: markPieceOpened,
    onSuccess: (piece) => client.setQueryData<Piece[]>(keys.pieces, replacePiece(piece)),
  });
}
