"""Ручная сверка распознанных страниц без эталона: локальная веб-страница.

Слева оригинал, справа результат движка (Verovio, такты пронумерованы по порядку с 1).
Отмечаются неверные такты и число пропущенных; такты, которые и так исключит автопроверка,
помечены заранее. Отметки сохраняются в bench/data/manual/<engine>/<page>.json.

Запуск: uv run --group bench python -m bench.review [--engines homr,audiveris]
Затем открыть http://127.0.0.1:8765
"""

import argparse
import html
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import verovio

from bench.compare import flag_measures, load_measures
from bench.report import MANUAL, latest_runs, manual_context
from bench.run import BENCH, load_pages
from omr_worker.engines.cli import _read_music_xml

PORT = 8765
VEROVIO_OPTIONS = {
    "pageWidth": 2400,
    "scale": 40,
    "adjustPageHeight": True,
    "breaks": "auto",
    "mnumInterval": 1,
    "svgViewBox": True,
    "footer": "none",
    "header": "none",
}

STYLE = """
body { font: 15px system-ui, sans-serif; margin: 0; color: #1d1d1f; }
header { padding: 10px 16px; background: #f3f3f5; position: sticky; top: 0; z-index: 2;
         display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; }
.cols img, .cols svg { width: 100%; height: auto; border: 1px solid #ddd; background: #fff; }
.bars { display: flex; flex-wrap: wrap; gap: 6px; }
.bars label { border: 1px solid #ccc; border-radius: 6px; padding: 3px 7px; cursor: pointer; }
.bars label.flagged { background: #eee; color: #888; cursor: default; }
.bars input:checked + span { color: #c0392b; font-weight: 600; }
table { border-collapse: collapse; margin: 16px; } td, th { padding: 6px 12px; border-bottom: 1px solid #eee; }
.done { color: #2e7d32; } .todo { color: #c0392b; }
"""


def renumber(music_xml: str) -> str:
    """Номера тактов по порядку с 1 в каждой партии — чтобы совпадали с галочками."""
    out, counter = [], 0
    for chunk in re.split(r"(<part\s[^>]*>|<measure\s[^>]*>)", music_xml):
        if chunk.startswith(("<part ", "<part\t")):
            counter = 0
        elif chunk.startswith("<measure"):
            counter += 1
            chunk = re.sub(r'number="[^"]*"', f'number="{counter}"', chunk, count=1)
            chunk = re.sub(r'\s+implicit="yes"', "", chunk)
        out.append(chunk)
    return "".join(out)


def render(output: Path) -> str:
    tk = verovio.toolkit()
    tk.setOptions(VEROVIO_OPTIONS)
    if not tk.loadData(renumber(_read_music_xml(output))):
        return "<p>Verovio не смог открыть результат.</p>"
    return "".join(tk.renderToSVG(n) for n in range(1, tk.getPageCount() + 1))


