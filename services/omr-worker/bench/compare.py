"""Сравнение распознанного MusicXML с эталоном по тактам и автопроверка тактов.

Сравниваем только то, что нужно режиму игры (`PracticeScore`): нотоносец, onset внутри такта,
высоту, длительность, форшлаг и продолжение лиги. Динамика, артикуляция, аппликатура и голоса
не учитываются.

Автопроверка повторяет правила `score-core.validateMeasures()` из ARCHITECTURE §7.3:
- сумма длительностей в голосе ≠ длине такта по размеру (короче можно только первому и
  последнему такту пьесы — затакт и неполный финал);
- такт есть не на всех нотоносцах (у нотоносцев разное число тактов);
- такт пустой: ни нот, ни пауз.
"""

import warnings
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import music21 as m21

# (нотоносец, onset в четвертях от начала такта, MIDI-высота, длительность, форшлаг, продолжение лиги)
NoteKey = tuple[int, Fraction, int, Fraction, bool, bool]


@dataclass
class Measure:
    notes: Counter[NoteKey] = field(default_factory=Counter)
    # По нотоносцам: суммы длительностей каждого голоса; None — такта на нотоносце нет.
    voice_lengths: list[list[Fraction] | None] = field(default_factory=list)
    has_events: bool = False
    expected_length: Fraction | None = None
    # Конец самого позднего события такта (onset + длительность) по всем нотоносцам.
    end: Fraction = Fraction(0)


@dataclass
class PageResult:
    gt_measures: int
    result_measures: int
    correct: int  # совпал с эталоном и не помечен проверкой
    flagged: int  # помечен автопроверкой (исключается из оценки)
    silent_errors: int  # неверен, но проверка его пропустила
    extra_measures: int  # лишние такты в результате, не помеченные проверкой
    tie_only_errors: int = 0  # из silent_errors: ноты верны, неверны только лиги

    @property
    def flagged_rate(self) -> float:
        return self.flagged / self.gt_measures if self.gt_measures else 0.0

    @property
    def silent_error_rate(self) -> float:
        return (
            (self.silent_errors + self.extra_measures) / self.gt_measures
            if self.gt_measures
            else 0.0
        )

    @property
    def correct_rate(self) -> float:
        return self.correct / self.gt_measures if self.gt_measures else 0.0


def _q(value: float | Fraction) -> Fraction:
    # music21 отдаёт длительности как float или Fraction; приводим к точной дроби.
    return Fraction(value).limit_denominator(64)


def load_score(path: Path) -> m21.stream.Score:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return m21.converter.parse(str(path), forceSource=True)


def slice_score(score: m21.stream.Score, first: int, count: int) -> m21.stream.Score:
    """Такты [first, first + count) каждой партии (по порядку, а не по номерам тактов).

    Размер, ключ и знаки из предыдущих тактов переносятся в первый такт среза."""
    sliced = m21.stream.Score()
    for part in score.parts:
        measures = list(part.getElementsByClass(m21.stream.Measure))[first : first + count]
        new_part = m21.stream.PartStaff()
        for index, measure in enumerate(measures):
            copy = measure.__deepcopy__()
            if index == 0:
                for cls in (m21.clef.Clef, m21.meter.TimeSignature, m21.key.KeySignature):
                    if not copy.getElementsByClass(cls):
                        context = measure.getContextByClass(cls)
                        if context is not None:
                            copy.insert(0, context.__deepcopy__())
            new_part.append(copy)
        sliced.insert(0, new_part)
    return sliced


def omr_ned(gt: m21.stream.Score, result: m21.stream.Score) -> float:
    """OMR-NED (musicdiff): редакционное расстояние по символам, нормированное на их число.
    0 — совпадение, 1 — ничего общего. Нужен для сравнения с публикациями, не для выбора."""
    from musicdiff import AnnScore, Comparison, DetailLevel
    from musicdiff.visualization import Visualization

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ann_result = AnnScore(result, DetailLevel.Default)
        ann_gt = AnnScore(gt, DetailLevel.Default)
        _, distance = Comparison.annotated_scores_diff(ann_result, ann_gt)
    return Visualization.get_omr_ned(distance, ann_result.notation_size(), ann_gt.notation_size())


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
            if time_sig is not None and target.expected_length is None:
                target.expected_length = _q(time_sig.barDuration.quarterLength)

            voices = list(measure.voices) or [measure]
            target.voice_lengths[staff_no - 1] = [
                sum(
                    (_q(e.quarterLength) for e in voice.notesAndRests if not e.duration.isGrace),
                    Fraction(0),
                )
                for voice in voices
            ]
            flat = measure.flatten()
            if flat.notesAndRests:
                target.has_events = True
            for element in flat.notesAndRests:
                if not element.duration.isGrace:
                    target.end = max(target.end, _q(element.offset) + _q(element.quarterLength))
            for element in flat.notes:
                grace = element.duration.isGrace
                tie_cont = element.tie is not None and element.tie.type in ("stop", "continue")
                for pitch in element.pitches:
                    target.notes[
                        (
                            staff_no,
                            _q(element.offset),
                            pitch.midi,
                            Fraction(0) if grace else _q(element.quarterLength),
                            grace,
                            tie_cont,
                        )
                    ] += 1
    return measures


