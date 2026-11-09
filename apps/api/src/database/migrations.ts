/**
 * Миграции баз, файлы из packages/contracts/sql. Порядок важен, уже применённые не менять.
 * omr.sqlite общая с воркером (services/omr-worker), поэтому его тесты применяют те же файлы.
 */
export const OMR_MIGRATIONS = ['omr_001_jobs.sql', 'omr_002_device_options.sql'] as const;

export const APP_MIGRATIONS = ['app_001_devices_pieces.sql'] as const;
