"""Движки OMR, которые запускаются отдельным процессом (CLI).

Каждый движок живёт в своём окружении: у oemer и homr конфликтуют зависимости, Audiveris — Java.
Путь к исполняемому файлу передаётся в конструктор, поэтому одни и те же адаптеры работают
и в бенчмарке (bench/envs/...), и в контейнере воркера.
"""

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .base import OmrResult


class EngineError(RuntimeError):
    pass


class EngineTimeout(EngineError):
    pass


class EngineCancelled(EngineError):
    pass


class EngineNoMusic(EngineError):
    """На странице нет нот (пустые станы, текст). Это не сбой: страница просто не даёт тактов."""


def kill_tree(process: subprocess.Popen) -> None:
    """Останавливает процесс вместе с дочерними: на Windows `homr.exe` из venv — лаунчер,
    распознавание идёт в дочернем python.exe, и `process.kill()` его не остановит."""
    import psutil

    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
    except psutil.Error:
        children = []
    for p in children:
        try:
            p.kill()
        except psutil.Error:
            pass
    process.kill()
    process.wait()


class CliEngine:
    name = "cli"
    # Строка в логе движка, означающая, что на странице нет нот.
    no_music_marker: str | None = None

    def __init__(self, executable: Path, timeout_s: int = 1800) -> None:
        self.executable = executable
        self.timeout_s = timeout_s

    def command(self, image: Path, out_dir: Path) -> list[str]:
        raise NotImplementedError

    def output_path(self, image: Path, out_dir: Path) -> Path:
        """Где движок оставляет MusicXML для страницы `image`."""
        return out_dir / f"{image.stem}.musicxml"

    def prepare(self, image: Path, out_dir: Path) -> Path:
        """Готовит вход; возвращает путь к картинке, которую получит движок."""
        return image

    def popen(self, image: Path, out_dir: Path) -> tuple[subprocess.Popen, Path]:
        """Запускает распознавание одной страницы. Возвращает процесс и путь будущего результата."""
        out_dir.mkdir(parents=True, exist_ok=True)
        image = self.prepare(image, out_dir)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONWARNINGS": "ignore"}
        log = (out_dir / f"{image.stem}.{self.name}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            self.command(image, out_dir), stdout=log, stderr=subprocess.STDOUT, env=env
        )
        return process, self.output_path(image, out_dir)

    def finalize(self, output: Path) -> Path:
        """Вызывается после завершения процесса; возвращает итоговый файл результата."""
        return output

    def recognize_page(
        self, image: Path, out_dir: Path, should_stop: Callable[[], bool] | None = None
    ) -> Path:
        """Распознаёт страницу. `should_stop` опрашивается каждые 0,5 с: True — остановить."""
        process, output = self.popen(image, out_dir)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                code = process.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                pass
            if should_stop is not None and should_stop():
                kill_tree(process)
                raise EngineCancelled(f"{self.name}: остановлено")
            if time.monotonic() > deadline:
                kill_tree(process)
                raise EngineTimeout(f"{self.name}: таймаут {self.timeout_s} с")
        output = self.finalize(output)
        if code != 0 or not output.exists():
            log = out_dir / f"{image.stem}.{self.name}.log"
            if self.no_music_marker and self.no_music_marker in log.read_text(
                encoding="utf-8", errors="replace"
            ):
                raise EngineNoMusic(f"{self.name}: на странице нет нот")
            raise EngineError(f"{self.name}: код выхода {code}, результата нет ({output.name})")
        return output

    def recognize(self, pages: list[Path]) -> OmrResult:
        if len(pages) != 1:
            # Склейка страниц в одну партитуру появится вместе с воркером (ROADMAP, фаза 7).
            raise NotImplementedError("пока распознаётся только одна страница")
        output = self.recognize_page(pages[0], pages[0].parent / f"{self.name}-out")
        return OmrResult(music_xml=_read_music_xml(output))


