import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Background } from '@/components/ui/glass';
import { colors, type } from '@/theme/tokens';

/** Временная заглушка экрана: что здесь будет и в какой фазе ROADMAP. */
export function PlaceholderScreen({
  title,
  phase,
  children,
}: {
  title: string;
  phase: string;
  children?: string;
}) {
  return (
    <View style={styles.container}>
      <Background />
      <SafeAreaView style={styles.safeArea}>
        <Text style={[type.pageTitle, { color: colors.ink }]}>{title}</Text>
        {children ? <Text style={[type.body, { color: colors.ink }]}>{children}</Text> : null}
        <Text style={[type.small, { color: colors.ink2 }]}>{phase}</Text>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: 24, gap: 16 },
});
