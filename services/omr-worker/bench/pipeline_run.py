"""Прогон всего конвейера воркера (предобработка → homr → склейка → постобработка → повторное
распознавание строк) по набору bench/dataset.yaml. Меряет то, что увидит приложение.

bench/run.py меряет сырые движки по страницам; здесь — целые пьесы и правила воркера.
Результат homr кэшируется по хешу картинки (bench/out/homr-cache/), поэтому после правки
постобработки повторный прогон занимает секунды. Правка предобработки меняет картинки —
тогда homr запускается заново.

Запуск:
    uv run --group bench python -m bench.pipeline_run --label base
    uv run --group bench python -m bench.pipeline_run --label ties --compare base [--only 'friend*']
Итог: bench/out/pipeline/<label>/summary.json и таблица в консоли.
"""

import argparse
import fnmatch
import hashlib
import json
import logging
import re
import shutil
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import yaml

from bench.compare import compare, load_measures, load_score, measures_from_score, slice_score
from bench.run import BENCH, DATA, ENGINES, OUT
from omr_worker.engines.cli import EngineError, EngineNoMusic, HomrEngine
from omr_worker.models import OmrFailure
from omr_worker.pipeline import run_pipeline

CACHE = OUT / "homr-cache"
REFERENCE = DATA / "reference"
MIN_OK_RATIO = 0.4


class CachedEngine:
    """homr с кэшем по содержимому картинки: тот же вход — тот же результат без запуска."""

    def __init__(self, engine: HomrEngine) -> None:
        self.engine = engine
        self.name = engine.name
        self.hits = 0
        self.misses = 0

    def version(self) -> str | None:
        return self.engine.version()

    def recognize_page(
        self, image: Path, out_dir: Path, should_stop: Callable[[], bool] | None = None
    ) -> Path:
        key = hashlib.sha256(image.read_bytes()).hexdigest()[:24]
        cached = CACHE / key
        out_dir.mkdir(parents=True, exist_ok=True)
        if not (cached / "done.json").exists():
            self.misses += 1
            cached.mkdir(parents=True, exist_ok=True)
            try:
                output = self.engine.recognize_page(image, out_dir, should_stop)
                shutil.copyfile(output, cached / "page.musicxml")
                positions = output.with_suffix(".txt")
                if positions.exists():
                    shutil.copyfile(positions, cached / "page.txt")
                status = {"status": "ok"}
            except EngineNoMusic as e:
                status = {"status": "no_music", "error": str(e)}
            except EngineError as e:
                status = {"status": "error", "error": str(e)}
            (cached / "done.json").write_text(json.dumps(status), encoding="utf-8")
        else:
            self.hits += 1
        status = json.loads((cached / "done.json").read_text(encoding="utf-8"))
        if status["status"] == "no_music":
            raise EngineNoMusic(status["error"])
        if status["status"] == "error":
            raise EngineError(status["error"])
        output = out_dir / f"{image.stem}.musicxml"
        shutil.copyfile(cached / "page.musicxml", output)
        if (cached / "page.txt").exists():
            shutil.copyfile(cached / "page.txt", output.with_suffix(".txt"))
        return output


def item_sources(item: dict) -> list[Path]:
    return [DATA / s for s in item.get("sources", [item.get("source")])]


def reference_measures(truth: dict) -> list:
    name = truth["reference"]
    score = load_score(REFERENCE / f"{name}.musicxml")
    if "page" in truth:
        layout = json.loads((REFERENCE / f"{name}.pages.json").read_text(encoding="utf-8"))
        entry = layout[truth["page"] - 1]
        score = slice_score(score, entry["firstMeasure"], entry["measureCount"])
    return measures_from_score(score)


