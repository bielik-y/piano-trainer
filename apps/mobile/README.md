# @piano/mobile

Expo-приложение (iOS + Android). Нужен **development build**, Expo Go не подойдёт: модуль MIDI нативный.

```bash
pnpm --filter @piano/mobile start     # dev-сервер
pnpm --filter @piano/mobile ios       # локальная сборка (нужен macOS)
pnpm --filter @piano/mobile android
```

Нативные зависимости добавляются только через `npx expo install <pkg>` (см. AGENTS.md).
