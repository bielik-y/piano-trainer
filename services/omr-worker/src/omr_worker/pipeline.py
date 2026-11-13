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
import re
import shutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

import music21 as m21
from PIL import Image

from .accidentals import add_accidentals
from .beams import add_beams
from .empty_staves import remove_empty_systems
from .engines.cli import EngineCancelled, EngineError, EngineNoMusic, EngineTimeout
from .measures import (
    check_measures,
    infer_time_signature,
    issue_details,
    measures_from_score,
    parse_score,
)
from .merge import (
    merge_pages,
    page_of_measure,
    replace_time_signature,
    set_score_info,
    set_time_signature,
)
from .hands import split_hands
from .metadata import ScoreInfo, read_score_info
from .meter import MeterChange, apply_meter_changes
from .models import (
    Cancelled,
    EngineInfo,
    OmrFailure,
    PageInfo,
    Progress,
    Report,
    SuspiciousMeasure,
    TimeSignatureChange,
)
from .preprocess import image_size, is_pdf, prepare_pages
from .rerun import PageSource, map_systems, rerecognize
from .ties import slurs_to_ties
from .timing import close_voice_gaps

log = logging.getLogger(__name__)

# Доли общего прогресса по этапам, в процентах.
PREPROCESS_END = 5
RECOGNIZE_END = 90
MERGE_END = 95
# Оценка времени на страницу до первой распознанной (по бенчмарку ~30–50 с).
DEFAULT_PAGE_SECONDS = 40
# Доля подозрительных тактов страницы, при которой пробуем распознать её повёрнутой на 180°.
UPSIDE_DOWN_SHARE = 0.4


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
    time_signature: tuple[int, int] | None = None,
) -> PipelineOutput:
    """Распознаёт задачу. Бросает OmrFailure (задача failed) или Cancelled.

    time_signature — размер, заданный пользователем: ставится на всю пьесу вместо найденного.
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
    from_pdf = len(sources) == 1 and is_pdf(sources[0])
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
    outputs: list[Path | None] = []
    spent: list[float] = []
    for page, image in zip(pages, images):
        if page.index in blank_pages:
            page.status, page.seconds = "done", 0.0
            documents.append(None)
            outputs.append(None)
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
            text = _read_text(output)
            # Вверх ногами бывают только фото: PDF из нотного редактора всегда стоит ровно.
            flipped = None if from_pdf else _try_upside_down(
                engine, image, text, work, listener, _known_signature(documents), time_signature
            )
            if flipped is not None:
                log.info("Страница %d снята вверх ногами: распознана повёрнутой", page.index)
                output, text = flipped
            documents.append(text)
            outputs.append(output)
            page.status = "done"
        except EngineCancelled:
            page.status = "pending"
            raise Cancelled() from None
        except EngineNoMusic:
            page.status = "done"
            documents.append(None)
            outputs.append(None)
        except EngineTimeout as e:
            page.status, page.error = "failed", f"Таймаут распознавания: {e}"
            documents.append(None)
            outputs.append(None)
        except EngineError as e:
            page.status, page.error = "failed", f"Движок не распознал страницу: {e}"
            documents.append(None)
            outputs.append(None)
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
    raw_xml = set_score_info(merged.music_xml, info)
    finished = _postprocess(raw_xml, time_signature)

    # 5. Повторное распознавание строк, где постобработка не помогла
    rerecognized: list[int] = []
    if finished.issues:
        page_sources = [
            PageSource(image, _positions(output)) for image, output in zip(images, outputs)
        ]
        raw_xml, rerecognized = rerecognize(
            raw_xml,
            set(finished.issues),
            map_systems(raw_xml, per_page),
            page_sources,
            recognize=lambda image: _read_text(
                engine.recognize_page(image, work / "rerun", should_stop=listener.should_stop)
            ),
            evaluate=lambda candidate: set(_postprocess(candidate, time_signature).issues),
            work=work / "rerun",
            should_stop=listener.should_stop,
        )
        if rerecognized:
            finished = _postprocess(raw_xml, time_signature)
    music_xml_text, score, measures, issues = (
        finished.music_xml, finished.score, finished.measures, finished.issues
    )
    time_signature_source = finished.time_signature_source
    details = issue_details(measures, issues)
    ok_count = len(measures) - len(issues)
    ok_ratio = round(ok_count / len(measures), 4)

    report = Report(
        measure_count=len(measures),
        ok_measure_count=ok_count,
        ok_ratio=ok_ratio,
        min_ok_ratio=min_ok_ratio,
        quality="ok" if ok_ratio >= min_ok_ratio else "low",
        staff_count=len(score.parts),
        time_signature=_main_time_signature(score),
        time_signature_source=time_signature_source,
        time_signature_changes=[
            TimeSignatureChange(
                index=index,
                number=measures[index].number or str(index + 1),
                time_signature=f"{beats}/{beat_type}",
            )
            for index, beats, beat_type in finished.meter_changes
            if index < len(measures)
        ],
        key_fifths=_main_key(score),
        title=info.title,
        composer=info.composer,
        tempo_text=info.tempo_text,
        tempo_bpm=info.tempo_bpm,
        rerecognized_measures=[measures[i].number or str(i + 1) for i in rerecognized],
        suspicious_measures=[
            SuspiciousMeasure(
                index=index,
                number=measures[index].number or str(index + 1),
                page=page_of_measure(per_page, index),
                reasons=reasons,
                staff=details[index].staff,
                length=details[index].length,
                expected_length=details[index].expected_length,
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


@dataclass(frozen=True)
class _Finished:
    music_xml: str
    score: m21.stream.Score
    measures: list
    issues: dict[int, list[str]]
    time_signature_source: str | None
    meter_changes: list[MeterChange]


def _postprocess(raw_xml: str, user_time: tuple[int, int] | None = None) -> _Finished:
    """Вся постобработка сырого MusicXML и проверка тактов.

    user_time — размер от пользователя: заменяет найденный движком, а смены размера посреди
    пьесы не ищутся — пользователь сказал, какой размер у пьесы."""
    music_xml_text = raw_xml
    meter_changes: list[MeterChange] = []
    if user_time is not None:
        music_xml_text = replace_time_signature(music_xml_text, *user_time)
        time_signature_source = "user"
    else:
        time_signature_source = "engine" if _has_time_signature(raw_xml) else None
        if time_signature_source is None:
            inferred = infer_time_signature(measures_from_score(parse_score(raw_xml)))
            if inferred is not None:
                music_xml_text = set_time_signature(music_xml_text, *inferred)
                time_signature_source = "inferred"
    # Руки разводятся по длине такта, поэтому после размера, и до поиска смен размера: иначе
    # такт со слитыми руками принимается за 6/4.
    music_xml_text = split_hands(music_xml_text)
    if time_signature_source == "engine":
        corrected = _correct_engine_meter(music_xml_text)
        if corrected is not None:
            music_xml_text = split_hands(corrected)
            time_signature_source = "inferred"
    if user_time is None:
        # Сдвиг нот считается по длине такта, поэтому после размера; знаки — по верному времени.
        music_xml_text, meter_changes = apply_meter_changes(music_xml_text)
    # Залиговки ищутся по верному времени нот; знак на продолжении залиговки не ставится.
    music_xml_text = close_voice_gaps(music_xml_text)
    music_xml_text = add_beams(add_accidentals(slurs_to_ties(music_xml_text)))
    score = parse_score(music_xml_text)
    measures = measures_from_score(score)
    return _Finished(
        music_xml_text,
        score,
        measures,
        check_measures(measures),
        time_signature_source,
        meter_changes,
    )


def _page_issue_share(
    music_xml: str,
    signature: tuple[int, int] | None,
    user_time: tuple[int, int] | None,
) -> float:
    """Доля подозрительных тактов страницы после той же постобработки, что и у всей пьесы:
    сырой результат homr на фото почти весь «вылезает» из тактов (общий курсор рук), и по нему
    плохую страницу от хорошей не отличить. Размер печатают только в начале пьесы, поэтому
    странице без него ставится размер прошлых страниц."""
    try:
        if signature is not None and not _has_time_signature(music_xml):
            music_xml = set_time_signature(music_xml, *signature)
        finished = _postprocess(music_xml, user_time)
    except Exception:
        return 1.0
    if not finished.measures:
        return 0.0
    return len(finished.issues) / len(finished.measures)


def _known_signature(documents: list[str | None]) -> tuple[int, int] | None:
    """Размер с уже распознанных страниц."""
    for doc in documents:
        if doc is None:
            continue
        match = re.search(r"<beats>(\d+)</beats>\s*<beat-type>(\d+)</beat-type>", doc)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def _try_upside_down(
    engine: "PageEngine",
    image: Path,
    text: str,
    work: Path,
    listener: "Listener",
    signature: tuple[int, int] | None,
    user_time: tuple[int, int] | None,
) -> tuple[Path, str] | None:
    """Страница, где подозрительна большая часть тактов, распознаётся ещё раз повёрнутой на 180°:
    фото бывает снято вверх ногами (страницы 2 и 4 «You've Got a Friend in Me»), и EXIF этого
    не знает. Повёрнутый вариант принимается, только если тактов с ошибками в нём хотя бы
    вдвое меньше и сам он ниже порога: перевёрнутые ноты иногда случайно складываются в такты.
    Тогда картинка страницы заменяется повёрнутой — по ней дальше режутся строки и читается
    текст."""
    share = _page_issue_share(text, signature, user_time)
    if share < UPSIDE_DOWN_SHARE:
        return None
    rotated = image.with_name(f"{image.stem}-r180{image.suffix}")
    with Image.open(image) as picture:
        picture.rotate(180).save(rotated)
    try:
        output = engine.recognize_page(rotated, work, should_stop=listener.should_stop)
    except EngineCancelled:
        raise
    except EngineError:
        rotated.unlink(missing_ok=True)
        return None
    rotated_text = _read_text(output)
    rotated_share = _page_issue_share(rotated_text, signature, user_time)
    if rotated_share * 2 > share or rotated_share >= UPSIDE_DOWN_SHARE:
        rotated.unlink(missing_ok=True)
        return None
    rotated.replace(image)
    return output, rotated_text


def _correct_engine_meter(music_xml: str) -> str | None:
    """Размер по сумме длительностей в голосах вместо верхней цифры от homr; None — не нужно.

    homr читает только нижнюю цифру размера, а верхнюю берёт как медиану длин тактов. Длину
    такта он считает по общему курсору обеих рук, поэтому на фото, где нота одной руки
    вступает на фоне длинной ноты другой, такты вытягиваются, и 4/4 становится 5/4. Сумма
    длительностей голоса этих дырок не видит. Нижняя цифра остаётся от homr, если с ней
    получается целое число долей (6/8 не превращается в 3/4)."""
    root = ET.fromstring(music_xml.encode("utf-8"))
    # homr ставит размер на каждой странице свой (медиана её тактов), поэтому их может быть
    # несколько: 5/4 на первой странице и 2/2 на последней.
    times = list(root.iter("time"))
    if not times:
        return None
    inferred = infer_time_signature(measures_from_score(parse_score(music_xml)))
    if inferred is None:
        return None
    length = Fraction(inferred[0] * 4, inferred[1])  # в четвертях
    if all(
        Fraction(int(t.findtext("beats")) * 4, int(t.findtext("beat-type"))) == length
        for t in times
    ):
        return None
    beat_type = int(times[0].findtext("beat-type"))
    beats = length * beat_type / 4
    signature = (int(beats), beat_type) if beats.denominator == 1 else inferred
    log.info("Размер от движка заменён на %d/%d по длинам голосов", *signature)
    return replace_time_signature(music_xml, *signature)


def _has_time_signature(music_xml: str) -> bool:
    return re.search(r"<time[\s>]", music_xml) is not None


def _positions(output: Path | None) -> Path | None:
    """Файл движка с положением строк на странице (homr --write-staff-positions)."""
    if output is None:
        return None
    positions = output.with_suffix(".txt")
    return positions if positions.exists() else None


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


def _main_time_signature(score: m21.stream.Score) -> str | None:
    """Размер, действующий в большинстве тактов, а не первый найденный: первым бывает
    лишний нотоносец над нотами или короткая смена размера."""
    return _most_common(score, m21.meter.TimeSignature, lambda ts: ts.ratioString)


def _main_key(score: m21.stream.Score) -> int | None:
    """Тональность большинства тактов (ключевые знаки первой строки бывают прочитаны неверно)."""
    return _most_common(score, m21.key.KeySignature, lambda key: key.sharps)


def _most_common(score: m21.stream.Score, cls: type, value: Callable) -> object | None:
    counts: Counter = Counter()
    for part in score.parts:
        current = None
        for measure in part.getElementsByClass(m21.stream.Measure):
            found = next(iter(measure.getElementsByClass(cls)), None)
            if found is not None:
                current = value(found)
            if current is not None:
                counts[current] += 1
    return counts.most_common(1)[0][0] if counts else None
