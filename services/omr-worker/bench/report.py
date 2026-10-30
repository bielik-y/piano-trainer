"""Сводный отчёт бенчмарка OMR: bench/out/report.md.

Для страниц с точным эталоном метрики считаются автоматически (bench/compare.py).
Для страниц с ручной сверкой нужны отметки bench/data/manual/<engine>/<page>.json
({"wrong": [индексы тактов с 0], "missing": число пропущенных тактов}), их делает bench/review.py.

Запуск: uv run --group bench python -m bench.report [--no-ned]
"""

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import verovio

from bench.compare import (
    PageResult,
    compare,
    flag_measures,
    load_measures,
    load_score,
    measures_from_score,
    omr_ned,
    slice_score,
)
from bench.run import BENCH, DATA, OUT, RESULTS, Page, load_pages

MANUAL = DATA / "manual"
REFERENCE = DATA / "reference"
ENGINE_ORDER = ["homr", "audiveris", "audiveris-x2", "oemer"]
KIND_TITLE = {"pdf": "PDF", "photo": "Фото"}


@dataclass
class Row:
    engine: str
    page: Page
    run: dict
    result: PageResult | None = None
    ned: float | None = None
    verovio_ok: bool | None = None
    reviewed: bool = False


def latest_runs() -> dict[tuple[str, str], dict]:
    runs: dict[tuple[str, str], dict] = {}
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if line:
            run = json.loads(line)
            runs[(run["engine"], run["page"])] = run
    return runs


def verovio_loads(path: Path) -> bool:
    tk = verovio.toolkit()
    return bool(tk.loadFile(str(path))) and tk.getPageCount() > 0


def reference_slice(page: Page) -> tuple[str, int, int, bool, bool]:
    """(имя эталона, первый такт, число тактов, начало пьесы, конец пьесы)."""
    name = page.truth["reference"]
    page_no = page.page_no or page.truth["page"]
    layout = json.loads((REFERENCE / f"{name}.pages.json").read_text(encoding="utf-8"))
    entry = layout[page_no - 1]
    return name, entry["firstMeasure"], entry["measureCount"], page_no == 1, page_no == len(layout)


def manual_context(engine: str, page: Page, runs: dict) -> tuple[bool, bool, Fraction | None]:
    """Для страницы без эталона: (начало пьесы, конец пьесы, размер с первой страницы).

    Размер берётся из результата того же движка на первой странице той же пьесы — так его
    увидит приложение после склейки страниц."""
    if page.page_no is None:
        return True, True, None
    default = None
    if page.page_no > 1:
        first = runs.get((engine, f"{page.item_id}-p1"))
        if first and first["ok"]:
            default = next(
                (
                    m.expected_length
                    for m in load_measures(BENCH / first["output"])
                    if m.expected_length
                ),
                None,
            )
    return page.page_no == 1, page.page_no == page.page_count, default


def evaluate(row: Row, with_ned: bool, gt_cache: dict, runs: dict) -> None:
    output = BENCH / row.run["output"]
    row.verovio_ok = verovio_loads(output)
    score = load_score(output)
    measures = measures_from_score(score)

    if isinstance(row.page.truth, dict):
        name, first, count, start, end = reference_slice(row.page)
        if name not in gt_cache:
            gt_cache[name] = load_score(REFERENCE / f"{name}.musicxml")
        gt_score = slice_score(gt_cache[name], first, count)
        gt_measures = measures_from_score(gt_score)
        # Размер, действующий на этой странице по эталону (на странице он может быть не напечатан).
        row.result = compare(gt_measures, measures, start, end, gt_measures[0].expected_length)
        row.reviewed = True
        if with_ned:
            row.ned = omr_ned(gt_score, score)
        return

    # Ручная сверка: верные такты = не помеченные проверкой и не отмеченные человеком.
    flagged = flag_measures(measures, *manual_context(row.engine, row.page, runs))
    marks_path = MANUAL / row.engine / f"{row.page.id}.json"
    marks = json.loads(marks_path.read_text(encoding="utf-8")) if marks_path.exists() else None
    row.reviewed = marks is not None
    wrong = set(marks["wrong"]) if marks else set()
    missing = marks.get("missing", 0) if marks else 0
    silent = len(wrong - flagged) + missing
    row.result = PageResult(
        gt_measures=len(measures) + missing,
        result_measures=len(measures),
        correct=len(measures) - len(flagged) - len(wrong - flagged) if marks else 0,
        flagged=len(flagged),
        silent_errors=silent,
        extra_measures=0,
    )


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f} %"


