import Constants from 'expo-constants';

/**
 * Адрес API. EXPO_PUBLIC_API_URL — явно (например, http://192.168.1.10:3000/v1); иначе берём хост
 * dev-сервера Expo: телефон в Expo Go уже видит компьютер по этому адресу, API слушает 0.0.0.0:3000.
 */
export function apiBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/+$/, '');
  const hostUri = Constants.expoConfig?.hostUri ?? '';
  const host = hostUri.split(':')[0] || 'localhost';
  return `http://${host}:3000/v1`;
}
