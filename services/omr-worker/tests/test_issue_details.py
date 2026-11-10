"""Подробности о подозрительных тактах: по ним приложение объясняет ошибку словами."""

from fractions import Fraction
from pathlib import Path

from omr_worker.measures import IssueDetails, Measure, check_measures, issue_details
from omr_worker.pipeline import run_pipeline

from .fixtures import measure, score
from .test_pipeline import FakeEngine, make_pdf

FOUR = Fraction(4)


def details(*measures: Measure) -> dict[int, IssueDetails]:
    found = list(measures)
    return issue_details(found, check_measures(found))


def test_short_voice_in_twelve_eight():
    # «В такте 11 восьмых вместо 12»: в 12/8 такт — 6 четвертей.
    full = Measure(voice_lengths=[[Fraction(6)]], has_events=True, expected_length=Fraction(6),
                   end=Fraction(6))
    short = Measure(voice_lengths=[[Fraction(11, 2)], [Fraction(6)]], has_events=True,
                    expected_length=Fraction(6), end=Fraction(6))
    assert details(full, short, full)[1] == IssueDetails(length=5.5, expected_length=6.0)


def test_overflow_reports_end_of_last_event():
    full = Measure(voice_lengths=[[FOUR]], has_events=True, expected_length=FOUR, end=FOUR)
    late = Measure(voice_lengths=[[FOUR]], has_events=True, expected_length=FOUR,
                   end=Fraction(9, 2))
    assert details(full, late, full)[1] == IssueDetails(length=4.5, expected_length=4.0)


def test_missing_staff_is_numbered_from_one():
    full = Measure(voice_lengths=[[FOUR], [FOUR]], has_events=True, expected_length=FOUR, end=FOUR)
    no_left_hand = Measure(voice_lengths=[[FOUR], None], has_events=True, expected_length=FOUR,
                           end=FOUR)
    assert details(full, no_left_hand, full)[1] == IssueDetails(staff=2)


def test_report_carries_details_and_meter_changes(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    full = ([("C5", 4)] * 4, [("C3", 16)])
    five = ([("C5", 4)] * 5, [("C3", 4)] * 5)
    late = ([("C5", 4)] * 4 + [("D5", 2)], [("C3", 16)])
    engine = FakeEngine([score(
        measure(1, *full, time="4/4"), measure(2, *full), measure(3, *five), measure(4, *full),
        measure(5, *late), measure(6, *full),
    )])

    report = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50).report

    assert [(c.index, c.number, c.time_signature) for c in report.time_signature_changes] == [
        (2, "3", "5/4")
    ]
    bad = {m.number: m for m in report.suspicious_measures}
    assert set(bad) == {"5"}
    assert bad["5"].expected_length == 4.0 and bad["5"].length == 4.5
    dumped = report.dump()
    assert dumped["timeSignatureChanges"] == [{"index": 2, "number": "3", "timeSignature": "5/4"}]
    assert dumped["suspiciousMeasures"][0]["expectedLength"] == 4.0
