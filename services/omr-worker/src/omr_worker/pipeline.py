"""Конвейер распознавания одной задачи (ARCHITECTURE §7.1).

исходники → страницы PNG → homr по страницам → склейка → проверка тактов → result.musicxml + report.json

Раскладка папки задачи:
    source/      исходные файлы (кладёт API)
    pages/N.png  страницы после предобработки
    work/        рабочие файлы движка
    result.musicxml, report.json
"""

import json
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import music21 as m21

from .empty_staves import remove_empty_systems
from .engines.cli import EngineCancelled, EngineError, EngineNoMusic, EngineTimeout
from .measures import check_measures, infer_time_signature, measures_from_score, parse_score
from .merge import merge_pages, page_of_measure, set_score_info, set_time_signature
from .metadata import ScoreInfo, read_score_info
from .models import (
    Cancelled,
    EngineInfo,
    OmrFailure,
    PageInfo,
    Progress,
    Report,
    SuspiciousMeasure,
)
from .preprocess import image_size, is_pdf, prepare_pages

log = logging.getLogger(__name__)

# Доли общего прогресса по этапам, в процентах.
PREPROCESS_END = 5
RECOGNIZE_END = 90
MERGE_END = 95
# Оценка времени на страницу до первой распознанной (по бенчмарку ~30–50 с).
DEFAULT_PAGE_SECONDS = 40


class PageEngine(Protocol):
    name: str

    def version(self) -> str | None: ...

    def recognize_page(
        self, image: Path, out_dir: Path, should_stop: Callable[[], bool] | None = None
    ) -> Path: ...


class Listener(Protocol):
    def on_progress(self, progress: Progress, pages: list[PageInfo]) -> None: ...

    def should_stop(self) -> bool: ...


class _Silent:
    def on_progress(self, progress: Progress, pages: list[PageInfo]) -> None:
        pass

    def should_stop(self) -> bool:
        return False


@dataclass(frozen=True)
class PipelineOutput:
    report: Report
    pages: list[PageInfo]
    music_xml: Path
    report_path: Path