class Handler(BaseHTTPRequestHandler):
    pages: ClassVar[dict] = {}
    runs: ClassVar[dict] = {}
    engines: ClassVar[list[str]] = []

    def send(self, body: bytes, content_type: str = "text/html; charset=utf-8", code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def items(self):
        for page in self.pages.values():
            if page.truth != "manual":
                continue
            for engine in self.engines:
                run = self.runs.get((engine, page.id))
                if run and run["ok"]:
                    yield page, engine, run

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self.index()
        if url.path == "/review":
            return self.review(query["page"], query["engine"])
        if url.path == "/image":
            image = self.pages[query["page"]].image
            kind = "image/png" if image.suffix == ".png" else "image/jpeg"
            return self.send(image.read_bytes(), kind)
        self.send(b"not found", "text/plain", 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        target = MANUAL / data["engine"] / f"{data['page']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        marks = {"wrong": sorted(data["wrong"]), "missing": int(data["missing"] or 0)}
        target.write_text(json.dumps(marks), encoding="utf-8")
        self.send(b'{"ok": true}', "application/json")

    def index(self):
        rows = []
        for page, engine, _ in self.items():
            done = (MANUAL / engine / f"{page.id}.json").exists()
            status = (
                '<span class="done">сверено</span>' if done else '<span class="todo">нет</span>'
            )
            rows.append(
                f'<tr><td><a href="/review?page={page.id}&engine={engine}">{page.id}</a></td>'
                f"<td>{engine}</td><td>{status}</td></tr>"
            )
        body = (
            f"<!doctype html><meta charset=utf-8><title>Сверка OMR</title><style>{STYLE}</style>"
            "<header><b>Ручная сверка распознавания</b></header>"
            "<table><tr><th>Страница</th><th>Движок</th><th>Статус</th></tr>"
            + "".join(rows)
            + "</table>"
        )
        self.send(body.encode("utf-8"))

    def review(self, page_id: str, engine: str):
        page = self.pages[page_id]
        output = BENCH / self.runs[(engine, page_id)]["output"]
        measures = load_measures(output)
        flagged = flag_measures(measures, *manual_context(engine, page, self.runs))
        saved_path = MANUAL / engine / f"{page_id}.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8")) if saved_path.exists() else {}
        wrong = set(saved.get("wrong", []))
        bars = []
        for i in range(len(measures)):
            if i in flagged:
                bars.append(
                    f'<label class="flagged" title="исключён автопроверкой">{i + 1} ✕</label>'
                )
            else:
                checked = " checked" if i in wrong else ""
                bars.append(
                    f"<label><input type=checkbox value={i}{checked}><span> {i + 1}</span></label>"
                )
        items = list(self.items())
        index = next(n for n, (p, e, _) in enumerate(items) if p.id == page_id and e == engine)
        next_link = (
            f"/review?page={items[index + 1][0].id}&engine={items[index + 1][1]}"
            if index + 1 < len(items)
            else "/"
        )
        body = f"""<!doctype html><meta charset=utf-8><title>{html.escape(page_id)} — {engine}</title>
<style>{STYLE}</style>
<header>
  <a href="/">← список</a>
  <b>{html.escape(page_id)}</b> · движок <b>{engine}</b> · {index + 1} из {len(items)}
  <span>Отметьте такты, где хоть одна нота неверна (высота, длительность, лишняя или пропущенная нота).
  Серые ✕ уже исключены автопроверкой.</span>
</header>
<div style="padding: 0 16px">
  <div class="bars">{"".join(bars)}</div>
  <p>Тактов оригинала, которых нет в результате совсем:
     <input id=missing type=number min=0 value="{saved.get("missing", 0)}" style="width:4em">
     <button id=save>Сохранить и дальше →</button> <span id=status></span></p>
</div>
<div class="cols">
  <div><h3>Оригинал</h3><img src="/image?page={page_id}"></div>
  <div><h3>Распознано ({len(measures)} тактов)</h3>{render(output)}</div>
</div>
<script>
document.getElementById('save').onclick = async () => {{
  const wrong = [...document.querySelectorAll('.bars input:checked')].map(i => +i.value);
  const missing = document.getElementById('missing').value;
  const r = await fetch('/save', {{method: 'POST', body: JSON.stringify(
      {{page: {json.dumps(page_id)}, engine: {json.dumps(engine)}, wrong, missing}})}});
  if (r.ok) location.href = {json.dumps(next_link)};
  else document.getElementById('status').textContent = 'Не сохранилось';
}};
</script>"""
        self.send(body.encode("utf-8"))

    def log_message(self, *args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engines", default="homr,audiveris")
    args = parser.parse_args()
    Handler.pages = {p.id: p for p in load_pages()}
    Handler.runs = latest_runs()
    Handler.engines = args.engines.split(",")
    print(f"Сверка: http://127.0.0.1:{PORT}  (Ctrl+C — остановить)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
