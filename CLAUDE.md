# piano-trainer

Мобильное приложение для разучивания произведений на пианино: пользователь загружает ноты (MusicXML или PDF/фото → OMR), учит их фрагментами по N тактов с проверкой игры через MIDI, а интервальные повторения, мини-уроки и стрик не дают выученному забыться.

- Идея и фичи: `docs/IDEA.md`
- Архитектура и ключевые решения: `docs/ARCHITECTURE.md`
- План по фазам с критериями готовности: `docs/ROADMAP.md`. После работы над фазой обновляй в нём статусы.

## Структура

pnpm-монорепо + Turborepo. Пакеты `@piano/*`.

- `apps/mobile` — Expo (SDK 58) + expo-router, iOS + Android, только dev client. Свои правила в `apps/mobile/AGENTS.md`: Expo-API сверять с документацией нужной версии SDK, нативные пакеты ставить через `npx expo install`, не трогать `ios/`/`android/` (CNG).
- `apps/api` — NestJS 12 + Fastify, ESM (импорты с суффиксом `.js`), Vitest. В MVP только `health` и `omr`.
- `packages/score-core` — модель партитуры (`PracticeScore`), MusicXML/MXL/MEI, фрагменты, проверка тактов.
- `packages/practice-engine` — матчер нот (режимы `wait`/`tempo`), оценка попыток, статусы фрагментов, повторения, уроки, стрики.
- `packages/notation-view` — бандл WebView с Verovio + протокол моста `protocol.ts`.
- `packages/contracts` — zod-схемы API, общие для api и mobile.
- `services/omr-worker` — Python 3.12 (uv), распознавание нот, очередь BullMQ `omr`.
- `infra/docker-compose.yml` — Postgres, Redis, MinIO.

## Правила

- `score-core` и `practice-engine` — чистый TS: никаких импортов React, RN или Node. Вся музыкальная логика живёт там и покрывается тестами Vitest на фикстурах.
- Сопоставление нот считается по нативным меткам времени MIDI на шкале аудио-часов, а не по времени прихода события в JS.
- WebView нотного стана только рисует и подсвечивает; решения принимает `practice-engine`.
- Offline-first: данные пользователя хранятся в SQLite на устройстве. Сущности имеют UUIDv7, `updatedAt`, `deletedAt`, попытки — append-only.
- Внутренние пакеты подключаются из исходников (`exports` → `src/index.ts`), без шага сборки.
- `nodeLinker: hoisted` в `pnpm-workspace.yaml` нужен для Metro, не меняй его.
- UI-тексты и документация на русском, идентификаторы в коде на английском.
- Коммиты по [Conventional Commits](https://www.conventionalcommits.org/ru/v1.0.0/): `<type>(<scope>): <описание>`. Тип и scope на английском (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`; scope — имя приложения или пакета без `@piano/`: `mobile`, `api`, `score-core`, `omr-worker`, `roadmap` и т. п.), описание на русском, в повелительном наклонении, без точки в конце. Ломающие изменения помечаются `!` после типа или scope.
- Автор коммитов задан в локальном конфиге репозитория (`git config user.name/user.email`), глобальный конфиг для этого проекта не используется.

## Команды

```bash
pnpm install
pnpm typecheck && pnpm test     # все пакеты через turbo
pnpm dev:mobile                 # Expo dev-сервер, берёт EXPO_TOKEN из ~/.expo-token
pnpm dev:api                    # API на :3000, префикс /v1
pnpm infra:up                   # Postgres/Redis/MinIO (нужен Docker)
cd services/omr-worker && uv sync && uv run pytest
```

Пошаговый запуск и типичные проблемы — `docs/RUNNING.md`. `npx expo login` на этой машине падает, поэтому Expo CLI авторизуется токеном из `~/.expo-token`.
