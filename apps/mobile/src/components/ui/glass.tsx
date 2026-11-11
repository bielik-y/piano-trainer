import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

import { colors, shadows } from '@/theme/tokens';

type GlassProps = {
  radius: number;
  /** Прозрачность белого сверху и снизу: карточка 0.82→0.5, таб-бар 0.7→0.42, шторка 0.88→0.94. */
  from?: number;
  to?: number;
  blur?: number;
  shadow?: keyof typeof shadows | null;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
};

/** Белое стекло светлой темы: размытие, белый градиент, белая обводка, холодная тень. */
export function Glass({
  radius,
  from = 0.82,
  to = 0.5,
  blur = 24,
  shadow = 'card',
  style,
  contentStyle,
  children,
}: GlassProps) {
  return (
    <View style={[{ borderRadius: radius }, shadow && shadows[shadow], style]}>
      <View style={[styles.clip, { borderRadius: radius }]}>
        <BlurView intensity={blur * 2} tint="light" style={StyleSheet.absoluteFill} />
        <LinearGradient
          colors={[`rgba(255,255,255,${from})`, `rgba(255,255,255,${to})`]}
          start={{ x: 0.2, y: 0 }}
          end={{ x: 0.8, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
        <View style={contentStyle}>{children}</View>
      </View>
    </View>
  );
}

/** Фон экрана: холодный светлый + три размытых свечения (голубое, сиреневое, небесное). */
export function Background({ tint }: { tint?: string }) {
  return (
    <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.bg }]} pointerEvents="none">
      <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
        <Defs>
          <Glow id="g1" color={tint ?? colors.glowBlue} opacity={tint ? 0.45 : 0.95} />
          <Glow id="g2" color={colors.glowViolet} opacity={0.8} />
          <Glow id="g3" color={colors.glowSky} opacity={0.9} />
        </Defs>
        <Circle cx="15%" cy="0%" r="300" fill="url(#g1)" />
        <Circle cx="100%" cy="48%" r="230" fill="url(#g2)" />
        <Circle cx="30%" cy="100%" r="280" fill="url(#g3)" />
      </Svg>
    </View>
  );
}

function Glow({ id, color, opacity }: { id: string; color: string; opacity: number }) {
  return (
    <RadialGradient id={id} cx="0.5" cy="0.5" r="0.5">
      <Stop offset="0" stopColor={color} stopOpacity={opacity} />
      <Stop offset="0.68" stopColor={color} stopOpacity={0} />
    </RadialGradient>
  );
}

const styles = StyleSheet.create({
  clip: {
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.95)',
  },
});
