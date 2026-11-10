-- Миграция 2: данные для экранов библиотеки и произведения (макет в docs/DESIGN.md).
-- suspicious_measures — SuspiciousMeasure[] из отчёта OMR: такт, страница, причины, подробности.
-- time_signature_changes — TimeSignatureChange[]: смены размера посреди пьесы.
-- hue — оттенок сферы-обложки 0–359, переходит от задачи распознавания.
-- opened_at — первое открытие пьесы; пока NULL, у карточки тег «Новое».
ALTER TABLE pieces ADD COLUMN suspicious_measures TEXT NOT NULL DEFAULT '[]';
ALTER TABLE pieces ADD COLUMN time_signature_changes TEXT NOT NULL DEFAULT '[]';
ALTER TABLE pieces ADD COLUMN hue INTEGER NOT NULL DEFAULT 210;
ALTER TABLE pieces ADD COLUMN opened_at TEXT;
