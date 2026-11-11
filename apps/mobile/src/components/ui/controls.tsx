import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { useEffect } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { PlayIcon } from '@/components/icons';
import type { CardStatus } from '@/features/library/queries';
import { colors, fonts, shadows } from '@/theme/tokens';

/** Нажатие с лёгким уменьшением, как :active в макете. */
export function Press({
  style,
  scale = 0.97,
  ...props
}: PressableProps & { style?: StyleProp<ViewStyle>; scale?: number }) {
  return (
    <Pressable {...props} style={({ pressed }) => [style, pressed && { transform: [{ scale }] }]} />
  );
}

/** Play на сфере — белое стекло. Нотная визуализация ещё не сделана, поэтому ничего не делает. */
export function PlayButton({ size = 44, label }: { size?: number; label: string }) {
  return (
    <Press
      accessibilityRole="button"
      accessibilityLabel={label}
      scale={0.9}
      onPress={() => {}}
      style={[styles.play, { width: size, height: size, borderRadius: size / 2 }]}
    >
      <BlurView intensity={28} tint="light" style={StyleSheet.absoluteFill} />
      <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(255,255,255,0.3)' }]} />
      <PlayIcon size={size > 50 ? 24 : 16} />
    </Press>
  );
}

const TAG_LABELS: Record<Exclude<CardStatus, null>, string> = {
  new: 'Новое',
  digitizing: 'Оцифровка',
  failed: 'Ошибка',
};

/** Тег статуса: «Новое» — светло-синий, «Оцифровка» — сплошной синий с пульсом, «Ошибка» — красный. */
export function Tag({ status }: { status: Exclude<CardStatus, null> }) {
  const label = TAG_LABELS[status];
  if (status === 'digitizing') {
    return (
      <View style={[styles.tag, styles.tagDigitizing]}>
        <LinearGradient
          colors={[colors.blue, colors.blueSoft]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={[StyleSheet.absoluteFill, { borderRadius: 999 }]}
        />
        <PulseDot />
        <Text style={[styles.tagText, { color: '#fff' }]}>{label}</Text>
      </View>
    );
  }
  const isNew = status === 'new';
  return (
    <View
      style={[
        styles.tag,
        isNew
          ? { backgroundColor: 'rgba(47,107,255,0.1)', borderColor: 'rgba(47,107,255,0.28)' }
          : { backgroundColor: 'rgba(229,57,76,0.1)', borderColor: 'rgba(229,57,76,0.3)' },
      ]}
    >
      <Text style={[styles.tagText, { color: isNew ? colors.blueInk : colors.redInk }]}>
        {label}
      </Text>
    </View>
  );
}

function PulseDot() {
  const opacity = useSharedValue(1);
  useEffect(() => {
    opacity.value = withRepeat(withTiming(0.45, { duration: 700 }), -1, true);
  }, [opacity]);
  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <Animated.View style={[styles.dot, style]} />;
}

/** Бейдж «! 2» — такты с ошибками распознавания. */
export function ErrorBadge({ count, label }: { count: number; label: string }) {
  return (
    <View style={styles.err} accessibilityLabel={label}>
      <View style={styles.bang}>
        <Text style={styles.bangText}>!</Text>
      </View>
      <Text style={styles.errText}>{count}</Text>
    </View>
  );
}

export function ProgressBar({ fraction }: { fraction: number }) {
  const pct = `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%` as const;
  return (
    <View style={styles.bar}>
      <View style={[styles.fill, { width: pct }]}>
        <LinearGradient
          colors={[colors.blue, colors.sky]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={StyleSheet.absoluteFill}
        />
      </View>
    </View>
  );
}

/** Круглая кнопка 44 из белого стекла: назад, «Ещё», закрыть. */
export function IconButton({
  label,
  onPress,
  children,
}: {
  label: string;
  onPress?: () => void;
  children: React.ReactNode;
}) {
  return (
    <Press
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={6}
      scale={0.92}
      style={styles.iconBtn}
    >
      {children}
    </Press>
  );
}

/** Чип выбора: выбранный — чёрная пилюля. */
export function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Press
      accessibilityRole="button"
      accessibilityState={{ selected: on }}
      onPress={onPress}
      style={[styles.chip, on && styles.chipOn]}
    >
      <Text style={[styles.chipText, on && { color: '#fff' }]}>{label}</Text>
    </Press>
  );
}

/** Главная кнопка действия: чёрная пилюля («Изменить», «Сохранить»). */
export function InkButton({
  label,
  icon,
  onPress,
  disabled,
  tone = 'ink',
  style,
}: {
  label: string;
  icon?: React.ReactNode;
  onPress: () => void;
  disabled?: boolean;
  tone?: 'ink' | 'red' | 'plain';
  style?: ViewStyle;
}) {
  const bg = tone === 'ink' ? colors.ink : tone === 'red' ? colors.red : 'rgba(255,255,255,0.8)';
  const fg = tone === 'plain' ? colors.ink2 : '#fff';
  return (
    <Press
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.inkBtn,
        { backgroundColor: bg, opacity: disabled ? 0.5 : 1 },
        tone === 'plain' ? styles.plainBtn : shadows.ink,
        style,
      ]}
    >
      {icon}
      <Text style={[styles.inkText, { color: fg }]}>{label}</Text>
    </Press>
  );
}

const styles = StyleSheet.create({
  play: {
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.75)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#141E3C',
    shadowOpacity: 0.18,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 6 },
  },
  tag: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    height: 22,
    paddingHorizontal: 9,
    borderRadius: 999,
    borderWidth: 1,
  },
  tagDigitizing: {
    borderColor: colors.blue,
    shadowColor: colors.blue,
    shadowOpacity: 0.3,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 4 },
  },
  tagText: { fontFamily: fonts.bold, fontSize: 11, letterSpacing: 0.2 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#fff' },
  err: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 22,
    paddingLeft: 4,
    paddingRight: 8,
    borderRadius: 999,
    backgroundColor: 'rgba(229,57,76,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(229,57,76,0.25)',
  },
  bang: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.red,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bangText: { color: '#fff', fontFamily: fonts.extrabold, fontSize: 10, lineHeight: 12 },
  errText: { color: colors.redInk, fontFamily: fonts.bold, fontSize: 12 },
  bar: {
    height: 6,
    borderRadius: 999,
    backgroundColor: 'rgba(15,25,50,0.08)',
    overflow: 'hidden',
  },
  fill: { height: '100%', minWidth: 6, borderRadius: 999, overflow: 'hidden' },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: '#fff',
    backgroundColor: 'rgba(255,255,255,0.65)',
    alignItems: 'center',
    justifyContent: 'center',
    ...shadows.card,
  },
  chip: {
    height: 40,
    minWidth: 52,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(15,25,50,0.1)',
    backgroundColor: 'rgba(255,255,255,0.8)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipOn: { backgroundColor: colors.ink, borderColor: colors.ink, ...shadows.ink },
  chipText: { fontFamily: fonts.bold, fontSize: 14, color: colors.ink2 },
  inkBtn: {
    height: 44,
    paddingHorizontal: 16,
    borderRadius: 999,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  plainBtn: { borderWidth: 1, borderColor: 'rgba(15,25,50,0.1)' },
  inkText: { fontFamily: fonts.bold, fontSize: 13 },
});
