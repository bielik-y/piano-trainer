"""Разбор MusicXML по тактам и автопроверка тактов (ARCHITECTURE §7.3).

Используется и воркером (отчёт по тактам, порог `low_quality`), и бенчмарком (bench/compare.py).

Такт считается подозрительным, если:
- его нет на одном из нотоносцев (у нотоносцев разное число тактов) — `missing_on_staff`;
- в нём нет ни нот, ни пауз — `empty`;
- неизвестен размер (не напечатан и не унаследован) — `no_time_signature`;
- событие выходит за конец такта — `overflow`;
- сумма длительностей в голосе ≠ длине такта по размеру — `duration_mismatch`
  (короче можно только первому и последнему такту пьесы — затакт и неполный финал).
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
        may_be_short = (piece_start and index == 0) or (piece_end and index == last)
        for lengths in measure.voice_lengths:
            for length in lengths or []:
                # Голос без событий (пустой <voice>) не нарушение.
                if length == 0:
                    continue
                if length > expected or (length < expected and not may_be_short):
                    issues[index] = ["duration_mismatch"]
    return issues


def flag_measures(
    measures: list[Measure],
    piece_start: bool,
    piece_end: bool,
    default_length: Fraction | None = None,
) -> set[int]:
    """Индексы тактов, которые автопроверка исключает из оценки."""
    return set(check_measures(measures, piece_start, piece_end, default_length))
