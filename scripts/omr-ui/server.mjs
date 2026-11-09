// Страница для ручной проверки распознавания: http://localhost:3100
// Отдаёт index.html и Verovio, запросы /v1/* передаёт в API. Только для разработки.
// API пускает только с токеном устройства: прокси регистрирует своё устройство и подставляет
// токен сам (картинкам страниц <img src> заголовок не передать). Токен лежит в .data/omr-ui-token.
import { createReadStream, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, request } from 'node:http';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.OMR_UI_PORT ?? 3100);
const API_PORT = Number(process.env.PORT ?? 3000);

const FILES = {
  '/': ['./index.html', 'text/html; charset=utf-8'],
  '/verovio.js': ['../../node_modules/verovio/dist/verovio-toolkit-wasm.js', 'text/javascript'],
};

const TOKEN_FILE = fileURLToPath(new URL('../../.data/omr-ui-token', import.meta.url));
let token = null;

async function deviceToken() {
  if (token) return token;
  try {
    token = readFileSync(TOKEN_FILE, 'utf8').trim() || null;
  } catch {}
  if (token) return token;
  const response = await fetch(`http://127.0.0.1:${API_PORT}/v1/devices`, { method: 'POST' });
  if (!response.ok) throw new Error(`POST /v1/devices: ${response.status}`);
  token = (await response.json()).token;
  mkdirSync(dirname(TOKEN_FILE), { recursive: true });
  writeFileSync(TOKEN_FILE, token);
  return token;
}

/** Токен больше не действует (например, удалили базу): при следующем запросе получим новый. */
function forgetToken() {
  token = null;
  rmSync(TOKEN_FILE, { force: true });
}

async function proxy(req, res) {
  let auth;
  try {
    auth = `Bearer ${await deviceToken()}`;
  } catch {
    res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ message: `API не отвечает на порту ${API_PORT}: запусти pnpm dev:api` }));
    return;
  }
  const upstream = request(
    {
      host: '127.0.0.1',
      port: API_PORT,
      method: req.method,
      path: req.url,
      headers: { ...req.headers, host: `localhost:${API_PORT}`, authorization: auth },
    },
    (answer) => {
      if (answer.statusCode === 401) forgetToken();
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    },
  );
  upstream.on('error', () => {
    if (res.headersSent) return res.destroy();
    res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ message: `API не отвечает на порту ${API_PORT}: запусти pnpm dev:api` }));
  });
  req.pipe(upstream);
}

const server = createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  if (path.startsWith('/v1/')) return void proxy(req, res);
  const file = FILES[path];
  if (!file) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { 'content-type': file[1] });
  createReadStream(fileURLToPath(new URL(file[0], import.meta.url))).pipe(res);
});

server.listen(PORT, '127.0.0.1', () => console.log(`Проверка OMR: http://localhost:${PORT}`));
