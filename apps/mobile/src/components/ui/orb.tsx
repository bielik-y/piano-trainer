import { useId } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';
import Svg, { Defs, LinearGradient, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

import { orbColors } from '@/theme/orb';

/**
 * Контур сферы — скруглённый прямоугольник с разными радиусами углов, как
 * border-radius: 42% 58% 63% 37% / 41% 44% 56% 59% в макете.
 */
function blobPath(x: number, y: number, w: number, h: number): string {
  const [tlx, trx, brx, blx] = [0.42 * w, 0.58 * w, 0.63 * w, 0.37 * w];
  const [tly, try_, bry, bly] = [0.41 * h, 0.44 * h, 0.56 * h, 0.59 * h];
  return [
    `M ${x + tlx} ${y}`,
    `L ${x + w - trx} ${y}`,
    `A ${trx} ${try_} 0 0 1 ${x + w} ${y + try_}`,
    `L ${x + w} ${y + h - bry}`,
    `A ${brx} ${bry} 0 0 1 ${x + w - brx} ${y + h}`,
    `L ${x + blx} ${y + h}`,
    `A ${blx} ${bly} 0 0 1 ${x} ${y + h - bly}`,
    `L ${x} ${y + tly}`,
    `A ${tlx} ${tly} 0 0 1 ${x + tlx} ${y}`,
    'Z',
  ].join(' ');
}

type Props = {
  hue: number;
  size: number;
  /** Ошибка распознавания — серая сфера. */
  muted?: boolean;
  /** Светлая подложка с радиусом 20, как у обложки в карточке. */
  plate?: boolean;
  style?: ViewStyle;
  children?: React.ReactNode;
};

/** Сфера-обложка произведения: градиенты по оттенку hue (пока без анимации). */
export function Orb({ hue, size, muted = false, plate = false, style, children }: Props) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, '');
  const c = orbColors(hue, muted);
  const blob = size * (plate ? 0.64 : 0.66);
  const offset = (size - blob) / 2;
  const d = blobPath(offset, offset, blob, blob);
  const haloOpacity = muted ? 0.15 : 0.6;

  return (
    <View style={[{ width: size, height: size }, plate && styles.plate, style]}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Defs>
          <LinearGradient id={`p${id}`} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#F8F9FC" />
            <Stop offset="1" stopColor="#ECEFF5" />
          </LinearGradient>
          <RadialGradient id={`h${id}`} cx="0.5" cy="0.5" r="0.5">
            <Stop offset="0" stopColor={c.halo} stopOpacity={haloOpacity} />
            <Stop offset="0.7" stopColor={c.halo} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id={`c${id}`} cx="0.45" cy="0.5" r="0.75">
            <Stop offset="0" stopColor={c.core} />
            <Stop offset="1" stopColor={c.rim} />
          </RadialGradient>
          <RadialGradient id={`s${id}`} cx="0.76" cy="0.74" r="0.7">
            <Stop offset="0" stopColor={c.spot} stopOpacity={1} />
            <Stop offset="0.64" stopColor={c.spot} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id={`l${id}`} cx="0.3" cy="0.26" r="0.55">
            <Stop offset="0" stopColor={c.highlight} stopOpacity={1} />
            <Stop offset="0.62" stopColor={c.highlight} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        {plate ? <Rect width={size} height={size} rx={20} fill={`url(#p${id})`} /> : null}
        <Rect width={size} height={size} fill={`url(#h${id})`} />
        <Path d={d} fill={`url(#c${id})`} />
        <Path d={d} fill={`url(#s${id})`} />
        <Path d={d} fill={`url(#l${id})`} />
      </Svg>
      <View style={styles.center}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  plate: { borderRadius: 20, overflow: 'hidden' },
  center: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
});
