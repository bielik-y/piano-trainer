import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/theme/tokens';

const EASE = Easing.bezier(0.2, 0.9, 0.2, 1);
const HIDDEN = 900;

type Props = { open: boolean; onClose: () => void; label: string; children: React.ReactNode };

/**
 * Шторка поверх экрана, как в макете: скрим с размытием, белое стекло с радиусом 38,
 * въезжает снизу; закрывается тапом по скриму, свайпом вниз или из кода (open = false).
 */
export function Sheet({ open, onClose, label, children }: Props) {
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(open);
  const y = useSharedValue(HIDDEN);
  const scrim = useSharedValue(0);

  if (open && !mounted) setMounted(true);

  useEffect(() => {
    if (!mounted) return;
    if (open) {
      y.value = withTiming(0, { duration: 550, easing: EASE });
      scrim.value = withTiming(1, { duration: 400 });
    } else {
      scrim.value = withTiming(0, { duration: 350 });
      y.value = withTiming(HIDDEN, { duration: 450, easing: EASE }, (done) => {
        if (done) runOnJS(setMounted)(false);
      });
    }
  }, [open, mounted, y, scrim]);

  const pan = Gesture.Pan()
    .activeOffsetY(8)
    .onUpdate((e) => {
      y.value = Math.max(0, e.translationY);
    })
    .onEnd((e) => {
      if (e.translationY > 120 || e.velocityY > 800) runOnJS(onClose)();
      else y.value = withTiming(0, { duration: 300, easing: EASE });
    });

  const sheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));
  const scrimStyle = useAnimatedStyle(() => ({ opacity: scrim.value }));

  if (!mounted) return null;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={open ? 'auto' : 'none'}>
      <Animated.View style={[StyleSheet.absoluteFill, scrimStyle]}>
        <Pressable
          accessibilityLabel="Закрыть"
          onPress={onClose}
          style={[StyleSheet.absoluteFill, styles.scrim]}
        >
          <BlurView intensity={12} tint="light" style={StyleSheet.absoluteFill} />
        </Pressable>
      </Animated.View>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.anchor}
        pointerEvents="box-none"
      >
        <GestureDetector gesture={pan}>
          <Animated.View
            accessibilityViewIsModal
            accessibilityLabel={label}
            style={[styles.sheet, { marginBottom: Math.max(insets.bottom - 26, 8) }, sheetStyle]}
          >
            <BlurView intensity={80} tint="light" style={StyleSheet.absoluteFill} />
            <LinearGradient
              colors={['rgba(255,255,255,0.88)', 'rgba(244,246,251,0.94)']}
              style={StyleSheet.absoluteFill}
            />
            <View style={styles.handle} />
            {children}
          </Animated.View>
        </GestureDetector>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: 'rgba(20,30,60,0.2)' },
  anchor: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    marginHorizontal: 8,
    borderRadius: 38,
    overflow: 'hidden',
    paddingTop: 10,
    paddingHorizontal: 16,
    paddingBottom: 22,
    borderWidth: 1,
    borderColor: '#fff',
    shadowColor: colors.shadow,
    shadowOpacity: 0.2,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: -20 },
  },
  handle: {
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: 'rgba(15,25,50,0.16)',
    alignSelf: 'center',
    marginBottom: 16,
  },
});
