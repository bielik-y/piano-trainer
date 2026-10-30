import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';

/** Временная заглушка экрана: что здесь будет и в какой фазе ROADMAP. */
export function PlaceholderScreen({ title, phase, children }: { title: string; phase: string; children?: string }) {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedText type="subtitle">{title}</ThemedText>
        {children ? <ThemedText>{children}</ThemedText> : null}
        <ThemedText type="small" themeColor="textSecondary">
          {phase}
        </ThemedText>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: Spacing.four, gap: Spacing.three },
});
