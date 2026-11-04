// Запуск OMR-воркера: `uv run omr-worker serve` в services/omr-worker.
// uv на Windows часто ставится через pip и не попадает в PATH — ищем его в типичных местах.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

function findUv() {
  if (spawnSync('uv', ['--version'], { stdio: 'ignore' }).status === 0) return 'uv';
  const candidates = [join(homedir(), '.local', 'bin', 'uv.exe'), join(homedir(), '.cargo', 'bin', 'uv.exe')];
  const roaming = process.env.APPDATA && join(process.env.APPDATA, 'Python');
  if (roaming && existsSync(roaming)) {
    for (const version of readdirSync(roaming)) candidates.push(join(roaming, version, 'Scripts', 'uv.exe'));
  }
  return candidates.find((p) => existsSync(p));
}

const uv = findUv();
if (!uv) {
  console.error('Не найден uv. Установите: https://docs.astral.sh/uv/ (или pip install uv)');
  process.exit(1);
}

const child = spawn(uv, ['run', 'omr-worker', 'serve', ...process.argv.slice(2)], {
  cwd: join(import.meta.dirname, '..', 'services', 'omr-worker'),
  // Логи на русском: без этого Python на Windows пишет в кодировке консоли (cp1251).
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  stdio: 'inherit',
});
child.on('exit', (code) => process.exit(code ?? 0));
