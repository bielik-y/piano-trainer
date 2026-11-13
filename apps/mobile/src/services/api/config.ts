import Constants from 'expo-constants';

/** Хост компьютера с dev-сервером Expo: «192.168.1.10:8081», «exp://192.168.1.10:8081» → «192.168.1.10». */
function devServerHost(): string | null {
  const candidates = [
    Constants.expoConfig?.hostUri,
    Constants.expoGoConfig?.debuggerHost,
    Constants.linkingUri,
    Constants.experienceUrl,
  ];
  for (const value of candidates) {
    const host = value?.replace(/^[a-z]+:\/\//i, '').split(/[:/]/)[0];
    if (host) return host;
  }
  return null;
}

/**
 * Адрес API. EXPO_PUBLIC_API_URL — явно (например, http://192.168.1.10:3000/v1); иначе берём хост
 * dev-сервера Expo: телефон в Expo Go уже видит компьютер по этому адресу, API слушает 0.0.0.0:3000.
 */
export function apiBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/+$/, '');
  return `http://${devServerHost() ?? 'localhost'}:3000/v1`;
}

if (__DEV__) console.log(`[api] base ${apiBaseUrl()}`);
