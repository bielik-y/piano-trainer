import json
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from omr_worker.config import REPO_ROOT, Settings
from omr_worker.engines.cli import EngineError
from omr_worker.jobs import JobStore, now_iso
from omr_worker.main import process_job
from omr_worker.models import OmrFailure
from omr_worker.pipeline import run_pipeline

from .fixtures import bad_measure, good_measure, score


class FakeEngine:
    """Вместо homr: для каждой страницы по очереди отдаёт заранее заданный MusicXML."""

    name = "fake"

    def __init__(self, documents: list[str | None]) -> None:
        self.documents = list(documents)
        self.calls = 0

    def version(self) -> str | None:
        return "1.0"

    def recognize_page(self, image: Path, out_dir: Path,
                       should_stop: Callable[[], bool] | None = None) -> Path:
        doc = self.documents[self.calls]
        self.calls += 1
        if doc is None:
            raise EngineError("fake: сбой")
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{image.stem}.musicxml"
        target.write_text(doc, encoding="utf-8")
        return target


def make_pdf(path: Path, pages: int) -> Path:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(path)
    return path


def make_photo(path: Path, rotate_exif: bool = False) -> Path:
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    if rotate_exif:
        exif[0x0112] = 6  # повернуть на 90°
    image.save(path, format="JPEG", exif=exif)
    return path


def test_pdf_pages_are_recognized_merged_and_checked(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=2)
    engine = FakeEngine([
        score(good_measure(1, time="4/4"), good_measure(2)),
        score(good_measure(1), bad_measure(2)),
    ])
    output = run_pipeline([pdf], tmp_path / "job", engine, min_ok_ratio=0.4, dpi=50)

    report = output.report
    assert report.measure_count == 4
    assert report.ok_measure_count == 3
    assert report.quality == "ok"
    assert report.time_signature == "4/4"
    assert report.staff_count == 2
    assert [(s.index, s.page, s.reasons) for s in report.suspicious_measures] == [
        (3, 2, ["overflow"])
    ]
    assert [p.measure_count for p in output.pages] == [2, 2]
    assert (tmp_path / "job" / "pages" / "2.png").exists()
    saved = json.loads(output.report_path.read_text(encoding="utf-8"))
    assert saved["okRatio"] == 0.75 and len(saved["pages"]) == 2


def test_low_quality_below_threshold(tmp_path: Path):
    photo = make_photo(tmp_path / "a.jpg")
    engine = FakeEngine([score(good_measure(1, time="4/4"), bad_measure(2), bad_measure(3))])
    output = run_pipeline([photo], tmp_path / "job", engine, min_ok_ratio=0.4)
    assert output.report.ok_ratio == pytest.approx(1 / 3, abs=1e-3)
    assert output.report.quality == "low"
    assert output.music_xml.exists()  # результат всё равно сохранён


def test_photo_is_rotated_by_exif(tmp_path: Path):
    photo = make_photo(tmp_path / "a.jpg", rotate_exif=True)
    engine = FakeEngine([score(good_measure(1, time="4/4"))])
    output = run_pipeline([photo], tmp_path / "job", engine, min_ok_ratio=0.4)
    assert (output.pages[0].width, output.pages[0].height) == (20, 40)


def test_failed_page_is_skipped(tmp_path: Path):
    photos = [make_photo(tmp_path / f"{n}.jpg") for n in range(2)]
    engine = FakeEngine([None, score(good_measure(1, time="4/4"))])
    output = run_pipeline(photos, tmp_path / "job", engine, min_ok_ratio=0.4)
    assert [p.status for p in output.pages] == ["failed", "done"]
    assert output.report.suspicious_measures == []
    assert output.report.measure_count == 1


def test_all_pages_failed(tmp_path: Path):
    engine = FakeEngine([None])
    with pytest.raises(OmrFailure) as e:
        run_pipeline([make_photo(tmp_path / "a.jpg")], tmp_path / "job", engine, min_ok_ratio=0.4)
    assert e.value.code == "engine_failed"


