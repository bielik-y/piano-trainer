-- Миграция 2: владелец задачи и параметры распознавания.
-- device_id — устройство, создавшее задачу (devices.id в app.sqlite; другая база, поэтому без FK).
--   У задач, созданных до миграции, он NULL: их не видит ни одно устройство.
-- options — OmrJobOptions (JSON), например {"timeSignature":"3/4"}; NULL — всё по умолчанию.
ALTER TABLE omr_jobs ADD COLUMN device_id TEXT;
ALTER TABLE omr_jobs ADD COLUMN options TEXT;

CREATE INDEX IF NOT EXISTS omr_jobs_device_created ON omr_jobs (device_id, created_at);
