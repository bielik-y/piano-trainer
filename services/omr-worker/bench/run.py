"""Прогон движков OMR по набору bench/dataset.yaml.

- Готовит входы в bench/out/inputs/: страницы PDF растеризуются в PNG 300 dpi (как в воркере),
  фото копируются как есть.
- Запускает движки строго по одному процессу, чтобы время и память на страницу были честными.
- Пишет результаты в bench/out/<engine>/ и строку на каждый запуск в bench/out/results.jsonl.
  Уже посчитанные пары (движок, страница) пропускаются; --force перезапускает.

Запуск: uv run --group bench python bench/run.py --engines homr,audiveris [--only 'mozart*']
"""

import argparse
import fnmatch
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import psutil
import pymupdf
import yaml

from omr_worker.engines.cli import AudiverisEngine, CliEngine, HomrEngine, OemerEngine

BENCH = Path(__file__).parent
DATA = BENCH / "data"
OUT = BENCH / "out"
RESULTS = OUT / "results.jsonl"
ENVS = BENCH / "envs"

ENGINES: dict[str, CliEngine] = {
    "homr": HomrEngine(ENVS / "homr" / "Scripts" / "homr.exe"),
    "audiveris": AudiverisEngine(
        Path(os.environ.get("AUDIVERIS_EXE", r"D:\Programs\Audiveris\Audiveris.exe"))
    ),
    "oemer": OemerEngine(ENVS / "oemer" / "Scripts" / "oemer.exe"),
    "audiveris-x2": AudiverisEngine(
        Path(os.environ.get("AUDIVERIS_EXE", r"D:\Programs\Audiveris\Audiveris.exe")), upscale=2
    ),
}

RASTER_DPI = 300


@dataclass
class Page:
    id: str
    item_id: str
    kind: str
    image: Path
    truth: dict | str
    page_no: int | None  # номер страницы в PDF; None для фото
    page_count: int | None = None  # страниц в PDF


def load_pages() -> list[Page]:
    manifest = yaml.safe_load((BENCH / "dataset.yaml").read_text(encoding="utf-8"))
    inputs = OUT / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    pages: list[Page] = []
    for item in manifest["items"]:
        source = DATA / item["source"]
        if source.suffix.lower() == ".pdf":
            doc = pymupdf.open(source)
            for page_no in range(1, doc.page_count + 1):
                if page_no in item.get("skip_pages", []):
                    continue
                image = inputs / f"{item['id']}-p{page_no}.png"
                if not image.exists():
                    doc[page_no - 1].get_pixmap(dpi=RASTER_DPI).save(image)
                page_id = f"{item['id']}-p{page_no}"
                pages.append(
                    Page(
                        page_id,
                        item["id"],
                        item["kind"],
                        image,
                        item["truth"],
                        page_no,
                        doc.page_count,
                    )
                )
        else:
            image = inputs / f"{item['id']}{source.suffix.lower()}"
            if not image.exists():
                shutil.copyfile(source, image)
            pages.append(Page(item["id"], item["id"], item["kind"], image, item["truth"], None))
    return pages


def done_runs() -> set[tuple[str, str]]:
    if not RESULTS.exists():
        return set()
    runs = (json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line)
    return {(r["engine"], r["page"]) for r in runs}


def run_one(engine: CliEngine, page: Page) -> dict:
    out_dir = OUT / engine.name
    started = time.perf_counter()
    process, output = engine.popen(page.image, out_dir)
    peak = 0
    timed_out = False
    watched = psutil.Process(process.pid)
    while process.poll() is None:
        try:
            tree = [watched, *watched.children(recursive=True)]
            peak = max(peak, sum(p.memory_info().rss for p in tree if p.is_running()))
        except psutil.Error:
            pass
        if time.perf_counter() - started > engine.timeout_s:
            for p in [watched, *watched.children(recursive=True)]:
                try:
                    p.kill()
                except psutil.Error:
                    pass
            timed_out = True
            break
        time.sleep(0.5)
    process.wait()
    output = engine.finalize(output)
    seconds = time.perf_counter() - started
    ok = not timed_out and process.returncode == 0 and output.exists()
    return {
        "engine": engine.name,
        "page": page.id,
        "ok": ok,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "seconds": round(seconds, 1),
        "peak_mb": round(peak / 2**20),
        "output": str(output.relative_to(BENCH)) if ok else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engines", default="homr,audiveris,oemer")
    parser.add_argument(
        "--only", default="*", help="glob по id страницы через запятую, например 'mozart*,screen*'"
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    patterns = args.only.split(",")
    pages = [p for p in load_pages() if any(fnmatch.fnmatch(p.id, pat) for pat in patterns)]
    done = set() if args.force else done_runs()
    for name in args.engines.split(","):
        engine = ENGINES[name]
        for page in pages:
            if (name, page.id) in done:
                continue
            result = run_one(engine, page)
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            status = "ok" if result["ok"] else f"ОШИБКА (код {result['exit_code']})"
            print(
                f"{name:9} {page.id:24} {result['seconds']:7.1f} с {result['peak_mb']:5} МБ  {status}",
                flush=True,
            )


if __name__ == "__main__":
    main()
