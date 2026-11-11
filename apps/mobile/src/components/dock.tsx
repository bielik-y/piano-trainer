import type { BottomTabBarProps } from 'expo-router/tabs';
import { LinearGradient } from 'expo-linear-gradient';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LibraryIcon, PlusIcon, ProfileIcon, TodayIcon } from '@/components/icons';
import { Press } from '@/components/ui/controls';
import { Glass } from '@/components/ui/glass';
import { colors, fonts } from '@/theme/tokens';

const TABS: Record<string, { label: string; Icon: typeof TodayIcon }> = {
  index: { label: 'Сегодня', Icon: TodayIcon },
  library: { label: 'Библиотека', Icon: LibraryIcon },
  profile: { label: 'Профиль', Icon: ProfileIcon },
};

/** Высота дока над нижним краем — чтобы списки оставляли под ним место. */
export const DOCK_SPACE = 150;

/** Плавающий таб-бар: стеклянная пилюля с тремя табами и чёрная кнопка «+» (LightMain). */
export function Dock({ state, navigateToTab, onAdd }: BottomTabBarProps & { onAdd: () => void }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.dock, { bottom: insets.bottom ? insets.bottom - 8 : 16 }]}>
      <Glass radius={999} from={0.7} to={0.42} blur={28} shadow="dock" style={{ flex: 1 }}>
        <View style={styles.tabs}>
          {state.routes.map((route, i) => {
            const tab = TABS[route.name];
            if (!tab) return null;
            const on = state.index === i;
            return (
              <Press
                key={route.key}
                accessibilityRole="tab"
                accessibilityState={{ selected: on }}
                onPress={() => navigateToTab(route.key)}
                style={[styles.tab, on && styles.tabOn]}
              >
                <tab.Icon color={on ? colors.blue : colors.ink3} />
                <Text style={[styles.tabText, { color: on ? colors.ink : colors.ink3 }]}>
                  {tab.label}
                </Text>
              </Press>
            );
          })}
        </View>
      </Glass>
      <AddButton onPress={onAdd} />
    </View>
  );
}

/** Чёрная сфера «+» с пульсирующим синим свечением. */
export function AddButton({ onPress }: { onPress: () => void }) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withRepeat(withTiming(1, { duration: 1800 }), -1, true);
  }, [t]);
  const glow = useAnimatedStyle(() => ({
    shadowOpacity: interpolate(t.value, [0, 1], [0.15, 0.55]),
    shadowRadius: interpolate(t.value, [0, 1], [10, 18]),
  }));
  return (
    <Animated.View style={[styles.fabGlow, glow]}>
      <Press
        accessibilityRole="button"
        accessibilityLabel="Добавить произведение"
        onPress={onPress}
        scale={0.92}
        style={styles.fab}
      >
        <LinearGradient
          colors={['#43557F', colors.ink]}
          locations={[0, 0.62]}
          start={{ x: 0.3, y: 0.2 }}
          end={{ x: 0.75, y: 0.9 }}
          style={StyleSheet.absoluteFill}
        />
        <PlusIcon size={26} color="#fff" />
      </Press>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  dock: {
    position: 'absolute',
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  tabs: { flexDirection: 'row', padding: 6, gap: 2 },
  tab: {
    flex: 1,
    height: 54,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  tabOn: {
    backgroundColor: '#fff',
    shadowColor: colors.shadow,
    shadowOpacity: 0.12,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 4 },
  },
  tabText: { fontFamily: fonts.bold, fontSize: 11 },
  fabGlow: {
    borderRadius: 33,
    shadowColor: colors.blue,
    shadowOffset: { width: 0, height: 0 },
  },
  fab: {
    width: 66,
    height: 66,
    borderRadius: 33,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