def run_item(item: dict, engine: CachedEngine, out_dir: Path) -> dict:
    job_dir = out_dir / item["id"]
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)
    started = time.perf_counter()
    try:
        output = run_pipeline(item_sources(item), job_dir, engine, min_ok_ratio=MIN_OK_RATIO)
    except OmrFailure as e:
        return {"id": item["id"], "kind": item["kind"], "failed": f"{e.code}: {e}"}
    report = output.report
    xml = output.music_xml.read_text(encoding="utf-8")
    reasons = Counter(r for m in report.suspicious_measures for r in m.reasons)
    row = {
        "id": item["id"],
        "kind": item["kind"],
        "seconds": round(time.perf_counter() - started, 1),
        "pages": len(output.pages),
        "measures": report.measure_count,
        "ok": report.ok_measure_count,
        "okRatio": report.ok_ratio,
        "reasons": dict(reasons),
        "timeSignature": report.time_signature,
        "meterChanges": [f"{c.number}:{c.time_signature}" for c in report.time_signature_changes],
        "keyFifths": report.key_fifths,
        "tempoText": report.tempo_text,
        "ties": len(re.findall(r'<tie type="start"', xml)),
        "slurs": len(re.findall(r'<slur [^>]*type="start"', xml)),
        "rerecognized": report.rerecognized_measures,
    }
    if isinstance(item["truth"], dict):
        result = compare(
            reference_measures(item["truth"]),
            load_measures(output.music_xml),
            flagged_result={m.index for m in report.suspicious_measures},
        )
        row["truth"] = {
            "measures": result.gt_measures,
            "correct": result.correct,
            "flagged": result.flagged,
            "silent": result.silent_errors + result.extra_measures,
            "tieOnly": result.tie_only_errors,
        }
    return row


def pct(part: int, total: int) -> str:
    return f"{part / total * 100:.0f}%" if total else "—"


def table(rows: list[dict], base: dict[str, dict] | None) -> str:
    lines = [
        f"{'пьеса':22} {'тактов':>6} {'норм.':>6} {'было':>6}  {'эталон: верно/помеч./тихие':28} "
        f"{'лиги т/с':9} размер, смены, тональность, темп"
    ]
    for row in rows:
        if "failed" in row:
            lines.append(f"{row['id']:22} СБОЙ {row['failed']}")
            continue
        old = (base or {}).get(row["id"])
        was = f"{old['okRatio'] * 100:.0f}%" if old and "okRatio" in old else ""
        truth = row.get("truth")
        truth_text = (
            f"{pct(truth['correct'], truth['measures'])}/{pct(truth['flagged'], truth['measures'])}"
            f"/{pct(truth['silent'], truth['measures'])} из {truth['measures']}"
            if truth
            else ""
        )
        lines.append(
            f"{row['id']:22} {row['measures']:>6} {row['okRatio'] * 100:>5.0f}% {was:>6}  "
            f"{truth_text:28} {row['ties']:>3}/{row['slurs']:<5} "
            f"{row['timeSignature']} {','.join(row['meterChanges']) or '-'} "
            f"K{row['keyFifths']} {row['tempoText']!r}"
        )
        lines.append(f"{'':22} причины: {row['reasons'] or '—'}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="имя замера, например base")
    parser.add_argument("--only", default="*", help="glob по id пьесы через запятую")
    parser.add_argument("--compare", help="метка прошлого замера для сравнения")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    manifest = yaml.safe_load((BENCH / "dataset.yaml").read_text(encoding="utf-8"))
    items = [
        i for i in manifest["items"] if any(fnmatch.fnmatch(i["id"], p) for p in args.only.split(","))
    ]
    out_dir = OUT / "pipeline" / args.label
    summary_path = out_dir / "summary.json"
    previous = (
        {r["id"]: r for r in json.loads(summary_path.read_text(encoding="utf-8"))}
        if summary_path.exists()
        else {}
    )
    engine = CachedEngine(ENGINES["homr"])
    rows = []
    for item in items:
        row = run_item(item, engine, out_dir)
        print(f"{item['id']:22} {row.get('seconds', 0):6.1f} с", flush=True)
        rows.append(row)
    # Частичный прогон (--only) дополняет прошлый замер с той же меткой.
    merged = {**previous, **{r["id"]: r for r in rows}}
    summary_path.write_text(
        json.dumps(list(merged.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    base = None
    if args.compare:
        base_path = OUT / "pipeline" / args.compare / "summary.json"
        base = {r["id"]: r for r in json.loads(base_path.read_text(encoding="utf-8"))}
    print(f"\nhomr: из кэша {engine.hits}, запусков {engine.misses}\n")
    print(table(list(merged.values()), base))


if __name__ == "__main__":
    main()
