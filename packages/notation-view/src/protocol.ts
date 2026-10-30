/**
 * Протокол моста React Native ⇄ WebView (Verovio).
 * Импортируется обеими сторонами: apps/mobile (services/notation) и этим бандлом.
 * См. docs/ARCHITECTURE.md §6.5.
 */
import type { Staff } from '@piano/score-core';

export type HighlightState = 'correct' | 'wrong' | 'missed' | 'cursor';

/** RN → WebView */
export type HostToViewMessage =
  | { type: 'load'; musicXml: string }
  | { type: 'showRange'; fromMeasure: number; toMeasure: number; staves: Staff[] }
  | { type: 'showAll'; staves: Staff[] }
  | { type: 'highlight'; ids: string[]; state: HighlightState }
  | { type: 'clearHighlights' }
  | { type: 'setTheme'; theme: 'light' | 'dark' };

/** WebView → RN */
export type ViewToHostMessage =
  | { type: 'ready'; verovioVersion: string }
  | { type: 'loaded'; measureCount: number; pageCount: number }
  | { type: 'rendered'; fromMeasure: number; toMeasure: number }
  | { type: 'error'; message: string };
