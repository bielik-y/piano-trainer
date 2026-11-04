"""Предобработка: исходники задачи → PNG по страницам.

- PDF растеризуется PyMuPDF (300 dpi по умолчанию, как в бенчмарке).
- Фото поворачивается по EXIF и сохраняется в PNG; HEIC с iPhone читается через pillow-heif.

Качество картинки пока не улучшаем (ARCHITECTURE §7.4). Пустые нотоносцы убирает empty_staves.py.
"""

from pathlib import Path

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .models import OmrFailure

register_heif_opener()

PDF_MAGIC = b"%PDF"


def is_pdf(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(4) == PDF_MAGIC


def pdf_page_count(path: Path) -> int:
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count
    except (pymupdf.FileDataError, RuntimeError) as e:
        raise OmrFailure("unreadable_file", f"Не удалось открыть PDF: {e}") from e


def rasterize_pdf(path: Path, out_dir: Path, dpi: int, max_pages: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileDataError, RuntimeError) as e:
        raise OmrFailure("unreadable_file", f"Не удалось открыть PDF: {e}") from e
    with doc:
        if doc.page_count == 0:
            raise OmrFailure("unreadable_file", "В PDF нет страниц")
        if doc.page_count > max_pages:
            raise OmrFailure(
                "too_many_pages", f"В PDF {doc.page_count} страниц, можно не больше {max_pages}"
            )
        pages = []
        for number, page in enumerate(doc, start=1):
            target = out_dir / f"{number}.png"
            page.get_pixmap(dpi=dpi).save(target)
            pages.append(target)
        return pages


def normalize_image(path: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(target, format="PNG")
    except (UnidentifiedImageError, OSError) as e:
        raise OmrFailure("unreadable_file", f"Не удалось открыть картинку {path.name}: {e}") from e
    return target


def prepare_pages(sources: list[Path], out_dir: Path, dpi: int, max_pages: int) -> list[Path]:
    """Один PDF или несколько картинок (в порядке страниц) → `out_dir/1.png`, `2.png`…"""
    if not sources:
        raise OmrFailure("unreadable_file", "Нет файлов")
    if len(sources) == 1 and is_pdf(sources[0]):
        return rasterize_pdf(sources[0], out_dir, dpi, max_pages)
    if any(is_pdf(s) for s in sources):
        raise OmrFailure("unreadable_file", "PDF нельзя смешивать с другими файлами")
    return [normalize_image(s, out_dir / f"{n}.png") for n, s in enumerate(sources, start=1)]


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size
