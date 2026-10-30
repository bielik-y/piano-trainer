// Запуск Expo dev-сервера с токеном из ~/.expo-token.
// Нужен потому, что `npx expo login` на Windows падает (см. docs/RUNNING.md).
import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const tokenFile = join(homedir(), '.expo-token');
const env = { ...process.env };

if (!env.EXPO_TOKEN && existsSync(tokenFile)) {
  env.EXPO_TOKEN = readFileSync(tokenFile, 'utf8').trim();
} else if (!env.EXPO_TOKEN) {
  console.warn(`⚠ Нет ${tokenFile} — Expo Go на iPhone не откроет проект. См. docs/RUNNING.md`);
}

const child = spawn('npx', ['expo', 'start', ...process.argv.slice(2)], {
  cwd: join(import.meta.dirname, '..', 'apps', 'mobile'),
  env,
  stdio: 'inherit',
  shell: true,
});
child.on('exit', (code) => process.exit(code ?? 0));
