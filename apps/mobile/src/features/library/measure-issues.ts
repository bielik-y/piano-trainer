import type { Piece, SuspiciousMeasure } from '@piano/contracts';

import { pl } from './text';

/** Ошибка распознавания такта словами: «Длительности не совпадают с размером» / «В такте 11 восьмых вместо 12». */
export type MeasureIssueText = { measure: string; title: string; detail: string };

/** Размер, действующий в такте index, с учётом смен посреди пьесы. */
function meterAt(piece: Piece, index: number): string | null {
  let meter = piece.timeSignature;
  for (const change of piece.timeSignatureChanges) {
    if (change.index <= index) meter = change.timeSignature;
  }
  return meter;
}

const FRACTIONS: Record<string, string> = { '0.25': '¼', '0.5': '½', '0.75': '¾' };

/** 4.5 → «4½», 11 → «11», 2.33 → «2,33». */
function formatCount(n: number): string {
  const whole = Math.floor(n);
  const rest = Math.round((n - whole) * 100) / 100;
  if (rest === 0) return String(whole);
  const frac = FRACTIONS[String(rest)];
  if (frac) return whole ? `${whole}${frac}` : frac;
  return String(Math.round(n * 100) / 100).replace('.', ',');
}

/**
 * Длину в четвертях переводим в единицы размера: в x/8 — восьмые, в x/2 — половинные,
 * иначе — доли-четверти. Дробное число читается с родительным падежом единственного числа.
 */
const denominatorOf = (meter: string | null) => Number(meter?.split('/')[1]) || 4;

/** Сколько единиц размера в длине: 6 четвертей в 12/8 — 12 восьмых. */
const unitsOf = (quarters: number, meter: string | null) => (quarters * denominatorOf(meter)) / 4;

function inUnits(quarters: number, meter: string | null): string {
  const denominator = denominatorOf(meter);
  const n = unitsOf(quarters, meter);
  const forms: [string, string, string] =
    denominator === 8
      ? ['восьмая', 'восьмых', 'восьмых']
      : denominator === 2
        ? ['половинная', 'половинных', 'половинных']
        : ['доля', 'доли', 'долей'];
  const word = Number.isInteger(n) ? pl(n, ...forms) : forms[1];
  return `${formatCount(n)} ${word}`;
}

function staffPart(staff: number | null): { title: string; detail: string } {
  if (staff === 2) {
    return { title: 'Такта нет на нижнем нотоносце', detail: 'Партия левой руки не распознана' };
  }
  if (staff === 1) {
    return { title: 'Такта нет на верхнем нотоносце', detail: 'Партия правой руки не распознана' };
  }
  return { title: 'Такта нет на одном из нотоносцев', detail: 'Часть партии не распознана' };
}

export function measureIssueText(piece: Piece, m: SuspiciousMeasure): MeasureIssueText {
  const meter = meterAt(piece, m.index);
  const sized = m.length !== null && m.expectedLength !== null;
  const base = { measure: m.number };

  if (m.reasons.includes('missing_on_staff')) return { ...base, ...staffPart(m.staff) };
  if (m.reasons.includes('overflow')) {
    return {
      ...base,
      title: 'Ноты выходят за конец такта',
      detail: sized
        ? `Сумма длительностей ${inUnits(m.length!, meter)} из ${formatCount(unitsOf(m.expectedLength!, meter))}`
        : 'Последние ноты не помещаются в размер',
    };
  }
  if (m.reasons.includes('duration_mismatch')) {
    return {
      ...base,
      title: 'Длительности не совпадают с размером',
      detail: sized
        ? `В такте ${inUnits(m.length!, meter)} вместо ${formatCount(unitsOf(m.expectedLength!, meter))}`
        : 'Сумма длительностей не сходится с размером',
    };
  }
  if (m.reasons.includes('empty')) {
    return { ...base, title: 'Пустой такт', detail: 'В такте не распознано ни одной ноты' };
  }
  return {
    ...base,
    title: 'Размер не определён',
    detail: 'Укажите размер в дополнительных настройках при загрузке',
  };
}
