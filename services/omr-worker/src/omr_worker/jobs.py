"""Очередь задач в SQLite (локальный режим, ARCHITECTURE §7.1.1).

Таблицу `omr_jobs` создаёт API (packages/contracts/sql/omr_0*.sql). Воркер берёт самую старую
задачу `queued`, атомарно переводит её в `processing` и пишет в ту же запись прогресс и результат.
Все обновления идут только при status = 'processing': если API успел отменить задачу,
воркер её не перезапишет.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .merge import parse_time_signature
from .models import ErrorCode, PageInfo, Progress, Report


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    source_paths: list[str]  # относительно папки задачи
    # Размер из OmrJobOptions.timeSignature; None — определить по нотам (auto).
    time_signature: tuple[int, int] | None = None


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA busy_timeout = 10000")

    def close(self) -> None:
        self.db.close()

    def table_exists(self) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'omr_jobs'"
        ).fetchone()
        return row is not None

    def fail_interrupted(self) -> int:
        """Задачи, оставшиеся в работе после падения воркера, завершаются ошибкой."""
        now = now_iso()
        cursor = self.db.execute(
            """UPDATE omr_jobs SET status = 'failed', error_code = 'interrupted',
                   error_message = 'Воркер перезапустился во время распознавания, загрузите файл ещё раз',
                   finished_at = ?, updated_at = ?, revision = revision + 1
               WHERE status = 'processing'""",
            (now, now),
        )
        return cursor.rowcount

    def claim(self) -> ClaimedJob | None:
        now = now_iso()
        row = self.db.execute(
            """UPDATE omr_jobs SET status = 'processing', started_at = ?, updated_at = ?,
                   revision = revision + 1
               WHERE id = (SELECT id FROM omr_jobs WHERE status = 'queued'
                           ORDER BY created_at, id LIMIT 1)
                 AND status = 'queued'
               RETURNING id, source_files, options""",
            (now, now),
        ).fetchone()
        if row is None:
            return None
        files = json.loads(row["source_files"])
        options = json.loads(row["options"]) if row["options"] else {}
        return ClaimedJob(
            id=row["id"],
            source_paths=[f["path"] for f in files],
            time_signature=parse_time_signature(options.get("timeSignature")),
        )

    def is_cancel_requested(self, job_id: str) -> bool:
        row = self.db.execute(
            "SELECT cancel_requested, status FROM omr_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row is None or bool(row["cancel_requested"]) or row["status"] != "processing"

    def update_progress(self, job_id: str, progress: Progress, pages: list[PageInfo]) -> None:
        self.db.execute(
            """UPDATE omr_jobs SET progress = ?, pages = ?, updated_at = ?, revision = revision + 1
               WHERE id = ? AND status = 'processing'""",
            (_json(progress.dump()), _json([p.dump() for p in pages]), now_iso(), job_id),
        )

    def finish(
        self,
        job_id: str,
        report: Report,
        pages: list[PageInfo],
        error: tuple[ErrorCode, str] | None = None,
    ) -> None:
        """done, либо failed с результатом (low_quality: файл всё равно можно скачать)."""
        self._close(
            job_id,
            status="failed" if error else "done",
            pages=pages,
            result=report.dump(),
            error=error,
        )

    def fail(
        self, job_id: str, code: ErrorCode, message: str, pages: list[PageInfo] | None
    ) -> None:
        self._close(job_id, status="failed", pages=pages, result=None, error=(code, message))

    def mark_cancelled(self, job_id: str, pages: list[PageInfo] | None) -> None:
        self._close(job_id, status="cancelled", pages=pages, result=None, error=None)

    def _close(
        self,
        job_id: str,
        *,
        status: str,
        pages: list[PageInfo] | None,
        result: dict | None,
        error: tuple[str, str] | None,
    ) -> None:
        now = now_iso()
        progress = None
        if status == "done" or (error and error[0] == "low_quality"):
            count = len(pages or [])
            progress = _json(
                Progress(stage="validating", page_count=count, percent=100, eta_seconds=0).dump()
            )
        self.db.execute(
            f"""UPDATE omr_jobs SET status = ?, result = ?, error_code = ?, error_message = ?,
                   pages = COALESCE(?, pages), {"progress = ?," if progress else ""}
                   finished_at = ?, updated_at = ?, revision = revision + 1
               WHERE id = ? AND status = 'processing'""",
            (
                status,
                _json(result) if result is not None else None,
                error[0] if error else None,
                error[1] if error else None,
                _json([p.dump() for p in pages]) if pages is not None else None,
                *([progress] if progress else []),
                now,
                now,
                job_id,
            ),
        )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)
