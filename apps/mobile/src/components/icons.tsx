import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { colors } from '@/theme/tokens';

/** Иконки из макета: контур 24×24, цвет — currentColor через color. */
type IconProps = { size?: number; color?: string; strokeWidth?: number };

function Stroke({
  size = 22,
  color = colors.ink,
  strokeWidth = 1.8,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </Svg>
  );
}

export const PlusIcon = (p: IconProps) => (
  <Stroke strokeWidth={2.2} {...p}>
    <Path d="M12 5v14M5 12h14" />
  </Stroke>
);

export const CloseIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M6 6l12 12M18 6L6 18" />
  </Stroke>
);

export const BackIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M15 5l-7 7 7 7" />
  </Stroke>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M9 5l7 7-7 7" />
  </Stroke>
);

export const ChevronDownIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M6 9l6 6 6-6" />
  </Stroke>
);

export const CheckIcon = (p: IconProps) => (
  <Stroke strokeWidth={2.6} {...p}>
    <Path d="M5 12.5l4.5 4.5L19 7.5" />
  </Stroke>
);

export const EditIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M4 20h4L19.5 8.5a2.8 2.8 0 0 0-4-4L4 16z" />
    <Path d="M13.5 6.5l4 4" />
  </Stroke>
);

export const TrashIcon = (p: IconProps) => (
  <Stroke strokeWidth={2} {...p}>
    <Path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
  </Stroke>
);

export const FileIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <Path d="M14 3v5h5" />
    <Path d="M12 17v-6l3 1" />
    <Circle cx={10.5} cy={17} r={1.5} />
  </Stroke>
);

export const CameraIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.6l1.4-2h5l1.4 2h1.6A2.5 2.5 0 0 1 20 8.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5z" />
    <Circle cx={12} cy={12.5} r={3.5} />
  </Stroke>
);

export const GalleryIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Rect x={3.5} y={4.5} width={17} height={15} rx={3} />
    <Circle cx={9} cy={10} r={1.8} />
    <Path d="M20.5 15.5l-4.5-4.5-8.5 8.5" />
  </Stroke>
);

export const TodayIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Path d="M12 3c.6 3 3.4 4.4 3.4 8.2A3.4 3.4 0 0 1 12 14.6a3.4 3.4 0 0 1-3.4-3.4c0-1 .3-1.8.8-2.6C7 10 5.5 12.4 5.5 15a6.5 6.5 0 0 0 13 0C18.5 9.4 13.8 6.2 12 3z" />
  </Stroke>
);

export const LibraryIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Rect x={3.5} y={4} width={4} height={16} rx={1.2} />
    <Rect x={9.5} y={4} width={4} height={16} rx={1.2} />
    <Path d="M16.2 5.2l3.6-.9 3 15.2-3.6.9z" />
  </Stroke>
);

export const ProfileIcon = (p: IconProps) => (
  <Stroke {...p}>
    <Circle cx={12} cy={8.5} r={4} />
    <Path d="M4.5 20.5c1.2-3.6 4.2-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
  </Stroke>
);

export function MoreIcon({ size = 20, color = colors.ink }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
      <Circle cx={5.5} cy={12} r={1.7} />
      <Circle cx={12} cy={12} r={1.7} />
      <Circle cx={18.5} cy={12} r={1.7} />
    </Svg>
  );
}

export function PlayIcon({ size = 16, color = '#fff' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 16 16" style={{ marginLeft: size * 0.18 }}>
      <Path
        d="M4 2.6c0-.8.9-1.3 1.6-.9l8 5.4c.6.4.6 1.4 0 1.8l-8 5.4c-.7.4-1.6-.1-1.6-.9z"
        fill={color}
      />
    </Svg>
  );
}
