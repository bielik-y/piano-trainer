import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useColorScheme } from 'react-native';

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="piece/[id]/index" options={{ title: 'Произведение' }} />
        <Stack.Screen name="piece/[id]/practice" options={{ title: 'Практика' }} />
        <Stack.Screen name="import/index" options={{ title: 'Добавить ноты', presentation: 'modal' }} />
        <Stack.Screen name="import/review/[jobId]" options={{ title: 'Результат распознавания' }} />
        <Stack.Screen name="lesson" options={{ title: 'Урок дня' }} />
      </Stack>
    </ThemeProvider>
  );
}
