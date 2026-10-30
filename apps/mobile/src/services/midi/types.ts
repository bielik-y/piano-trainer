import type { NoteEvent } from '@piano/practice-engine';

export interface MidiDevice {
  id: string;
  name: string;
  transport: 'usb' | 'ble' | 'virtual';
}

/**
 * Источник нот для практики. Реализации:
 * - нативный модуль modules/expo-midi (фаза 1),
 * - экранная клавиатура для dev-сборки (фаза 4).
 */
export interface NoteInput {
  listDevices(): Promise<MidiDevice[]>;
  connect(deviceId: string): Promise<void>;
  disconnect(): Promise<void>;
  /** Возвращает функцию отписки. */
  subscribe(listener: (event: NoteEvent) => void): () => void;
}
