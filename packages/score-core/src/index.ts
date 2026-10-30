/**
 * score-core: модель партитуры, не зависящая от платформы.
 * Без React/RN/Node API — только чистый TS. См. docs/ARCHITECTURE.md §5.1.
 */

/** Позиция или длительность в четвертях от начала партитуры (qstamp Verovio). */
export type Quarters = number;

/** 1 — верхний нотоносец (обычно правая рука), 2 — нижний (левая). */
export type Staff = 1 | 2;

export type Hands = 'R' | 'L' | 'RL';

export interface TimeSignature {
  beats: number;
  beatType: number;
}

export interface MeasureInfo {
  /** Порядковый индекс с 0 — по нему режем фрагменты. */
  index: number;
  /** Номер такта из партитуры (может быть затакт «0» или «12a»). */
  number: string;
  timeSig: TimeSignature;
  startQ: Quarters;
  durationQ: Quarters;
}

export interface ScoreNote {
  /** xml:id элемента в MEI — по нему WebView подсвечивает ноту. */
  id: string;
  /** Высота в MIDI (60 = до первой октавы). */
  midi: number;
  staff: Staff;
  measureIndex: number;
  onsetQ: Quarters;
  durationQ: Quarters;
  /** Продолжение лиги: звучит, но заново не нажимается. */
  tieContinuation: boolean;
  grace: boolean;
}

/** Плоский индекс партитуры для движка практики. Строится один раз при импорте. */
export interface PracticeScore {
  measures: MeasureInfo[];
  /** Отсортированы по onsetQ, затем по midi. */
  notes: ScoreNote[];
  tempoBpm: number;
}

export interface MeasureRange {
  /** Включительно, индексы MeasureInfo.index. */
  from: number;
  to: number;
}

export interface MeasureIssue {
  measureIndex: number;
  staff: Staff;
  expectedQ: Quarters;
  actualQ: Quarters;
}

export function staffsForHands(hands: Hands): Staff[] {
  switch (hands) {
    case 'R':
      return [1];
    case 'L':
      return [2];
    case 'RL':
      return [1, 2];
  }
}

// --- Реализуется в фазе 2 (docs/ROADMAP.md) ---

/** Распаковка .mxl (zip) → текст MusicXML. */
export async function unzipMxl(_data: Uint8Array): Promise<string> {
  throw new Error('Not implemented');
}

/** Такты, где сумма длительностей не совпадает с размером (исключаются из оценки, ARCHITECTURE §7.3). */
export function validateMeasures(_score: PracticeScore): MeasureIssue[] {
  throw new Error('Not implemented');
}

/** Ноты диапазона тактов для выбранных рук. */
export function notesInRange(
  _score: PracticeScore,
  _range: MeasureRange,
  _hands: Hands,
): ScoreNote[] {
  throw new Error('Not implemented');
}