def test_too_many_pdf_pages(tmp_path: Path):
    pdf = make_pdf(tmp_path / "in.pdf", pages=3)
    with pytest.raises(OmrFailure) as e:
        run_pipeline([pdf], tmp_path / "job", FakeEngine([]), min_ok_ratio=0.4, max_pdf_pages=2)
    assert e.value.code == "too_many_pages"


def test_unreadable_file(tmp_path: Path):
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"not an image")
    with pytest.raises(OmrFailure) as e:
        run_pipeline([junk], tmp_path / "job", FakeEngine([]), min_ok_ratio=0.4)
    assert e.value.code == "unreadable_file"


# --- Задача из очереди SQLite ---

# Те же миграции, что применяет API (apps/api/src/database/migrations.ts), по порядку номеров.
MIGRATIONS = sorted((REPO_ROOT / "packages" / "contracts" / "sql").glob("omr_0*.sql"))


def make_store(tmp_path: Path) -> JobStore:
    store = JobStore(tmp_path / "omr.sqlite")
    for migration in MIGRATIONS:
        store.db.executescript(migration.read_text(encoding="utf-8"))
    return store


def add_job(store: JobStore, job_id: str, files: list[dict]) -> None:
    now = now_iso()
    store.db.execute(
        "INSERT INTO omr_jobs (id, status, created_at, updated_at, source_kind, source_files)"
        " VALUES (?, 'queued', ?, ?, 'images', ?)",
        (job_id, now, now, json.dumps(files)),
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, homr_exe=Path("homr"), min_ok_ratio=0.4,
                    max_pdf_pages=20, raster_dpi=50, page_timeout_s=10, poll_interval_s=0.1)


def row(store: JobStore, job_id: str) -> dict:
    return dict(store.db.execute("SELECT * FROM omr_jobs WHERE id = ?", (job_id,)).fetchone())


def test_job_is_claimed_and_finished(tmp_path: Path):
    store = make_store(tmp_path)
    cfg = settings(tmp_path)
    source = cfg.job_dir("j1") / "source"
    source.mkdir(parents=True)
    make_photo(source / "01-a.jpg")
    add_job(store, "j1", [{"path": "source/01-a.jpg"}])

    job = store.claim()
    assert job is not None and job.id == "j1"
    assert store.claim() is None
    engine = FakeEngine([score(good_measure(1, time="4/4"), bad_measure(2), bad_measure(3))])
    process_job(store, cfg, engine, job.id, job.source_paths)  # type: ignore[arg-type]

    result = row(store, "j1")
    assert result["status"] == "failed"
    assert result["error_code"] == "low_quality"
    assert json.loads(result["result"])["measureCount"] == 3
    assert json.loads(result["progress"])["percent"] == 100
    assert result["revision"] >= 3


def test_cancel_requested_job(tmp_path: Path):
    store = make_store(tmp_path)
    cfg = settings(tmp_path)
    source = cfg.job_dir("j2") / "source"
    source.mkdir(parents=True)
    make_photo(source / "01-a.jpg")
    add_job(store, "j2", [{"path": "source/01-a.jpg"}])
    job = store.claim()
    assert job is not None
    store.db.execute("UPDATE omr_jobs SET cancel_requested = 1 WHERE id = 'j2'")

    process_job(store, cfg, FakeEngine([score(good_measure(1, time="4/4"))]), job.id,  # type: ignore[arg-type]
                job.source_paths)
    assert row(store, "j2")["status"] == "cancelled"


def test_interrupted_jobs_fail_on_start(tmp_path: Path):
    store = make_store(tmp_path)
    add_job(store, "j3", [])
    store.claim()
    assert store.fail_interrupted() == 1
    assert row(store, "j3")["error_code"] == "interrupted"
