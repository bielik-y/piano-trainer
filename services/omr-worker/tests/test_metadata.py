from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf

from omr_worker import metadata
from omr_worker.measures import check_measures, measures_from_score, parse_score
from omr_worker.merge import set_score_info
from omr_worker.metadata import ScoreInfo, TextLine, classify_lines, read_score_info
from omr_worker.pipeline import run_pipeline

from .fixtures import good_measure, score
from .test_empty_staves import make_page
from .test_pipeline import FakeEngine, make_pdf


def line(text: str, x0: float, x1: float, y0: float, height: float = 0.02) -> TextLine:
    return TextLine(text, x0, x1, y0, y0 + height)


def test_title_composer_and_tempo_word():
    # Раскладка «Just The Two Of Us».
    info = classify_lines(
        [
            line("JUST THE TWO OF US", 0.40, 0.60, 0.066, 0.028),
            line("Bill Withers", 0.87, 0.96, 0.113),
            line("Moderately", 0.06, 0.15, 0.202),
        ],
        staff_top=0.27,
    )
    assert info == ScoreInfo("JUST THE TWO OF US", "Bill Withers", "Moderately", None)


def test_arranger_is_not_composer_and_subtitle_is():
    # Раскладка «Champange Coast»: автор по центру под названием, справа аранжировщик.
    info = classify_lines(
        [
            line("Champange Coast (TikTok Version)", 0.16, 0.83, 0.036, 0.038),
            line("Blood Orange", 0.41, 0.58, 0.076),
            line("Arranged by: @ethantunes", 0.73, 0.95, 0.094),
            line("=123", 0.15, 0.23, 0.120),
        ],
        staff_top=0.14,
    )
    assert info == ScoreInfo("Champange Coast (TikTok Version)", "Blood Orange", None, 123)


def test_source_line_is_not_composer():
    info = classify_lines(
        [
            line("YOU'VE GOT A FRIEND IN ME", 0.37, 0.63, 0.065, 0.028),
            line("From Toy Story", 0.84, 0.96, 0.113),
            line("Easy Shuffle", 0.11, 0.22, 0.229),
        ],
        staff_top=0.3,
    )
    assert info.composer is None
    assert info.tempo_text == "Easy Shuffle"


def test_music_by_without_title_and_chord_is_not_tempo():
    # Фрагмент: названия нет, над нотоносцем аккорды.
    info = classify_lines(
        [
            line("Music by Justin Hurwitz", 0.79, 0.99, 0.0),
            line("Lyrics by Benj Pasek and Justin Paul", 0.69, 0.98, 0.031),
            line("Fast", 0.13, 0.18, 0.068),
            line("Abmaj7", 0.16, 0.23, 0.097),
        ],
        staff_top=0.15,
    )
    assert info == ScoreInfo(None, "Justin Hurwitz", "Fast", None)


def test_years_and_instrument_label_are_ignored():
    info = classify_lines(
        [
            line("Prelude in E Minor, Op. 28, No. 4", 0.35, 0.65, 0.031),
            line("Frederic Chopin", 0.84, 0.94, 0.071),
            line("1810-49", 0.89, 0.94, 0.081),
            line("Piano", 0.06, 0.11, 0.09),
            line("Largo", 0.21, 0.26, 0.095),
        ],
        staff_top=0.12,
    )
    assert info == ScoreInfo("Prelude in E Minor, Op. 28, No. 4", "Frederic Chopin", "Largo", None)


def test_number_without_equals_is_not_tempo():
    # На фрагменте с аккордами OCR прочитал ноты как 48.
    info = classify_lines(
        [line("48", 0.12, 0.18, 0.302), line("120", 0.15, 0.18, 0.215)], staff_top=0.16
    )
    assert info.tempo_bpm is None


def test_tempo_with_equals_inside_system_is_found():
    info = classify_lines([line("= 120", 0.11, 0.19, 0.194)], staff_top=0.03)
    assert info.tempo_bpm == 120


def test_implausible_tempo_is_ignored():
    info = classify_lines(
        [line("= 999", 0.15, 0.2, 0.1), line("600", 0.58, 0.6, 0.11)], staff_top=0.03
    )
    assert info.tempo_bpm is None