def flag_measures(
    measures: list[Measure],
    piece_start: bool,
    piece_end: bool,
    default_length: Fraction | None = None,
) -> set[int]:
    """Индексы тактов, которые автопроверка исключает из оценки.

    `default_length` — длина такта по размеру, действующему с предыдущих страниц. Размер печатают
    только в начале пьесы, а движки видят по одной странице; в приложении страницы склеиваются,
    и размер с первой страницы действует дальше."""
    flagged: set[int] = set()
    last = len(measures) - 1
    for index, measure in enumerate(measures):
        if any(lengths is None for lengths in measure.voice_lengths) or not measure.has_events:
            flagged.add(index)
            continue
        expected = measure.expected_length or default_length
        if expected is None:
            flagged.add(index)
            continue
        # Событие выходит за конец такта (голос начат не с начала такта и т. п.).
        if measure.end > expected:
            flagged.add(index)
            continue
        may_be_short = (piece_start and index == 0) or (piece_end and index == last)
        for lengths in measure.voice_lengths:
            for length in lengths or []:
                # Голос без событий (пустой <voice>) не нарушение.
                if length == 0:
                    continue
                if length > expected or (length < expected and not may_be_short):
                    flagged.add(index)
    return flagged


def _similarity(a: Measure, b: Measure) -> float:
    if not a.notes and not b.notes:
        return 1.0
    common = sum((a.notes & b.notes).values())
    total = sum((a.notes | b.notes).values())
    return common / total if total else 0.0


def align(gt: list[Measure], result: list[Measure]) -> list[tuple[int | None, int | None]]:
    """Выравнивает такты эталона и результата (DP по сходству нот).

    Пары (i, j): такт эталона i сопоставлен такту результата j; None — пропуск с одной стороны.
    При равном числе тактов это просто сопоставление по индексу."""
    if len(gt) == len(result):
        return [(i, i) for i in range(len(gt))]
    n, m = len(gt), len(result)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score[i][j] = max(
                score[i - 1][j],
                score[i][j - 1],
                score[i - 1][j - 1] + _similarity(gt[i - 1], result[j - 1]),
            )
    pairs: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and score[i][j] == score[i - 1][j - 1] + _similarity(gt[i - 1], result[j - 1])
        ):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or score[i][j] == score[i - 1][j]):
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    return pairs[::-1]


def compare(
    gt: list[Measure],
    result: list[Measure],
    piece_start: bool = True,
    piece_end: bool = True,
    default_length: Fraction | None = None,
) -> PageResult:
    """Сравнивает такты страницы. `gt` — такты эталона именно этой страницы."""
    flagged_result = flag_measures(result, piece_start, piece_end, default_length)
    correct = flagged = silent = extra = tie_only = 0
    for gi, rj in align(gt, result):
        if gi is None:
            # Лишний такт: если проверка его не поймала, игрок получит лишние «ошибки».
            if rj not in flagged_result:
                extra += 1
            continue
        if rj is None:
            # Пропущенный такт проверка увидеть не может.
            silent += 1
        elif rj in flagged_result:
            flagged += 1
        elif gt[gi].notes == result[rj].notes:
            correct += 1
        else:
            silent += 1
            if _without_ties(gt[gi].notes) == _without_ties(result[rj].notes):
                tie_only += 1
    return PageResult(
        gt_measures=len(gt),
        result_measures=len(result),
        correct=correct,
        flagged=flagged,
        silent_errors=silent,
        extra_measures=extra,
        tie_only_errors=tie_only,
    )


def _without_ties(notes: Counter[NoteKey]) -> Counter:
    stripped: Counter = Counter()
    for key, count in notes.items():
        stripped[key[:5]] += count
    return stripped
