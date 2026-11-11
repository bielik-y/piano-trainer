import {
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/manrope';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { DefaultTheme, SplashScreen, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { ToastProvider } from '@/components/ui/toast';
import { colors } from '@/theme/tokens';

void SplashScreen.preventAutoHideAsync();

const DAY = 24 * 60 * 60 * 1000;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { gcTime: 7 * DAY, staleTime: 30 * 1000, retry: 1 },
  },
});

/** Кэш библиотеки на диске: после перезапуска список виден сразу, потом обновляется с сервера. */
const persister = createAsyncStoragePersister({ storage: AsyncStorage, key: 'library-cache' });

const theme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: colors.bg, text: colors.ink, primary: colors.blue },
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
  });
  const ready = fontsLoaded || fontError !== null;

  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={{ persister, maxAge: 7 * DAY, buster: 'v1' }}
      >
        <ThemeProvider value={theme}>
          <ToastProvider>
            <StatusBar style="dark" />
            <Stack
              screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}
            >
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="piece/[id]/index" />
              <Stack.Screen
                name="piece/[id]/practice"
                options={{ headerShown: true, title: 'Практика' }}
              />
              <Stack.Screen
                name="import/index"
                options={{ headerShown: true, title: 'Добавить ноты', presentation: 'modal' }}
              />
              <Stack.Screen
                name="import/review/[jobId]"
                options={{ headerShown: true, title: 'Результат распознавания' }}
              />
              <Stack.Screen name="lesson" options={{ headerShown: true, title: 'Урок дня' }} />
            </Stack>
          </ToastProvider>
        </ThemeProvider>
      </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}
