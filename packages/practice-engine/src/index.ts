/**
 * practice-engine: сопоставление сыгранного с партитурой, оценка попыток,
 * статусы фрагментов, интервальное повторение, мини-уроки и стрики.
 * Чистый TS, тестируется без устройства. См. docs/ARCHITECTURE.md §5–6.
 */
import type { Hands, MeasureRange, PracticeScore } from '@piano/score-core';

// --- Ввод ---

/** Событие с MIDI-клавиатуры (или экранной клавиатуры в dev). */
export interface NoteEvent {
  type: 'on' | 'off';
  midi: number;
  velocity: number;
  /** Время в мс на шкале сессии (аудио-часы, задержка уже вычтена). */
  t: number;
}

// --- Сопоставление ---

export type PracticeMode = 'wait' | 'tempo';

export type MatchKind = 'correct' | 'early' | 'late' | 'wrong' | 'missed';

export interface MatchResult {
  kind: MatchKind;
  /** xml:id ожидаемой ноты; для 'wrong' отсутствует. */
  noteId?: string;
  playedMidi?: number;
  /** Отклонение от ожидаемого времени, мс (только режим tempo). */
  deltaMs?: number;
}

export interface MatcherConfig {
  score: PracticeScore;
  range: MeasureRange;
  hands: Hands;
  mode: PracticeMode;
  /** Для режима tempo. */
  bpm?: number;
  /** 0.5–1.0 */
  tempoPct?: number;
  /** Время первой доли фрагмента на шкале сессии, мс (режим tempo). */
  startT?: number;
}

export interface Matcher {
  feed(event: NoteEvent): MatchResult[];
  /** Продвинуть часы: в режиме tempo помечает ноты, окно которых истекло, как 'missed'. */
  tick(now: number): MatchResult[];
  /** xml:id нот, которые ждём следующими (для курсора). */
  expectedNext(): string[];
  isComplete(): boolean;
  summary(): AttemptSummary;
}

export interface AttemptSummary {
  /** 0–1: доля верно сыгранных ожидаемых нот. */
  noteAccuracy: number;
  /** 0–1: доля нот в окне «хорошо»; null в режиме wait. */
  rhythmAccuracy: number | null;
  missed: number;
  extra: number;
  durationMs: number;
}

// --- Прогресс ---

export type FragmentStatus = 'not_started' | 'learning' | 'learned' | 'needs_review';

export interface MasteryCriterion {
  consecutivePasses: number;
  minNoteAccuracy: number;
  minTempoPct: number;
  mode: PracticeMode;
}

export const DEFAULT_MASTERY: MasteryCriterion = {
  consecutivePasses: 3,
  minNoteAccuracy: 0.95,
  minTempoPct: 1,
  mode: 'tempo',
};

export interface ReviewState {
  dueAt: Date;
  intervalDays: number;
  ease: number;
  lapses: number;
}

/** Алгоритм интервального повторения (MVP: упрощённый SM-2, позже — FSRS). */
export interface Scheduler {
  initial(now: Date): ReviewState;
  next(state: ReviewState, passed: boolean, now: Date): ReviewState;
}

// --- Уроки ---

export type LessonStepKind = 'review' | 'weak' | 'new';

export interface LessonStep {
  kind: LessonStepKind;
  fragmentId: string;
  hands: Hands;
  mode: PracticeMode;
  tempoPct: number;
}

export interface LessonPlan {
  /** Локальная дата YYYY-MM-DD — по ней считается стрик. */
  date: string;
  steps: LessonStep[];
  estimatedMinutes: number;
}
