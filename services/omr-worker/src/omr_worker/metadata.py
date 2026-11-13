"""Название, автор и темп с первой страницы нот.

Текст берётся из текстового слоя PDF; распознавание (RapidOCR) нужно для картинок и для PDF, где
часть шапки вставлена картинкой. Что есть что, определяется по положению на странице:
- название — самая высокая строка по центру над первым нотоносцем;
- автор — строка «Music by …» или строка у правого края, иначе строка по центру под названием;
- темп словами — строка слева над нотоносцем, темп числом — «= 120» в первой системе.

Движок нот этого не умеет: homr читает только одну строку и часто берёт её не оттуда.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from .empty_staves import first_system_bounds

log = logging.getLogger(__name__)

# Если нотоносцы не нашлись (фото с наклоном), шапкой считается эта верхняя доля страницы.
FALLBACK_HEADER = 0.35
# Доля страницы ниже первой системы, которую тоже читаем: темп бывает напечатан рядом с ней.
SYSTEM_MARGIN = 0.02
MIN_OCR_SCORE = 0.5
MIN_BPM, MAX_BPM = 30, 300

COMPOSER_PREFIX = re.compile(
    r"^(?:(?:words and )?music by|composed by|composer:?|written by|by)\s+(.+)$", re.IGNORECASE
)
NOT_COMPOSER = re.compile(r"\b(?:arr|arrang\w*|lyrics?|transcri\w*|from|for|op|no)\b", re.IGNORECASE)
NOT_TEMPO = re.compile(r"^(?:piano|pianoforte|voice|vocals?|cresc\w*|dim\w*|legato)\.?$", re.IGNORECASE)
# Текст темпа должен содержать слово из словаря или английское наречие на -ly («Tenderly»):
# иначе это мусор OCR («DJS») или подпись.
TEMPO_WORDS = re.compile(
    r"\b(?:"
    r"grave|largo|larghetto|lento|adagio\w*|andant\w*|moderato|allegr\w*|vivace|vivo|presto|"
    r"prestissimo|tempo|rubato|maestoso|cantabile|dolce|grazioso|animato|agitato|sostenuto|"
    r"tranquillo|espressivo|giocoso|scherzando|marcato|assai|molto|poco|non\s+troppo|"
    r"slow\w*|moderate\w*|medium|fast|quick\w*|bright\w*|easy|steady|gentl\w*|freely|lively|"
    r"relaxed|walking|swing\w*|shuffle|rock|ballad|waltz|march|groove|latin|bossa|samba|"
    r"reggae|funk\w*|blues|pop|feel|straight|half[- ]time|"
    r"langsam|mäßig|massig|schnell|ruhig|lebhaft|bewegt|lent|modéré|vif|"
    r"медленно|умеренно|быстро|спокойно|оживл\w*"
    r"|[a-z]{3,}ly"
    r")\b",
    re.IGNORECASE,
)
CHORD = re.compile(r"^[A-G][b#]?(?:maj|min|m|dim|aug|sus|add)?\d*$")
BPM_AFTER_EQUALS = re.compile(r"=\s*(\d{2,3})\b")
# OCR настроен на китайский и латиницу: ноты он порой читает как иероглифы.
CJK = re.compile(r"[\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]")


@dataclass(frozen=True)
class TextLine:
    """Строка текста; координаты — доли ширины и высоты страницы."""

    text: str
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class ScoreInfo:
    title: str | None = None
    composer: str | None = None
    tempo_text: str | None = None
    tempo_bpm: int | None = None


def read_score_info(image: Path, pdf: Path | None = None, page_index: int = 0) -> ScoreInfo:
    """Читает первую страницу с нотами: `image` — её картинка, `pdf` — исходник, если это PDF."""
    bounds = first_system_bounds(image)
    limit = min(1.0, bounds[1] + SYSTEM_MARGIN) if bounds else FALLBACK_HEADER
    staff_top = bounds[0] if bounds else None
    lines = _lines_from_pdf(pdf, page_index, limit) if pdf is not None else []
    info = classify_lines(lines, staff_top)
    if _is_complete(info):
        return info
    return classify_lines(_merge_lines(lines, _lines_from_ocr(image, limit)), staff_top)


def _is_complete(info: ScoreInfo) -> bool:
    return bool(info.title and info.composer and (info.tempo_text or info.tempo_bpm))


def _merge_lines(exact: list[TextLine], recognized: list[TextLine]) -> list[TextLine]:
    """Строки текстового слоя точнее распознанных: распознанная добавляется, только если
    на её месте ничего нет."""
    return exact + [
        line
        for line in recognized
        if not any(line.y0 < other.y1 and other.y0 < line.y1 for other in exact)
    ]


def classify_lines(lines: list[TextLine], staff_top: float | None) -> ScoreInfo:
    """Раскладывает строки по ролям. `staff_top` — верх первого нотоносца, None — не найден."""
    header_limit = staff_top if staff_top is not None else FALLBACK_HEADER
    header = [line for line in lines if line.y0 < header_limit and _has_words(line.text)]

    title_line = _find_title(header)
    rest = [line for line in header if line is not title_line]
    composer_line, composer = _find_composer(rest, title_line)
    rest = [line for line in rest if line is not composer_line]
    return ScoreInfo(
        title=title_line.text if title_line else None,
        composer=composer,
        tempo_text=_find_tempo_text(rest),
        tempo_bpm=_find_bpm(lines),
    )


def _has_words(text: str) -> bool:
    return sum(ch.isalpha() for ch in text) >= 3


def _find_title(header: list[TextLine]) -> TextLine | None:
    centered = [
        line
        for line in header
        if abs(line.center - 0.5) < 0.15 and not COMPOSER_PREFIX.match(line.text)
    ]
    return max(centered, key=lambda line: line.height, default=None)


def _find_composer(
    lines: list[TextLine], title: TextLine | None
) -> tuple[TextLine | None, str | None]:
    for line in lines:
        match = COMPOSER_PREFIX.match(line.text)
        if match and not NOT_COMPOSER.search(match.group(1)):
            return line, match.group(1).strip()

    candidates = [line for line in lines if _looks_like_name(line.text)]
    right = [line for line in candidates if line.x0 > 0.5 and line.x1 > 0.8]
    if right:
        return right[0], right[0].text
    if title is not None:
        below = [
            line for line in candidates if abs(line.center - 0.5) < 0.15 and line.y0 >= title.y0
        ]
        if below:
            return below[0], below[0].text
    return None, None


def _looks_like_name(text: str) -> bool:
    words = text.split()
    return (
        2 <= len(words) <= 5
        and not NOT_COMPOSER.search(text)
        and not any(ch.isdigit() for ch in text)
        and all(word[0].isupper() for word in words)
    )


def _find_tempo_text(lines: list[TextLine]) -> str | None:
    for line in sorted(lines, key=lambda item: item.y0):
        text = line.text.strip().rstrip(".")
        if (
            line.x0 < 0.35
            and line.x1 < 0.5
            and not any(ch.isdigit() for ch in text)
            and not CHORD.match(text)
            and not NOT_TEMPO.match(text)
            and TEMPO_WORDS.search(text)
        ):
            return text
    return None


def _find_bpm(lines: list[TextLine]) -> int | None:
    for line in lines:
        match = BPM_AFTER_EQUALS.search(line.text)
        if match and MIN_BPM <= int(match.group(1)) <= MAX_BPM:
            return int(match.group(1))
    # Число без «=» не считается: это бывают номера тактов, аппликатура и неверно прочитанные ноты.
    return None


def _lines_from_pdf(pdf: Path, page_index: int, limit: float) -> list[TextLine]:
    with pymupdf.open(pdf) as doc:
        page = doc[page_index]
        width, height = page.rect.width, page.rect.height
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = " ".join(
                    span["text"].strip() for span in line["spans"] if span["text"].strip()
                )
                x0, y0, x1, y1 = line["bbox"]
                if text and y0 / height < limit:
                    lines.append(TextLine(text, x0 / width, x1 / width, y0 / height, y1 / height))
    return lines


def _lines_from_ocr(image: Path, limit: float) -> list[TextLine]:
    with Image.open(image) as source:
        picture = np.asarray(source.convert("RGB"))
    height, width = picture.shape[:2]
    top = picture[: max(1, int(height * limit))]
    if not (top < 128).any():
        return []
    return [
        TextLine(text, x0 / width, x1 / width, y0 / height, y1 / height)
        for text, x0, x1, y0, y1 in _run_ocr(top)
    ]


_reader = None


def _run_ocr(picture: np.ndarray) -> list[tuple[str, float, float, float, float]]:
    """Строки картинки в пикселях: (текст, x0, x1, y0, y1). Модель загружается один раз."""
    global _reader
    if _reader is None:
        from rapidocr import RapidOCR

        _reader = RapidOCR(params={"Global.log_level": "error"})
    result = _reader(picture)
    if result.txts is None:
        return []
    rows = []
    for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
        if score < MIN_OCR_SCORE or CJK.search(str(text)):
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        rows.append((str(text).strip(), min(xs), max(xs), min(ys), max(ys)))
    return rows
