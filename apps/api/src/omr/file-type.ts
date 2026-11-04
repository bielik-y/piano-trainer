/** Тип загруженного файла по первым байтам: расширению и Content-Type от клиента не доверяем. */
export type SniffedType =
  | { kind: 'pdf'; contentType: 'application/pdf'; ext: 'pdf' }
  | { kind: 'image'; contentType: 'image/jpeg'; ext: 'jpg' }
  | { kind: 'image'; contentType: 'image/png'; ext: 'png' }
  | { kind: 'image'; contentType: 'image/heic'; ext: 'heic' };

const HEIF_BRANDS = new Set(['heic', 'heix', 'heim', 'heis', 'hevc', 'hevx', 'mif1', 'msf1']);

export function sniffFileType(head: Uint8Array): SniffedType | null {
  const ascii = (from: number, to: number) => String.fromCharCode(...head.subarray(from, to));
  if (ascii(0, 4) === '%PDF') return { kind: 'pdf', contentType: 'application/pdf', ext: 'pdf' };
  if (head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff)
    return { kind: 'image', contentType: 'image/jpeg', ext: 'jpg' };
  if (ascii(0, 8) === '\x89PNG\r\n\x1a\n')
    return { kind: 'image', contentType: 'image/png', ext: 'png' };
  if (ascii(4, 8) === 'ftyp' && HEIF_BRANDS.has(ascii(8, 12)))
    return { kind: 'image', contentType: 'image/heic', ext: 'heic' };
  return null;
}
