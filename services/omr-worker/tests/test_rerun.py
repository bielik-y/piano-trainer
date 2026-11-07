from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.rerun import PageSource, map_systems, rerecognize, system_bounds, transplant

from .fixtures import bad_measure, good_measure, score

NEW_SYSTEM = '<print new-system="yes"/>'


def with_print(measure: str) -> str:
    return measure.replace(">", ">" + NEW_SYSTEM, 1)


def page(*measures: str) -> str:
    return score(*measures)


def issues(xml: str) -> set[int]:
    return set(check_measures(measures_from_score(parse_score(xml))))


def test_measures_are_mapped_to_pages_and_systems():
    # Страница 1: строки [1, 2] и [3]; страница 2: строка [4, 5].
    xml = page(
        good_measure(1, time="4/4"), good_measure(2), with_print(good_measure(3)),
        good_measure(4).replace(">", '><print new-page="yes"/>', 1), good_measure(5),
    )
    systems = map_systems(xml, [3, 0, 2])
    assert [(s.page, s.index, s.measures) for s in systems] == [
        (0, 0, [0, 1]), (0, 1, [2]), (2, 0, [3, 4]),
    ]


def test_system_bounds_reach_halfway_to_neighbours(tmp_path: Path):
    image = tmp_path / "p.png"
    Image.new("L", (1000, 1000), "white").save(image)
    positions = tmp_path / "p.txt"
    # Две строки: 100–200 и 500–600 пикселей.
    positions.write_text("1 0.5 0.15 0.9 0.1\n1 0.5 0.55 0.9 0.1\n", encoding="utf-8")
    assert system_bounds(positions, image) == [(40, 350), (350, 660)]


def test_transplant_keeps_markup_and_rescales_durations():
    original = page(good_measure(1, time="4/4"), with_print(bad_measure(2)))
    # Тот же такт из повторного распознавания с divisions = 8: длительности вдвое больше.
    candidate = ET.fromstring(
        '<measure number="1"><attributes><divisions>8</divisions></attributes>'
        "<note><pitch><step>D</step><octave>5</octave></pitch><duration>32</duration>"
        "<voice>1</voice><type>whole</type><staff>1</staff></note>"
        "<backup><duration>32</duration></backup>"
        "<note><pitch><step>D</step><octave>3</octave></pitch><duration>32</duration>"
        "<voice>5</voice><type>whole</type><staff>2</staff></note></measure>"
    )

    result = transplant(original, {1: candidate}, divisions=8)

    measure = ET.fromstring(result).findall("part/measure")[1]
    assert measure.find("print").get("new-system") == "yes"
    assert [d.text for d in measure.iter("duration")] == ["16", "16", "16"]
    assert issues(result) == set()


def test_only_flagged_measures_that_get_fixed_are_replaced(tmp_path: Path):
    image = tmp_path / "p.png"
    Image.new("RGB", (400, 400), "white").save(image)
    positions = tmp_path / "p.txt"
    positions.write_text("1 0.5 0.5 0.9 0.4\n", encoding="utf-8")
    raw = page(good_measure(1, time="4/4"), bad_measure(2), good_measure(3), good_measure(4))
    assert issues(raw) == {1}

    calls = []

    def recognize(crop: Path) -> str:
        calls.append(crop.name)
        # Повторно: такт 2 исправлен, а такт 3 «испортился» — его брать нельзя.
        return page(good_measure(1, time="4/4"), good_measure(2), bad_measure(3), good_measure(4))

    systems = map_systems(raw, [4])
    new_raw, replaced = rerecognize(
        raw, {1}, systems, [PageSource(image, positions)], recognize, issues,
        tmp_path / "rerun", lambda: False,
    )

    assert replaced == [1]
    assert issues(new_raw) == set()
    assert calls == ["p1-s1.png"]  # исправилось с первой попытки, вторая не нужна


def test_system_with_different_measure_count_is_skipped(tmp_path: Path):
    image = tmp_path / "p.png"
    Image.new("RGB", (400, 400), "white").save(image)
    positions = tmp_path / "p.txt"
    positions.write_text("1 0.5 0.5 0.9 0.4\n", encoding="utf-8")
    raw = page(good_measure(1, time="4/4"), bad_measure(2), good_measure(3))
    calls = []

    def recognize(crop: Path) -> str:
        calls.append(crop.name)
        return page(good_measure(1, time="4/4"), good_measure(2))

    new_raw, replaced = rerecognize(
        raw, {1}, map_systems(raw, [3]), [PageSource(image, positions)], recognize, issues,
        tmp_path / "rerun", lambda: False,
    )
    assert replaced == []
    assert new_raw == raw
    assert calls == ["p1-s1.png", "p1-s1-pad.png"]


def test_without_positions_nothing_is_rerun(tmp_path: Path):
    raw = page(good_measure(1, time="4/4"), bad_measure(2))

    def recognize(crop: Path) -> str:
        raise AssertionError("не должно вызываться")

    new_raw, replaced = rerecognize(
        raw, {1}, map_systems(raw, [2]), [PageSource(tmp_path / "p.png", None)], recognize,
        issues, tmp_path, lambda: False,
    )
    assert (new_raw, replaced) == (raw, [])
