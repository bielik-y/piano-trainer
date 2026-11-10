"""Разбор MusicXML по тактам и автопроверка тактов (ARCHITECTURE §7.3).

Используется и воркером (отчёт по тактам, порог `low_quality`), и бенчмарком (bench/compare.py).

Такт считается подозрительным, если:
- его нет на одном из нотоносцев (у нотоносцев разное число тактов) — `missing_on_staff`;
- в нём нет ни нот, ни пауз — `empty`;
- неизвестен размер (не напечатан и не унаследован) — `no_time_signature`;
- событие выходит за конец такта — `overflow`;
- сумма длительностей в голосе ≠ длине такта по размеру — `duration_mismatch`
  (короче можно первому такту пьесы — затакт; последнему — только если вместе с затактом он
  даёт целый такт; и дополнительному голосу, если другой голос того же нотоносца заполняет такт).
"""

import warnings
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import music21 as m21

# (нотоносец, onset в четвертях от начала такта, MIDI-высота, длительность, форшлаг, продолжение лиги)
NoteKey = tuple[int, Fraction, int, Fraction, bool, bool]

REASONS = ("missing_on_staff", "empty", "no_time_signature", "overflow", "duration_mismatch")

# Вычисление размера: сколько тактов нужно для вывода и какую долю должна занять самая частая длина.
MIN_MEASURES_TO_INFER = 4
MIN_SHARE_TO_INFER = 0.6


@dataclass
class Measure:
    notes: Counter[NoteKey] = field(default_factory=Counter)
    # По нотоносцам: суммы длительностей каждого голоса; None — такта на нотоносце нет.
    voice_lengths: list[list[Fraction] | None] = field(default_factory=list)
    has_events: bool = False
    expected_length: Fraction | None = None
    # Конец самого позднего события такта (onset + длительность) по всем нотоносцам.
    end: Fraction = Fraction(0)
    # Номер такта из партитуры (атрибут number первого нотоносца).
    number: str = ""


def q(value: float | Fraction) -> Fraction:
    # music21 отдаёт длительности как float или Fraction; приводим к точной дроби.
    return Fraction(value).limit_denominator(64)


def load_score(path: Path) -> m21.stream.Score:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return m21.converter.parse(str(path), forceSource=True)


def parse_score(music_xml: str) -> m21.stream.Score:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return m21.converter.parse(music_xml, format="musicxml", forceSource=True)


def load_measures(path: Path) -> list[Measure]:
    """Разбирает MusicXML (или .mxl) в список тактов по всем нотоносцам."""
    return measures_from_score(load_score(path))


def measures_from_score(score: m21.stream.Score) -> list[Measure]:
    parts = list(score.parts)
    per_staff = [list(part.getElementsByClass(m21.stream.Measure)) for part in parts]
    count = max((len(staff) for staff in per_staff), default=0)
    measures = [Measure(voice_lengths=[None] * len(parts)) for _ in range(count)]

    for staff_no, staff in enumerate(per_staff, start=1):
        time_sig: m21.meter.TimeSignature | None = None
        for index, measure in enumerate(staff):
            current = measure.timeSignature or measure.getContextByClass(m21.meter.TimeSignature)
            if current is not None:
                time_sig = current
            target = measures[index]
            if not target.number:
                target.number = str(measure.number) + (measure.numberSuffix or "")
            if time_sig is not None and target.expected_length is None:
                target.expected_length = q(time_sig.barDuration.quarterLength)

            voices = list(measure.voices) or [measure]
            target.voice_lengths[staff_no - 1] = [
                sum(
                    (q(e.quarterLength) for e in voice.notesAndRests if not e.duration.isGrace),
                    Fraction(0),
                )
                for voice in voices
            ]
            flat = measure.flatten()
            if flat.notesAndRests:
                target.has_events = True
            for element in flat.notesAndRests:
                if not element.duration.isGrace:
                    target.end = max(target.end, q(element.offset) + q(element.quarterLength))
            for element in flat.notes:
                grace = element.duration.isGrace
                tie_cont = element.tie is not None and element.tie.type in ("stop", "continue")
                for pitch in element.pitches:
                    target.notes[
                        (
                            staff_no,
                            q(element.offset),
                            pitch.midi,
                            Fraction(0) if grace else q(element.quarterLength),
                            grace,
                            tie_cont,
                        )
                    ] += 1
    return measures


