/** Цвета сферы-обложки по оттенку произведения (docs/DESIGN.md, «Сферы-обложки»). */

export function hsl(h: number, s: number, l: number): string {
  const hue = ((Math.round(h) % 360) + 360) % 360;
  return `hsl(${hue}, ${s}%, ${l}%)`;
}

export type OrbColors = {
  /** Блик сверху слева: h+25 · 94 %. */
  highlight: string;
  /** Пятно снизу справа: h+70 · 62 %. */
  spot: string;
  /** Ядро: h · 58 % → h−50 · 38 %. */
  core: string;
  rim: string;
  /** Свечение со сдвигом h−70. */
  halo: string;
};

export function orbColors(hue: number, muted = false): OrbColors {
  if (muted) {
    return {
      highlight: hsl(0, 0, 96),
      spot: hsl(0, 0, 78),
      core: hsl(0, 0, 66),
      rim: hsl(0, 0, 44),
      halo: hsl(0, 0, 80),
    };
  }
  return {
    highlight: hsl(hue + 25, 100, 94),
    spot: hsl(hue + 70, 95, 62),
    core: hsl(hue, 92, 58),
    rim: hsl(hue - 50, 80, 38),
    halo: hsl(hue - 70, 100, 72),
  };
}
