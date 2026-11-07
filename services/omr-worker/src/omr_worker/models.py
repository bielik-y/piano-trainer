"""Данные задачи, которые воркер пишет в базу и в report.json.

Зеркало zod-схем из packages/contracts (OmrProgress, OmrPage, OmrReport): API проверяет их
при чтении, поэтому расхождение сразу видно. Поля в JSON — camelCase.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Stage = Literal["preprocessing", "recognizing", "merging", "validating"]
PageStatus = Literal["pending", "processing", "done", "failed"]
ErrorCode = Literal[
    "low_quality",
    "unreadable_file",
    "too_many_pages",
    "no_music_found",
    "engine_failed",
    "timeout",
    "interrupted",
]


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def dump(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class Progress(Model):
    stage: Stage
    page: int | None = None
    page_count: int
    percent: int
    eta_seconds: int | None = None


class PageInfo(Model):
    index: int  # с 1
    status: PageStatus = "pending"
    width: int | None = None
    height: int | None = None
    measure_count: int | None = None
    seconds: float | None = None
    error: str | None = None


class SuspiciousMeasure(Model):
    index: int  # с 0, по порядку в партитуре
    number: str  # номер такта в MusicXML
    page: int  # с 1
    reasons: list[str]


class EngineInfo(Model):
    name: str
    version: str | None = None


class Report(Model):
    measure_count: int
    ok_measure_count: int
    ok_ratio: float
    min_ok_ratio: float
    quality: Literal["ok", "low"]
    staff_count: int
    time_signature: str | None = None
    # engine — знак размера нашёл движок, inferred — вычислен по длинам тактов.
    time_signature_source: Literal["engine", "inferred"] | None = None
    key_fifths: int | None = None
    title: str | None = None
    composer: str | None = None
    tempo_text: str | None = None
    tempo_bpm: int | None = None
    # Такты, которые исправило повторное распознавание отдельной строки.
    rerecognized_measures: list[str] = []
    suspicious_measures: list[SuspiciousMeasure]
    engine: EngineInfo


class OmrFailure(Exception):
    """Задача завершается со статусом failed и этим кодом."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Cancelled(Exception):
    pass