def check_measures(
    measures: list[Measure],
    piece_start: bool = True,
    piece_end: bool = True,
    default_length: Fraction | None = None,
) -> dict[int, list[str]]:
    """Подозрительные такты: индекс → причины (из REASONS).

    `default_length` — длина такта по размеру, действующему с предыдущих страниц: размер печатают
    только в начале пьесы, поэтому при проверке отдельной страницы его передают явно."""
    issues: dict[int, list[str]] = {}
    last = len(measures) - 1
    for index, measure in enumerate(measures):
        if any(lengths is None for lengths in measure.voice_lengths):
            issues[index] = ["missing_on_staff"]
            continue
        if not measure.has_events:
            issues[index] = ["empty"]
            continue
        expected = measure.expected_length or default_length
        if expected is None:
            issues[index] = ["no_time_signature"]
            continue
        # Событие выходит за конец такта (голос начат не с начала такта и т. п.).
        if measure.end > expected:
            issues[index] = ["overflow"]
            continue
        may_be_short = (piece_start and index == 0) or (
            piece_end and index == last and _completes_pickup(measures, expected, piece_start)
        )
        for lengths in measure.voice_lengths:
            staff_is_full = expected in (lengths or [])
            for length in lengths or []:
                # Голос без событий (пустой <voice>) не нарушение.
                if length == 0:
                    continue
                if length > expected or (
                    length < expected and not may_be_short and not staff_is_full
                ):
                    issues[index] = ["duration_mismatch"]
    return issues


@dataclass(frozen=True)
class IssueDetails:
    """Подробности о подозрительном такте, чтобы приложение могло объяснить ошибку словами.

    Длины — в четвертях: «11 восьмых вместо 12» в 12/8 — length 5.5, expected_length 6."""

    # Нотоносец без такта (с 1) — для missing_on_staff.
    staff: int | None = None
    # overflow — конец самого позднего события; duration_mismatch — длина неверного голоса.
    length: float | None = None
    # Длина такта по размеру.
    expected_length: float | None = None


def issue_details(
    measures: list[Measure],
    issues: dict[int, list[str]],
    default_length: Fraction | None = None,
) -> dict[int, IssueDetails]:
    """Подробности для тактов, которые нашла check_measures (те же индексы)."""
    details: dict[int, IssueDetails] = {}
    for index, reasons in issues.items():
        measure = measures[index]
        expected = measure.expected_length or default_length
        if "missing_on_staff" in reasons:
            staff = next(i for i, v in enumerate(measure.voice_lengths) if v is None) + 1
            details[index] = IssueDetails(staff=staff)
        elif "overflow" in reasons and expected is not None:
            details[index] = IssueDetails(length=float(measure.end),
                                          expected_length=float(expected))
        elif "duration_mismatch" in reasons and expected is not None:
            lengths = [x for v in measure.voice_lengths for x in (v or []) if x and x != expected]
            # Длиннее размера — главная ошибка; иначе самый короткий из неполных голосов.
            longer = [x for x in lengths if x > expected]
            wrong = max(longer) if longer else min(lengths, default=None)
            details[index] = IssueDetails(
                length=float(wrong) if wrong is not None else None,
                expected_length=float(expected),
            )
        else:
            details[index] = IssueDetails()
    return details


def _completes_pickup(measures: list[Measure], expected: Fraction, piece_start: bool) -> bool:
    """Последний такт может быть неполным, только если вместе с затактом он даёт целый такт.

    Иначе короткий финал — это потерянные ноты. Если начала пьесы в проверке нет (отдельная
    страница), затакт не виден, и финал проверяется по-старому — неполный разрешён."""
    if not piece_start:
        return True
    if len(measures) < 2:
        return False
    first, last = measures[0], measures[-1]
    pickup = _longest_voice(first)
    first_length = first.expected_length or expected
    return pickup < first_length and pickup + _longest_voice(last) == expected


def infer_time_signature(measures: list[Measure]) -> tuple[int, int] | None:
    """Размер по длинам тактов: (доли, длительность доли) или None, если вывод ненадёжен.

    Длина такта — самый длинный его голос, поэтому короткий дополнительный голос не мешает.
    Первый и последний такты не считаются: там бывают затакт и неполный финал.
    По длине не отличить 3/4 от 6/8, выбирается размер с простой долей."""
    lengths = [
        length
        for measure in measures[1:-1]
        if (length := _longest_voice(measure)) > 0
    ]
    if len(lengths) < MIN_MEASURES_TO_INFER:
        return None
    length, count = Counter(lengths).most_common(1)[0]
    if count / len(lengths) < MIN_SHARE_TO_INFER:
        return None
    return _signature_for_length(length)


def _longest_voice(measure: Measure) -> Fraction:
    return max(
        (length for staff in measure.voice_lengths for length in staff or []),
        default=Fraction(0),
    )


def _signature_for_length(length: Fraction) -> tuple[int, int] | None:
    beat_type = 4 * length.denominator
    if beat_type > 16:
        return None  # 1/3 четверти и т. п.: это сбой длительностей, а не размер
    beats = int(length * beat_type / 4)
    return (beats, beat_type) if beats <= 12 else None


def flag_measures(
    measures: list[Measure],
    piece_start: bool,
    piece_end: bool,
    default_length: Fraction | None = None,
) -> set[int]:
    """Индексы тактов, которые автопроверка исключает из оценки."""
    return set(check_measures(measures, piece_start, piece_end, default_length))
