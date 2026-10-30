"""Тесты сравнения тактов бенчмарка OMR (bench/compare.py) на синтетических партитурах."""

from pathlib import Path

import pytest

m21 = pytest.importorskip(
    "music21", reason="нужна группа зависимостей bench: uv sync --group bench"
)

from bench.compare import compare, load_measures

# Такт = (правая рука, левая рука); рука = список (высота или "r" для паузы, длительность в четвертях).
Bar = tuple[list[tuple[str, float]], list[tuple[str, float]]]

C_MAJOR: list[Bar] = [
    ([("C5", 2), ("E5", 1), ("G5", 1)], [("C3", 4)]),
    ([("B4", 3), ("r", 1)], [("G2", 4)]),
    ([("A4", 4)], [("F2", 2), ("C3", 2)]),
]


def write_score(tmp_path: Path, name: str, bars: list[Bar], time_sig: str = "4/4") -> Path:
    score = m21.stream.Score()
    for staff_index, clef in ((0, m21.clef.TrebleClef()), (1, m21.clef.BassClef())):
        part = m21.stream.PartStaff()
        for number, bar in enumerate(bars, start=1):
            measure = m21.stream.Measure(number=number)
            if number == 1:
                measure.append([clef, m21.meter.TimeSignature(time_sig)])
            for pitch, length in bar[staff_index]:
                event = m21.note.Rest() if pitch == "r" else m21.note.Note(pitch)
                event.quarterLength = length
                measure.append(event)
            part.append(measure)
        score.insert(0, part)
    path = tmp_path / f"{name}.musicxml"
    # Без makeNotation music21 не дополняет неполные такты скрытыми паузами — как и движки OMR.
    score.write("musicxml", fp=str(path), makeNotation=False)
    return path


def run(tmp_path: Path, result_bars: list[Bar]):
    gt = load_measures(write_score(tmp_path, "gt", C_MAJOR))
    result = load_measures(write_score(tmp_path, "result", result_bars))
    return compare(gt, result)


def test_identical_score_is_fully_correct(tmp_path):
    page = run(tmp_path, C_MAJOR)
    assert (page.correct, page.flagged, page.silent_errors, page.extra_measures) == (3, 0, 0, 0)


def test_wrong_pitch_is_a_silent_error(tmp_path):
    bars = list(C_MAJOR)
    bars[0] = ([("C5", 2), ("F5", 1), ("G5", 1)], bars[0][1])
    page = run(tmp_path, bars)
    assert (page.correct, page.flagged, page.silent_errors) == (2, 0, 1)


def test_wrong_duration_is_caught_by_validation(tmp_path):
    bars = list(C_MAJOR)
    bars[1] = ([("B4", 2), ("r", 1)], bars[1][1])  # 3 доли вместо 4, такт не первый и не последний
    page = run(tmp_path, bars)
    assert (page.correct, page.flagged, page.silent_errors) == (2, 1, 0)


def test_event_past_barline_is_caught_by_validation(tmp_path):
    gt = load_measures(write_score(tmp_path, "gt", C_MAJOR))
    result = load_measures(write_score(tmp_path, "result", C_MAJOR))
    # Сумма длительностей в голосе верная, но голос начат со сдвигом и выходит за черту такта.
    result[1].end += 1
    assert compare(gt, result).flagged == 1


def test_wrong_tie_only_is_counted_separately(tmp_path):
    gt = load_measures(write_score(tmp_path, "gt", C_MAJOR))
    result = load_measures(write_score(tmp_path, "result", C_MAJOR))
    key = next(iter(result[2].notes))
    result[2].notes[key[:5] + (True,)] = result[2].notes.pop(key)
    page = compare(gt, result)
    assert (page.silent_errors, page.tie_only_errors) == (1, 1)


def test_short_last_measure_is_allowed(tmp_path):
    gt_bars = list(C_MAJOR)
    gt_bars[2] = ([("A4", 2)], [("F2", 2)])
    gt = load_measures(write_score(tmp_path, "gt", gt_bars))
    result = load_measures(write_score(tmp_path, "result", gt_bars))
    assert compare(gt, result).correct == 3
    # Но в середине пьесы (страница не последняя) такой такт помечается.
    assert compare(gt, result, piece_end=False).flagged == 1


def test_extra_measure_is_aligned_and_counted(tmp_path):
    extra: Bar = ([("D5", 4)], [("D3", 4)])
    page = run(tmp_path, [C_MAJOR[0], extra, C_MAJOR[1], C_MAJOR[2]])
    assert (page.correct, page.extra_measures, page.silent_errors) == (3, 1, 0)


def test_missing_measure_is_a_silent_error(tmp_path):
    page = run(tmp_path, [C_MAJOR[0], C_MAJOR[2]])
    assert (page.correct, page.silent_errors) == (2, 1)
