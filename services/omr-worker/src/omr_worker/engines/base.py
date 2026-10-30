"""Абстракция движка распознавания: oemer, Audiveris и т. п. См. docs/ARCHITECTURE.md §7."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OmrResult:
    music_xml: str


class OmrEngine(Protocol):
    name: str

    def recognize(self, pages: list[Path]) -> OmrResult: ...
