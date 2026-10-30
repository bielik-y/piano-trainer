"""Готовит эталонные пьесы для бенчмарка OMR из Humdrum (**kern).

Для каждого `bench/data/reference/*.krn`:
- `<name>.musicxml` — эталон («правильный ответ»), конвертация через music21;
- `<name>.pdf` — ноты, отрендеренные Verovio (A4, 300 dpi), это вход для движков;
- `<name>.p<N>.png` — те же страницы картинками (для съёмки экрана телефоном);
- `<name>.pages.json` — какие такты на какой странице PDF, чтобы сверять страницы по отдельности.

SVG растеризуется через resvg: PyMuPDF рисует SVG Verovio пустой страницей.

Запуск: uv run --group bench python bench/prepare_reference.py
"""

import json
import re
import warnings
from pathlib import Path

import music21 as m21
import pymupdf
import resvg_py
import verovio

REFERENCE_DIR = Path(__file__).parent / "data" / "reference"

A4_WIDTH_PX_300DPI = 2480

# A4 в единицах Verovio (1/10 мм) и масштаб, при котором нотоносец ~7 мм, как в типичном издании.
VEROVIO_OPTIONS = {
    "pageWidth": 2100,
    "pageHeight": 2970,
    "pageMarginTop": 100,
    "pageMarginBottom": 100,
    "pageMarginLeft": 120,
    "pageMarginRight": 120,
    "scale": 45,
    "adjustPageHeight": False,
    "breaks": "auto",
    "footer": "none",
}

MEASURE_ID = re.compile(r'<g\s+id="([^"]+)"\s+class="measure')
# Знак common time из `*met(c)` Verovio кладёт в SVG без видимого глифа, и страница выходит
# без размера. Без этой строки Verovio рисует размер цифрами из `*M4/4`.
INVISIBLE_METER = re.compile(r"^\*met\(c\)(\t\*met\(c\)|\t\*)*$")


def to_musicxml(krn: Path, out: Path) -> int:
    """Эталон в MusicXML. Возвращает число тактов в партии правой руки."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        score = m21.converter.parse(str(krn))
    for part in score.parts:
        measures = list(part.getElementsByClass(m21.stream.Measure))
        # music21 добавляет пустой такт после финальной черты в некоторых kern-файлах.
        if measures and not measures[-1].notesAndRests:
            part.remove(measures[-1])
    score.write("musicxml", fp=str(out))
    return len(score.parts[0].getElementsByClass(m21.stream.Measure))


def render_pdf(krn: Path, pdf_out: Path) -> list[dict]:
    """Рендерит PNG-страницы и PDF из них, возвращает карту страниц:
    [{page, firstMeasure, measureCount}]."""
    tk = verovio.toolkit()
    tk.setOptions(VEROVIO_OPTIONS)
    lines = krn.read_text(encoding="utf-8").splitlines()
    tk.loadData("\n".join(line for line in lines if not INVISIBLE_METER.match(line)))
    doc = pymupdf.open()
    pages = []
    first = 0
    for page_no in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(page_no)
        count = len(MEASURE_ID.findall(svg))
        pages.append({"page": page_no, "firstMeasure": first, "measureCount": count})
        first += count
        png = bytes(
            resvg_py.svg_to_bytes(svg_string=svg, width=A4_WIDTH_PX_300DPI, background="#ffffff")
        )
        krn.with_suffix(f".p{page_no}.png").write_bytes(png)
        page = doc.new_page(width=pymupdf.paper_size("a4")[0], height=pymupdf.paper_size("a4")[1])
        page.insert_image(page.rect, stream=png)
    doc.save(pdf_out)
    return pages


def main() -> None:
    for krn in sorted(REFERENCE_DIR.glob("*.krn")):
        for stale in REFERENCE_DIR.glob(f"{krn.stem}.p*.png"):
            stale.unlink()
        xml_measures = to_musicxml(krn, krn.with_suffix(".musicxml"))
        pages = render_pdf(krn, krn.with_suffix(".pdf"))
        pdf_measures = sum(p["measureCount"] for p in pages)
        krn.with_suffix(".pages.json").write_text(json.dumps(pages, indent=2), encoding="utf-8")
        status = "ok" if xml_measures == pdf_measures else "РАСХОЖДЕНИЕ"
        print(
            f"{krn.stem}: страниц {len(pages)}, тактов в PDF {pdf_measures}, "
            f"в MusicXML {xml_measures} — {status}"
        )


if __name__ == "__main__":
    main()
