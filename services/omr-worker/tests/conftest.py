import pytest

from omr_worker import metadata


@pytest.fixture(autouse=True)
def no_real_ocr(monkeypatch):
    """Модель OCR тяжёлая и скачивается при первом запуске; тесты её не трогают."""
    monkeypatch.setattr(metadata, "_run_ocr", lambda picture: [])
