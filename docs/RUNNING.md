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

### 3. Проверить, что ничего не сломалось
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
