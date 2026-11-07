"""Настройки воркера из переменных окружения (одни и те же имена у API, см. apps/api/src/config.ts)."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# src/omr_worker/config.py → корень репозитория
REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _default_homr() -> Path:
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    exe = "homr.exe" if sys.platform == "win32" else "homr"
    return SERVICE_ROOT / "bench" / "envs" / "homr" / scripts / exe


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    homr_exe: Path
    min_ok_ratio: float
    max_pdf_pages: int
    raster_dpi: int
    page_timeout_s: int
    poll_interval_s: float

    @property
    def db_path(self) -> Path:
        return self.data_dir / "omr.sqlite"

    def job_dir(self, job_id: str) -> Path:
        return self.data_dir / "jobs" / job_id


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        data_dir=Path(env.get("OMR_DATA_DIR", REPO_ROOT / ".data" / "omr")).resolve(),
        homr_exe=Path(env.get("OMR_HOMR_EXE", _default_homr())),
        min_ok_ratio=float(env.get("OMR_MIN_OK_RATIO", "0.4")),
        max_pdf_pages=int(env.get("OMR_MAX_PDF_PAGES", "20")),
        raster_dpi=int(env.get("OMR_RASTER_DPI", "300")),
        page_timeout_s=int(env.get("OMR_PAGE_TIMEOUT_S", "600")),
        poll_interval_s=float(env.get("OMR_POLL_INTERVAL_S", "1")),
    )