def summary_table(rows: list[Row]) -> list[str]:
    groups: dict[tuple[str, str], dict[str, list[Row]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        truth = "эталон" if isinstance(row.page.truth, dict) else "ручная сверка"
        groups[(row.page.kind, truth)][row.engine].append(row)

    lines = [
        (
            "| Категория | Движок | Страниц (сбоев) | Тактов | Верные | Исключены проверкой | "
            "**Тихие ошибки** | из них только лиги | OMR-NED | Verovio | Время, с/стр (медиана) | "
            "Память, МБ (макс.) |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (kind, truth), by_engine in sorted(groups.items()):
        for engine in ENGINE_ORDER:
            engine_rows = by_engine.get(engine)
            if not engine_rows:
                continue
            ok = [r for r in engine_rows if r.result is not None]
            reviewed = [r for r in ok if r.reviewed]
            failures = len(engine_rows) - len(ok)
            # Упавший движок — вся страница «не распознана»: в метрики не входит, считается в сбоях.
            total = sum(r.result.gt_measures for r in reviewed)
            if reviewed and total:
                correct = sum(r.result.correct for r in reviewed) / total
                flagged = sum(r.result.flagged for r in reviewed) / total
                silent = (
                    sum(r.result.silent_errors + r.result.extra_measures for r in reviewed) / total
                )
                tie_only = sum(r.result.tie_only_errors for r in reviewed) / total
            else:
                correct = silent = tie_only = None
                flagged_total = sum(r.result.result_measures for r in ok)
                flagged = (
                    sum(r.result.flagged for r in ok) / flagged_total if flagged_total else None
                )
            neds = [r.ned for r in ok if r.ned is not None]
            seconds = [r.run["seconds"] for r in engine_rows if r.run["ok"]]
            memory = [r.run["peak_mb"] for r in engine_rows]
            not_reviewed = (
                "" if len(reviewed) == len(ok) else f" (сверено {len(reviewed)} из {len(ok)})"
            )
            lines.append(
                f"| {KIND_TITLE[kind]}, {truth} | {engine} | {len(engine_rows)} ({failures}) | "
                f"{total if reviewed else '—'}{not_reviewed} | {pct(correct)} | {pct(flagged)} | "
                f"**{pct(silent)}** | {pct(tie_only)} | {f'{statistics.mean(neds):.2f}' if neds else '—'} | "
                f"{sum(1 for r in ok if r.verovio_ok)}/{len(ok)} | "
                f"{f'{statistics.median(seconds):.0f}' if seconds else '—'} | {max(memory) if memory else '—'} |"
            )
    return lines


def pages_table(rows: list[Row]) -> list[str]:
    lines = [
        "| Страница | Движок | Тактов (результат/эталон) | Верные | Исключены | Тихие | NED | Время, с |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: (r.page.id, ENGINE_ORDER.index(r.engine))):
        if row.result is None:
            lines.append(
                f"| {row.page.id} | {row.engine} | сбой | | | | | {row.run['seconds']:.0f} |"
            )
            continue
        r = row.result
        gt = r.gt_measures if isinstance(row.page.truth, dict) else "?"
        silent = r.silent_errors + r.extra_measures if row.reviewed else "не сверено"
        lines.append(
            f"| {row.page.id} | {row.engine} | {r.result_measures}/{gt} | "
            f"{r.correct if row.reviewed else '—'} | {r.flagged} | {silent} | "
            f"{f'{row.ned:.2f}' if row.ned is not None else '—'} | {row.run['seconds']:.0f} |"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ned", action="store_true", help="не считать OMR-NED (медленно)")
    args = parser.parse_args()

    pages = {p.id: p for p in load_pages()}
    rows: list[Row] = []
    gt_cache: dict = {}
    runs = latest_runs()
    for (engine, page_id), run in runs.items():
        if page_id not in pages:
            continue
        row = Row(engine, pages[page_id], run)
        if run["ok"]:
            evaluate(row, not args.no_ned, gt_cache, runs)
        rows.append(row)

    report = [
        "# Бенчмарк OMR — сводка",
        "",
        "Тихие ошибки — такты с неверными нотами, которые автопроверка не поймала (плюс пропущенные",
        "и лишние такты), в % от тактов эталона. Это будущее ложное «сыграно неверно», главная метрика.",
        "Исключены проверкой — такты, которые не будут оцениваться в режиме игры.",
        "",
        *summary_table(rows),
        "",
        "## По страницам",
        "",
        *pages_table(rows),
        "",
    ]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(summary_table(rows)))


if __name__ == "__main__":
    main()
