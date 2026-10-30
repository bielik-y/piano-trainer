# expo-midi

Локальный Expo-модуль для приёма MIDI (USB + BLE) на iOS и Android. Создаётся в фазе 1:

```bash
cd apps/mobile
npx create-expo-module@latest --local   # имя: expo-midi
```

Требования (docs/ARCHITECTURE.md §6):

- iOS: CoreMIDI, `MIDITimeStamp` → наносекунды; BLE-сопряжение через `CABTMIDICentralViewController`.
- Android: `android.media.midi.MidiManager`, USB и `openBluetoothDevice`; разрешения `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT`.
- События в JS: `onNoteOn`, `onNoteOff`, `onControlChange` (педаль CC64), `onDevicesChanged`;
  у каждого есть нативная метка времени.
- JS-обёртка реализует интерфейс `NoteInput` из `src/services/midi/types.ts`.
