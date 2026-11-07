# Как запускать проект

## Каждый раз

### 1. Мобильное приложение
Открой PowerShell (Win + R → `powershell`) и выполни:

```powershell
cd D:\Projects\piano-trainer
pnpm dev:mobile
```

Дождись строки `Waiting on http://localhost:8081` и QR-кода.

На iPhone открой **Expo Go** → в разделе **Development servers** нажми `piano-trainer`.
Если его там нет, отсканируй QR-код камерой или выбери «Enter URL manually» → `exp://<IP компьютера>:8081`.

- Телефон и компьютер должны быть в одной Wi-Fi сети.
- После правок кода приложение обновится само. Если что-то зависло, нажми `r` в терминале.
- Остановить сервер: `Ctrl + C`.

### 2. API (если нужен)
Во втором окне PowerShell:

```powershell
cd D:\Projects\piano-trainer
pnpm dev:api
```

Проверка: открой http://localhost:3000/v1/health в браузере, должен прийти ответ `{"status":"ok",...}`.

### 3. Распознавание нот (OMR) через Swagger

Docker не нужен: задачи хранятся в SQLite, файлы — в `.data/omr/` в корне репозитория (ARCHITECTURE §7.1.1).

Нужно два окна PowerShell:

```powershell
# окно 1 — API
cd D:\Projects\piano-trainer
pnpm dev:api

# окно 2 — воркер распознавания (homr)
cd D:\Projects\piano-trainer
pnpm dev:omr-worker
```

Воркер ждёт строку «Жду задачи (homr 0.7.0)». Если API ещё не запущен, воркер пишет «Таблицы omr_jobs ещё нет» и ждёт.

**Удобнее всего проверять на тестовой странице.** В третьем окне запусти `pnpm dev:omr-ui` и открой http://localhost:3100: слева загрузка файлов, статус и подозрительные такты, справа распознанные ноты и оригинал.

Или через Swagger, http://localhost:3000/docs:

1. **POST /v1/omr/jobs** → Try it out → в `files` выбери один PDF или до 10 фото (кнопка «Add string item» добавляет ещё файл) → Execute. Скопируй `id` из ответа.
2. **GET /v1/omr/jobs/{id}** — статус и прогресс: `queued` → `processing` (в `progress` видно страницу и процент) → `done` / `failed` / `cancelled`. Страница распознаётся примерно 25–50 с.
3. **GET /v1/omr/jobs/{id}/result.musicxml** — в ответе появится ссылка «Download file». Файл открывается в MuseScore.
4. **GET /v1/omr/jobs/{id}/report.json** — какие такты подозрительны и почему; **GET …/pages/{page}** — картинка страницы, которую получил движок.
5. **POST /v1/omr/jobs/{id}/cancel** — отмена.

Если нормальных тактов меньше 40 %, задача получает `failed` с `error.code = low_quality`, но MusicXML всё равно скачивается. Порог меняется переменной `OMR_MIN_OK_RATIO`.

Прогресс вживую (SSE) удобнее смотреть не в Swagger, а в PowerShell:

```powershell
curl.exe -N http://localhost:3000/v1/omr/jobs/<id>/events
```

Без API распознать файл одной командой:

```powershell
cd D:\Projects\piano-trainer\services\omr-worker
uv run omr-worker recognize "C:\путь\к\нотам.pdf" --out omr-out
```

homr живёт в отдельном окружении `services/omr-worker/bench/envs/homr` (его создаёт бенчмарк); другой путь задаётся переменной `OMR_HOMR_EXE`. Если `uv` не в PATH, `pnpm dev:omr-worker` ищет его сам.

### 4. Проверить, что ничего не сломалось
```powershell
pnpm typecheck
pnpm test
```

## Если что-то пошло не так

| Проблема | Что делать |
|---|---|
| Expo Go: «not signed in to Expo CLI» | Нет или устарел токен в `C:\Users\User\.expo-token` (см. ниже) |
| `Port 8081 is being used` | Сервер уже запущен в другом окне: закрой его или нажми `Y`, чтобы взять другой порт |
| Телефон не подключается | Одна ли Wi-Fi сеть? Брандмауэр Windows: разрешить Node.js для частных сетей. Крайний вариант: `pnpm dev:mobile --tunnel` |
| Ошибки после `git pull` | `pnpm install` |
| `pnpm` не найден | `npm i -g pnpm` |
| Задача OMR висит в `queued` | Не запущен воркер (`pnpm dev:omr-worker`) |
| Задача OMR `failed` с `interrupted` | Воркер перезапускали во время распознавания — загрузи файл ещё раз |
| Воркер: «Не найден homr» | Нет `services/omr-worker/bench/envs/homr` — укажи путь к `homr.exe` в `OMR_HOMR_EXE` |

## Вход в Expo (токен)

`npx expo login` на этой машине падает (баг Expo CLI на Windows при открытии браузера), поэтому CLI логинится **токеном**:

1. https://expo.dev/settings/access-tokens → **Create token** (аккаунт `mankaaaaa`).
2. В PowerShell:
   ```powershell
   Set-Content -Path "$HOME\.expo-token" -Value "ТОКЕН" -NoNewline
   ```
3. `pnpm dev:mobile` сам подхватит токен из этого файла (`scripts/start-mobile.mjs`).

Проверить вход:

```powershell
cd D:\Projects\piano-trainer\apps\mobile
$env:EXPO_TOKEN = Get-Content "$HOME\.expo-token"; npx expo whoami
```

Токен — это доступ к аккаунту Expo: не коммить его и никому не отправляй.

## С фазы 1 (нативный MIDI-модуль)

Expo Go перестанет подходить: понадобится своя dev-сборка приложения через EAS. Инструкцию добавим сюда, когда дойдём до этого шага.
