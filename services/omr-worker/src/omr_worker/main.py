"""Точка входа воркера.

    omr-worker serve                         слушать очередь (локально — таблица SQLite)
    omr-worker recognize FILE... [--out DIR] распознать файлы без API и очереди

Настройки — переменные окружения, см. config.py.
"""

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from .config import Settings, load_settings
from .engines.cli import HomrEngine
from .jobs import JobStore
from .merge import parse_time_signature
from .models import Cancelled, OmrFailure, PageInfo, Progress
from .pipeline import run_pipeline

log = logging.getLogger("omr_worker")

LOW_QUALITY_MESSAGE = (
    "Не удалось надёжно распознать: нормальных тактов {ok:.0%}, нужно не меньше {min:.0%}. "
    "Попробуйте PDF лучшего качества или файл MusicXML"
)


def make_engine(settings: Settings) -> HomrEngine:
    if not settings.homr_exe.exists():
        raise SystemExit(
            f"Не найден homr: {settings.homr_exe}. Укажите путь в OMR_HOMR_EXE "
            "(локально homr ставится в bench/envs/homr, см. docs/RUNNING.md)"
        )
    return HomrEngine(settings.homr_exe, timeout_s=settings.page_timeout_s)


class JobListener:
    """Пишет прогресс в базу и раз в 0,5 с проверяет, не отменили ли задачу."""

    def __init__(self, store: JobStore, job_id: str) -> None:
        self.store = store
        self.job_id = job_id
        self.pages: list[PageInfo] | None = None
        self._checked_at = 0.0
        self._stop = False

    def on_progress(self, progress: Progress, pages: list[PageInfo]) -> None:
        self.pages = pages
        self.store.update_progress(self.job_id, progress, pages)
        log.info(
            "%s: %s %s%%%s",
            self.job_id,
            progress.stage,
            progress.percent,
            f", страница {progress.page}/{progress.page_count}" if progress.page else "",
        )

    def should_stop(self) -> bool:
        now = time.monotonic()
        if not self._stop and now - self._checked_at >= 0.5:
            self._checked_at = now
            self._stop = self.store.is_cancel_requested(self.job_id)
        return self._stop


def process_job(store: JobStore, settings: Settings, engine: HomrEngine, job_id: str,
                source_paths: list[str], time_signature: tuple[int, int] | None = None) -> None:
    job_dir = settings.job_dir(job_id)
    listener = JobListener(store, job_id)
    try:
        output = run_pipeline(
            [job_dir / p for p in source_paths],
            job_dir,
            engine,
            min_ok_ratio=settings.min_ok_ratio,
            dpi=settings.raster_dpi,
            max_pdf_pages=settings.max_pdf_pages,
            listener=listener,
            time_signature=time_signature,
        )
    except Cancelled:
        store.mark_cancelled(job_id, listener.pages)
        log.info("%s: отменена", job_id)
        return
    except OmrFailure as e:
        store.fail(job_id, e.code, e.message, listener.pages)
        log.warning("%s: ошибка %s — %s", job_id, e.code, e.message)
        return
    except Exception as e:
        log.exception("%s: внутренняя ошибка", job_id)
        store.fail(job_id, "engine_failed", f"Внутренняя ошибка воркера: {e}", listener.pages)
        return
    report = output.report
    if report.quality == "low":
        message = LOW_QUALITY_MESSAGE.format(ok=report.ok_ratio, min=report.min_ok_ratio)
        store.finish(job_id, report, output.pages, error=("low_quality", message))
        log.warning("%s: low_quality, нормальных тактов %.0f%%", job_id, report.ok_ratio * 100)
    else:
        store.finish(job_id, report, output.pages)
        log.info("%s: готово, тактов %s, нормальных %.0f%%", job_id, report.measure_count,
                 report.ok_ratio * 100)


def serve(settings: Settings) -> None:
    engine = make_engine(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = JobStore(settings.db_path)
    log.info("База задач: %s", settings.db_path)
    while not store.table_exists():
        log.info("Таблицы omr_jobs ещё нет — запустите API (pnpm dev:api), жду…")
        time.sleep(3)
    interrupted = store.fail_interrupted()
    if interrupted:
        log.warning("Прерванных задач после прошлого запуска: %s", interrupted)
    log.info("Жду задачи (homr %s)", engine.version() or "?")
    try:
        while True:
            job = store.claim()
            if job is None:
                time.sleep(settings.poll_interval_s)
                continue
            log.info("%s: взята в работу%s", job.id,
                     f", размер {job.time_signature[0]}/{job.time_signature[1]}"
                     if job.time_signature else "")
            process_job(store, settings, engine, job.id, job.source_paths, job.time_signature)
    except KeyboardInterrupt:
        log.info("Остановлен")
    finally:
        store.close()


def recognize(settings: Settings, files: list[Path], out: Path,
              time_signature: tuple[int, int] | None = None) -> int:
    engine = make_engine(settings)
    out.mkdir(parents=True, exist_ok=True)

    class Printer:
        def on_progress(self, progress: Progress, pages: list[PageInfo]) -> None:
            page = f" страница {progress.page}/{progress.page_count}" if progress.page else ""
            print(f"[{progress.percent:3}%] {progress.stage}{page}", flush=True)

        def should_stop(self) -> bool:
            return False

    source_dir = out / "source"
    source_dir.mkdir(exist_ok=True)
    sources = []
    for n, f in enumerate(files, start=1):
        target = source_dir / f"{n:02}-{f.name}"
        shutil.copyfile(f, target)
        sources.append(target)
    try:
        output = run_pipeline(
            sources,
            out,
            engine,
            min_ok_ratio=settings.min_ok_ratio,
            dpi=settings.raster_dpi,
            max_pdf_pages=settings.max_pdf_pages,
            listener=Printer(),
            time_signature=time_signature,
        )
    except OmrFailure as e:
        print(f"Ошибка {e.code}: {e.message}", file=sys.stderr)
        return 1
    report = output.report
    print(json.dumps(report.dump() | {"suspiciousMeasures": len(report.suspicious_measures)},
                     ensure_ascii=False, indent=2))
    print(f"MusicXML: {output.music_xml}\nОтчёт:    {output.report_path}")
    if report.quality == "low":
        print("low_quality: " + LOW_QUALITY_MESSAGE.format(ok=report.ok_ratio,
                                                         min=report.min_ok_ratio))
        return 2
    return 0


def cli(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="omr-worker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="слушать очередь задач")
    rec = commands.add_parser("recognize", help="распознать файлы без API")
    rec.add_argument("files", nargs="+", type=Path, help="1 PDF или фото по порядку страниц")
    rec.add_argument("--out", type=Path, default=Path("omr-out"), help="папка результата")
    rec.add_argument("--time-signature", metavar="N/M",
                     help="размер пьесы, например 3/4; по умолчанию определяется по нотам")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "serve":
        serve(settings)
        return 0
    time_signature = None
    if args.time_signature:
        time_signature = parse_time_signature(args.time_signature)
        if time_signature is None:
            parser.error(f"--time-signature: ожидается размер вида 3/4, получено {args.time_signature}")
    return recognize(settings, args.files, args.out, time_signature)


def main() -> None:
    sys.exit(cli())


if __name__ == "__main__":
    main()
