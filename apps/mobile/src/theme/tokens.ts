/**
 * Светлая тема из макета (docs/DESIGN.md, холст «Piano Trainer — Библиотека», LightDesignSystem).
 * Интерфейс почти бесцветный: цвет приходит от сфер-обложек.
 */
export const colors = {
  bg: '#EEF1F7',
  surface: '#FFFFFF',
  ink: '#0B1220',
  ink2: '#4A5570',
  ink3: '#5F6984',
  blue: '#2F6BFF',
  blueSoft: '#4C8DFF',
  blueInk: '#1D4FCC',
  sky: '#7CC4FF',
  red: '#E5394C',
  redInk: '#B81F33',
  redDeep: '#A81B2E',
  /** Свечения фона. */
  glowBlue: '#A9C8FF',
  glowViolet: '#DCCFFF',
  glowSky: '#BFEBFF',
  /** Холодная тень, никогда не чёрная. */
  shadow: '#1E3264',
  hairline: 'rgba(15,25,50,0.08)',
} as const;

export const radius = {
  card: 28,
  art: 20,
  tile: 22,
  sheet: 38,
  pill: 999,
} as const;

/** Поля экрана — 16, сетка — 4. */
export const space = {
  gutter: 16,
} as const;

export const fonts = {
  medium: 'Manrope_500Medium',
  semibold: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  extrabold: 'Manrope_800ExtraBold',
} as const;

export const type = {
  screenTitle: { fontFamily: fonts.extrabold, fontSize: 38, lineHeight: 40, letterSpacing: -1.1 },
  pageTitle: { fontFamily: fonts.extrabold, fontSize: 26, lineHeight: 30, letterSpacing: -0.5 },
  section: { fontFamily: fonts.extrabold, fontSize: 18, letterSpacing: -0.2 },
  cardTitle: { fontFamily: fonts.bold, fontSize: 16, lineHeight: 20, letterSpacing: -0.16 },
  body: { fontFamily: fonts.semibold, fontSize: 14, lineHeight: 20 },
  secondary: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 18 },
  small: { fontFamily: fonts.semibold, fontSize: 12, lineHeight: 16 },
  eyebrow: {
    fontFamily: fonts.bold,
    fontSize: 12,
    letterSpacing: 1.44,
    textTransform: 'uppercase',
  },
} as const;

/** Тени RN: холодные синие 8–16 %. */
export const shadows = {
  card: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.08,
    shadowRadius: 15,
    shadowOffset: { width: 0, height: 10 },
    elevation: 3,
  },
  dock: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.16,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 14 },
    elevation: 6,
  },
  ink: {
    shadowColor: colors.ink,
    shadowOpacity: 0.25,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
} as const;
