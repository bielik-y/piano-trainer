import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from omr_worker.engines.cli import EngineError, EngineNoMusic, HomrEngine
from omr_worker.models import OmrFailure
from omr_worker.pipeline import run_pipeline

from .fixtures import good_measure, score
from .test_empty_staves import make_page
from .test_pipeline import FakeEngine, make_pdf, make_photo


class NoMusicEngine(FakeEngine):
    """Страницы со значением None движок считает страницами без нот."""

    def recognize_page(self, image: Path, out_dir: Path,
                       should_stop: Callable[[], bool] | None = None) -> Path:
        if self.documents[self.calls] is None:
            self.calls += 1
            raise EngineNoMusic("fake: нет нот")
        return super().recognize_page(image, out_dir, should_stop)


def script_engine(code: str) -> HomrEngine:
    class Script(HomrEngine):
        def command(self, image: Path, out_dir: Path) -> list[str]:
            return [sys.executable, "-c", code]

    return Script(Path("homr"))


def test_page_without_music_is_not_an_error(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=2)
    engine = NoMusicEngine([score(good_measure(1, time="4/4")), None])
    output = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50)

    assert [(p.status, p.measure_count, p.error) for p in output.pages] == [
        ("done", 1, None),
        ("done", 0, None),
    ]


def test_only_pages_without_music_fail_as_no_music(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=1)
    with pytest.raises(OmrFailure) as failure:
        run_pipeline([pdf], tmp_path / "job", NoMusicEngine([None]), min_ok_ratio=0.4, dpi=50)
    assert failure.value.code == "no_music_found"


def test_page_of_empty_staves_is_not_sent_to_engine(tmp_path: Path):
    music = make_page(tmp_path / "1.png", [True])
    blank = make_page(tmp_path / "2.png", [False, False])
    engine = FakeEngine([score(good_measure(1, time="4/4"))])

    output = run_pipeline([music, blank], tmp_path / "job", engine, min_ok_ratio=0.4)

    assert engine.calls == 1
    assert [(p.status, p.measure_count) for p in output.pages] == [("done", 1), ("done", 0)]


def test_homr_no_noteheads_means_no_music(tmp_path: Path):
    engine = script_engine("print('Exception: No noteheads found'); raise SystemExit(1)")
    with pytest.raises(EngineNoMusic):
        engine.recognize_page(make_photo(tmp_path / "1.jpg"), tmp_path / "out")


def test_other_engine_failure_stays_an_error(tmp_path: Path):
    engine = script_engine("raise SystemExit(1)")
    with pytest.raises(EngineError) as failure:
        engine.recognize_page(make_photo(tmp_path / "1.jpg"), tmp_path / "out")
    assert not isinstance(failure.value, EngineNoMusic)
