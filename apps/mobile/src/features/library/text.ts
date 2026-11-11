import type { OmrErrorCode, OmrJob, Piece } from '@piano/contracts';

/** Русское склонение по числу: 1 такт, 2 такта, 5 тактов. */
export function pl(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 10;
  const b = Math.abs(n) % 100;
  if (a === 1 && b !== 11) return one;
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return few;
  return many;
}

export const measuresText = (n: number) => `${n} ${pl(n, 'такт', 'такта', 'тактов')}`;
export const piecesCountText = (n: number) =>
  `${n} ${pl(n, 'произведение', 'произведения', 'произведений')}`;

/** Что показать на карточке и странице задачи, которая не распозналась. */
export function failureText(code: OmrErrorCode | undefined): { short: string; long: string } {
  switch (code) {
    case 'low_quality':
      return {
        short: 'Не удалось распознать',
        long: 'Нормально распознано меньше 40 % тактов. Попробуйте PDF лучшего качества или более чёткие фото.',
      };
    case 'unreadable_file':
      return {
        short: 'Файл не открылся',
        long: 'Проверьте, что это PDF или фото, и загрузите снова.',
      };
    case 'too_many_pages':
      return { short: 'Больше 20 страниц', long: 'Разделите PDF на части до 20 страниц.' };
    case 'no_music_found':
      return {
        short: 'Ноты не найдены',
        long: 'На страницах не нашлось нотных строк. Снимайте ноты ровно и при хорошем свете.',
      };
    default:
      return {
        short: 'Не удалось распознать',
        long: 'Сбой распознавания. Попробуйте загрузить ещё раз.',
      };
  }
}

/** Название задачи, пока ноты не распознаны: имя файла или «Снимки · 3 страницы». */
export function jobTitle(job: OmrJob): string {
  if (job.result?.title) return job.result.title;
  if (job.source.kind === 'pdf') {
    return job.source.files[0]?.name.replace(/\.pdf$/i, '') || 'Документ PDF';
  }
  const n = job.source.files.length;
  return `Снимки · ${n} ${pl(n, 'страница', 'страницы', 'страниц')}`;
}

/** Прогресс оцифровки: страниц готово из всего и доля 0–1 для полосы. */
export function jobProgress(job: OmrJob): { text: string; fraction: number } {
  if (job.status === 'queued') return { text: 'В очереди на распознавание', fraction: 0 };
  const total = job.progress?.pageCount || job.pages.length;
  const done = job.pages.filter((p) => p.status === 'done').length;
  const fraction = job.status === 'done' ? 1 : (job.progress?.percent ?? 0) / 100;
  if (!total) return { text: 'Готовим страницы', fraction };
  return {
    text: `Распознано ${done} из ${total} ${pl(total, 'страницы', 'страниц', 'страниц')}`,
    fraction: Math.max(fraction, done / total),
  };
}

/** Подпись под размером на странице произведения. */
export function meterSubtitle(piece: Piece): string | null {
  const change = piece.timeSignatureChanges[0];
  if (change) return `${change.timeSignature} в такте ${change.number}`;
  if (piece.timeSignatureSource === 'user') return 'указан при загрузке';
  if (piece.timeSignatureSource === 'inferred') return 'определён автоматически';
  return null;
}