class AudiverisEngine(CliEngine):
    """`upscale` > 1 увеличивает картинку перед распознаванием: Audiveris отказывается от страниц,
    где расстояние между линейками нотоносца меньше ~10 px (сжатые фото из мессенджеров)."""

    name = "audiveris"

    def __init__(self, executable: Path, timeout_s: int = 1800, upscale: float = 1.0) -> None:
        super().__init__(executable, timeout_s)
        self.upscale = upscale
        if upscale != 1.0:
            self.name = f"audiveris-x{upscale:g}"

    def prepare(self, image: Path, out_dir: Path) -> Path:
        if self.upscale == 1.0:
            return image
        import cv2

        target = out_dir / f"{image.stem}.png"
        picture = cv2.imread(str(image))
        resized = cv2.resize(
            picture, None, fx=self.upscale, fy=self.upscale, interpolation=cv2.INTER_CUBIC
        )
        cv2.imwrite(str(target), resized)
        return target

    def command(self, image: Path, out_dir: Path) -> list[str]:
        return [
            str(self.executable),
            "-batch",
            "-export",
            "-output",
            str(out_dir),
            "--",
            str(image),
        ]

    def output_path(self, image: Path, out_dir: Path) -> Path:
        return out_dir / f"{image.stem}.mxl"

    def finalize(self, output: Path) -> Path:
        """Если Audiveris счёл страницу несколькими частями (`<stem>.mvt1.mxl`, `mvt2`…),
        склеивает их по порядку в `<stem>.musicxml`."""
        if output.exists():
            return output
        movements = sorted(
            output.parent.glob(f"{output.stem}.mvt*.mxl"),
            key=lambda p: int(p.suffixes[-2].removeprefix(".mvt")),
        )
        if not movements:
            return output
        merged = output.with_suffix(".musicxml")
        merged.write_text(
            _merge_movements([_read_music_xml(m) for m in movements]), encoding="utf-8"
        )
        return merged


class OemerEngine(CliEngine):
    name = "oemer"

    def command(self, image: Path, out_dir: Path) -> list[str]:
        return [str(self.executable), str(image), "-o", str(out_dir)]


class HomrEngine(CliEngine):
    """homr пишет результат рядом с картинкой, поэтому картинка копируется в out_dir."""

    name = "homr"
    no_music_marker = "No noteheads found"

    def version(self) -> str | None:
        """Версия homr из его окружения (dist-info рядом с исполняемым файлом)."""
        env = self.executable.parent.parent
        for info in [*env.glob("Lib/site-packages/homr-*.dist-info"),
                     *env.glob("lib/python*/site-packages/homr-*.dist-info")]:
            return info.name.removeprefix("homr-").removesuffix(".dist-info")
        return None

    def prepare(self, image: Path, out_dir: Path) -> Path:
        target = out_dir / image.name
        if target.resolve() != image.resolve():
            shutil.copyfile(image, target)
        return target

    def command(self, image: Path, out_dir: Path) -> list[str]:
        # Положение строк нужно для повторного распознавания проблемных строк (rerun.py).
        return [str(self.executable), str(image), "--write-staff-positions"]


def _merge_movements(documents: list[str]) -> str:
    """Склеивает partwise-MusicXML: такты каждой партии следующих частей дописываются
    в ту же по порядку партию первой части, номера тактов идут подряд."""
    from xml.etree import ElementTree as ET

    roots = [ET.fromstring(doc.encode("utf-8")) for doc in documents]
    base_parts = roots[0].findall("part")
    for root in roots[1:]:
        for base, part in zip(base_parts, root.findall("part")):
            base.extend(part.findall("measure"))
    for part in base_parts:
        for number, measure in enumerate(part.findall("measure"), start=1):
            measure.set("number", str(number))
    return ET.tostring(roots[0], encoding="unicode", xml_declaration=True)


def _read_music_xml(path: Path) -> str:
    if path.suffix == ".mxl":
        import zipfile

        with zipfile.ZipFile(path) as archive:
            # В .mxl корневой файл указан в META-INF/container.xml; у Audiveris он единственный .xml.
            name = next(n for n in archive.namelist() if n.endswith(".xml") and "/" not in n)
            return archive.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")