def test_score_info_is_written_to_music_xml():
    page = score(good_measure(1, time="4/4")).replace(
        "<part-list>",
        "<work><work-title>Moderatley</work-title></work>"
        "<identification><encoding><software>homr</software></encoding></identification>"
        "<part-list>",
    )

    result = set_score_info(page, ScoreInfo("Song", "Author", "Allegro", 120))

    root = ET.fromstring(result)
    assert [e.text for e in root.iter("work-title")] == ["Song"]
    assert root.findtext("identification/creator") == "Author"
    measure = root.find("part/measure")
    tags = [child.tag for child in measure]
    assert tags.index("attributes") < tags.index("direction") < tags.index("note")
    assert measure.findtext("direction/direction-type/words") == "Allegro"
    assert measure.findtext("direction/direction-type/metronome/per-minute") == "120"
    assert measure.find("direction/sound").get("tempo") == "120"
    assert check_measures(measures_from_score(parse_score(result))) == {}


def test_engine_title_is_removed_when_nothing_found():
    page = score(good_measure(1, time="4/4")).replace(
        "<part-list>", "<work><work-title>Moderatley</work-title></work><part-list>"
    )
    assert "Moderatley" not in set_score_info(page, ScoreInfo())


def test_text_layer_of_pdf_is_used_without_ocr(tmp_path: Path, monkeypatch):
    def fail(picture):
        raise AssertionError("OCR не нужен, текст есть в PDF")

    monkeypatch.setattr(metadata, "_run_ocr", fail)
    pdf = tmp_path / "in.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((230, 60), "Some Title", fontsize=24)
    page.insert_text((480, 100), "John Smith", fontsize=11)
    page.insert_text((50, 130), "Allegro", fontsize=11)
    doc.save(pdf)
    image = tmp_path / "1.png"
    pymupdf.open(pdf)[0].get_pixmap(dpi=50).save(image)

    info = read_score_info(image, pdf, 0)

    assert info == ScoreInfo("Some Title", "John Smith", "Allegro", None)


def test_pdf_header_partly_in_picture_is_completed_by_ocr(tmp_path: Path, monkeypatch):
    # Как в «You've Got A Friend In Me»: название текстом, темп вставлен картинкой.
    pdf = tmp_path / "in.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((230, 60), "Some Title", fontsize=24)
    doc.save(pdf)
    image = tmp_path / "1.png"
    pymupdf.open(pdf)[0].get_pixmap(dpi=72).save(image)
    monkeypatch.setattr(
        metadata,
        "_run_ocr",
        lambda picture: [
            ("Sorne Tit1e", 230.0, 370.0, 40.0, 62.0),
            ("Easy Shuffle", 50.0, 130.0, 120.0, 135.0),
        ],
    )

    info = read_score_info(image, pdf, 0)

    assert info.title == "Some Title"
    assert info.tempo_text == "Easy Shuffle"


def test_image_uses_ocr(tmp_path: Path, monkeypatch):
    image = make_page(tmp_path / "1.png", [True])
    monkeypatch.setattr(
        metadata,
        "_run_ocr",
        lambda picture: [("Some Title", 500.0, 900.0, 5.0, 25.0)],
    )
    assert read_score_info(image).title == "Some Title"


def test_ocr_failure_does_not_fail_job(tmp_path: Path, monkeypatch):
    def fail(picture):
        raise RuntimeError("модель не загрузилась")

    monkeypatch.setattr(metadata, "_run_ocr", fail)
    image = make_page(tmp_path / "1.png", [True])
    engine = FakeEngine([score(good_measure(1, time="4/4"))])

    report = run_pipeline([image], tmp_path / "job", engine, min_ok_ratio=0.4).report

    assert report.measure_count == 1
    assert report.title is None


def test_report_contains_score_info(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "omr_worker.pipeline.read_score_info", lambda *args: ScoreInfo("X", "Y", "Z", 90)
    )
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    engine = FakeEngine([score(good_measure(1, time="4/4"))])

    output = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50)

    report = output.report
    assert (report.title, report.composer, report.tempo_text, report.tempo_bpm) == ("X", "Y", "Z", 90)
    assert "<work-title>X</work-title>" in output.music_xml.read_text(encoding="utf-8")
