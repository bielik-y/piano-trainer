import { ApiError, type ApiErrorCode, DeviceRegistration } from '@piano/contracts';
import * as SecureStore from 'expo-secure-store';

import { apiBaseUrl } from './config';

/** Схема контракта: zod-схема из @piano/contracts или что угодно с parse. */
type Schema<T> = { parse(value: unknown): T };

const TOKEN_KEY = 'device-token';

/** Ошибка запроса к API: code из контракта или network — сервер недоступен. */
export class RequestError extends Error {
  constructor(
    readonly code: ApiErrorCode | 'network' | 'unknown',
    message: string,
    readonly status = 0,
  ) {
    super(message);
  }
}

let tokenPromise: Promise<string> | null = null;

async function register(): Promise<string> {
  const res = await rawFetch('/devices', { method: 'POST' });
  if (!res.ok) throw await toError(res);
  const { token } = DeviceRegistration.parse(await res.json());
  await SecureStore.setItemAsync(TOKEN_KEY, token);
  return token;
}

/** Токен устройства: из защищённого хранилища или новая анонимная регистрация. */
function deviceToken(): Promise<string> {
  tokenPromise ??= (async () => (await SecureStore.getItemAsync(TOKEN_KEY)) ?? register())();
  tokenPromise.catch(() => {
    tokenPromise = null;
  });
  return tokenPromise;
}

/**
 * multipart-запрос через XMLHttpRequest: fetch в Expo SDK 58 не принимает части формы
 * вида { uri, name, type } («Unsupported FormDataPart implementation»), а XHR React Native
 * читает файл по uri сам.
 */
function xhrForm(url: string, init: RequestInit): Promise<Response> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(init.method ?? 'POST', url);
    for (const [name, value] of Object.entries((init.headers ?? {}) as Record<string, string>)) {
      xhr.setRequestHeader(name, value);
    }
    xhr.onload = () =>
      resolve(
        new Response(xhr.responseText, {
          status: xhr.status,
          headers: { 'Content-Type': xhr.getResponseHeader('Content-Type') ?? 'application/json' },
        }),
      );
    xhr.onerror = () => reject(new Error(`XHR ${xhr.status}`));
    xhr.ontimeout = () => reject(new Error('XHR timeout'));
    xhr.send(init.body as FormData);
  });
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  const url = apiBaseUrl() + path;
  try {
    return await (init.body instanceof FormData ? xhrForm(url, init) : fetch(url, init));
  } catch (e) {
    if (__DEV__) console.warn(`[api] ${init.method ?? 'GET'} ${url}: ${String(e)}`);
    throw new RequestError('network', 'Нет связи с сервером');
  }
}

async function toError(res: Response): Promise<RequestError> {
  try {
    const body = ApiError.parse(await res.json());
    return new RequestError(body.code, body.message, res.status);
  } catch {
    return new RequestError('unknown', `Ошибка сервера (${res.status})`, res.status);
  }
}

async function authorized(path: string, init: RequestInit): Promise<Response> {
  const send = async (token: string) =>
    rawFetch(path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  let res = await send(await deviceToken());
  if (res.status === 401) {
    // Токен не узнали (база сервера сброшена) — регистрируемся заново, один раз.
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    tokenPromise = null;
    res = await send(await deviceToken());
  }
  if (!res.ok) throw await toError(res);
  return res;
}

/** Запрос с JSON-ответом, проверенным схемой контракта. */
export async function apiJson<T>(
  schema: Schema<T>,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await authorized(path, {
    method: init.method ?? 'GET',
    headers: init.body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  return schema.parse(await res.json());
}

/** Запрос без тела ответа (204) или с ответом, который не нужен. */
export async function apiSend(path: string, init: { method: string; body?: unknown }) {
  await authorized(path, {
    method: init.method,
    headers: init.body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

/** multipart/form-data: Content-Type с boundary ставит сам XHR. */
export async function apiForm<T>(schema: Schema<T>, path: string, form: FormData): Promise<T> {
  const res = await authorized(path, { method: 'POST', body: form });
  return schema.parse(await res.json());
}
