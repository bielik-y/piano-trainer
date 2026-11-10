-- Миграция 3: оттенок сферы-обложки и скрытие задачи из библиотеки.
-- hue — 0–359, задаётся случайно при загрузке и переходит к пьесе из этой задачи (DESIGN.md).
--   У старых задач NULL: API вычисляет оттенок из id.
-- dismissed_at — карточка задачи убрана с экрана библиотеки: пьесу добавили или ошибку посмотрели.
ALTER TABLE omr_jobs ADD COLUMN hue INTEGER;
ALTER TABLE omr_jobs ADD COLUMN dismissed_at TEXT;