def run_pipeline(
    sources: list[Path],
    job_dir: Path,
    engine: PageEngine,
    *,
    min_ok_ratio: float,
    dpi: int = 300,
    max_pdf_pages: int = 20,
    listener: Listener | None = None,
) -> PipelineOutput:
    """Распознаёт задачу. Бросает OmrFailure (задача failed) или Cancelled.

    Низкое качество — не исключение: report.quality == "low", решение принимает вызывающий."""
    listener = listener or _Silent()

    def check_stop() -> None:
        if listener.should_stop():
            raise Cancelled()

    # 1. Предобработка
    listener.on_progress(Progress(stage="preprocessing", page_count=0, percent=0), [])
    pages_dir = job_dir / "pages"
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    images = prepare_pages(sources, pages_dir, dpi, max_pdf_pages)
    pages: list[PageInfo] = []
    blank_pages: set[int] = set()
    for index, image in enumerate(images, start=1):
        width, height = image_size(image)
        pages.append(PageInfo(index=index, width=width, height=height))
        cleaned = remove_empty_systems(image)
        if cleaned.removed:
            log.info("Страница %d: убрано пустых систем: %d", index, cleaned.removed)
            if cleaned.blank:
                blank_pages.add(index)
    total = len(pages)
    check_stop()

    # 2. Распознавание по страницам
    work = job_dir / "work"
    documents: list[str | None] = []
    spent: list[float] = []
    for page, image in zip(pages, images):
        if page.index in blank_pages:
            page.status, page.seconds = "done", 0.0
            documents.append(None)
            spent.append(0.0)
            continue
        page.status = "processing"
        remaining = total - len(spent)
        average = sum(spent) / len(spent) if spent else DEFAULT_PAGE_SECONDS
        listener.on_progress(
            Progress(
                stage="recognizing",
                page=page.index,
                page_count=total,
                percent=_percent(PREPROCESS_END, RECOGNIZE_END, len(spent), total),
                eta_seconds=round(average * remaining) + 5,
            ),
            pages,
        )
        started = time.monotonic()
        try:
            output = engine.recognize_page(image, work, should_stop=listener.should_stop)
            documents.append(_read_text(output))
            page.status = "done"
        except EngineCancelled:
            page.status = "pending"
            raise Cancelled() from None
        except EngineNoMusic:
            page.status = "done"
            documents.append(None)
        except EngineTimeout as e:
            page.status, page.error = "failed", f"Таймаут распознавания: {e}"
            documents.append(None)
        except EngineError as e:
            page.status, page.error = "failed", f"Движок не распознал страницу: {e}"
            documents.append(None)
        page.seconds = round(time.monotonic() - started, 1)
        spent.append(page.seconds)

    recognized = [doc for doc in documents if doc is not None]
    if not recognized:
        if not any(p.status == "failed" for p in pages):
            raise OmrFailure("no_music_found", "На страницах не найдено нот")
        code = "timeout" if all("Таймаут" in (p.error or "") for p in pages) else "engine_failed"
        raise OmrFailure(code, "Не удалось распознать ни одной страницы")
    check_stop()

    # 3. Склейка
    listener.on_progress(
        Progress(stage="merging", page_count=total, percent=RECOGNIZE_END), pages
    )
    try:
        merged = merge_pages(recognized)
    except Exception as e:
        raise OmrFailure("engine_failed", f"Движок вернул некорректный MusicXML: {e}") from e
    # Страницы без результата дают 0 тактов: так номера страниц в отчёте остаются верными.
    per_page: list[int] = []
    counts = iter(merged.measures_per_page)
    for page, doc in zip(pages, documents):
        page.measure_count = next(counts) if doc is not None else 0
        per_page.append(page.measure_count)

    # 4. Проверка тактов
    listener.on_progress(
        Progress(stage="validating", page_count=total, percent=MERGE_END), pages
    )
    try:
        score = parse_score(merged.music_xml)
    except Exception as e:
        raise OmrFailure("engine_failed", f"Не удалось разобрать результат: {e}") from e
    measures = measures_from_score(score)
    if not measures or not any(m.has_events for m in measures):
        raise OmrFailure("no_music_found", "На страницах не найдено нот")
    info = _read_info(sources, images, documents)
    music_xml_text = set_score_info(merged.music_xml, info)
    time_signature_source = "engine" if _first_time_signature(score) else None
    if time_signature_source is None:
        inferred = infer_time_signature(measures)
        if inferred is not None:
            music_xml_text = set_time_signature(music_xml_text, *inferred)
            score = parse_score(music_xml_text)
            measures = measures_from_score(score)
            time_signature_source = "inferred"
    issues = check_measures(measures)
    ok_count = len(measures) - len(issues)
    ok_ratio = round(ok_count / len(measures), 4)

    report = Report(
        measure_count=len(measures),
        ok_measure_count=ok_count,
        ok_ratio=ok_ratio,
        min_ok_ratio=min_ok_ratio,
        quality="ok" if ok_ratio >= min_ok_ratio else "low",
        staff_count=len(score.parts),
        time_signature=_first_time_signature(score),
        time_signature_source=time_signature_source,
        key_fifths=_first_key(score),
        title=info.title,
        composer=info.composer,
        tempo_text=info.tempo_text,
        tempo_bpm=info.tempo_bpm,
        suspicious_measures=[
            SuspiciousMeasure(
                index=index,
                number=measures[index].number or str(index + 1),
                page=page_of_measure(per_page, index),
                reasons=reasons,
            )
            for index, reasons in sorted(issues.items())
        ],
        engine=EngineInfo(name=engine.name, version=engine.version()),
    )

    music_xml = job_dir / "result.musicxml"
    music_xml.write_text(music_xml_text, encoding="utf-8")
    report_path = job_dir / "report.json"
    report_path.write_text(
        json.dumps(
            {**report.dump(), "pages": [p.dump() for p in pages]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return PipelineOutput(report=report, pages=pages, music_xml=music_xml, report_path=report_path)


def _read_info(
    sources: list[Path], images: list[Path], documents: list[str | None]
) -> ScoreInfo:
    """Сбой чтения названия и темпа не должен ронять задачу: без них ноты всё равно есть."""
    index = next(i for i, doc in enumerate(documents) if doc is not None)
    pdf = sources[0] if len(sources) == 1 and is_pdf(sources[0]) else None
    try:
        return read_score_info(images[index], pdf, index)
    except Exception:
        log.warning("Не удалось прочитать название и темп", exc_info=True)
        return ScoreInfo()


def _percent(start: int, end: int, done: int, total: int) -> int:
    return start + round((end - start) * done / total) if total else start


def _read_text(path: Path) -> str:
    if path.suffix == ".mxl":
        from .engines.cli import _read_music_xml

        return _read_music_xml(path)
    return path.read_text(encoding="utf-8")


def _first_time_signature(score: m21.stream.Score) -> str | None:
    found = next(iter(score.recurse().getElementsByClass(m21.meter.TimeSignature)), None)
    return found.ratioString if found is not None else None


def _first_key(score: m21.stream.Score) -> int | None:
    found = next(iter(score.recurse().getElementsByClass(m21.key.KeySignature)), None)
    return found.sharps if found is not None else None
