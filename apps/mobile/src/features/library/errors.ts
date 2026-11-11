import { RequestError } from '@/services/api/client';

/** Текст ошибки запроса для тоста. */
export function requestErrorText(error: unknown): string {
  if (!(error instanceof RequestError)) return 'Что-то пошло не так. Попробуйте ещё раз';
  switch (error.code) {
    case 'network':
      return 'Нет связи с сервером';
    case 'file_too_large':
      return 'Файл больше 25 МБ';
    case 'too_many_files':
      return 'Можно не больше 10 фото';
    case 'unsupported_file_type':
      return 'Подходят только PDF и фото';
    case 'mixed_sources':
      return 'Выберите один PDF или только фото';
    case 'no_files':
      return 'Файлы не выбраны';
    case 'not_found':
      return 'Произведение не найдено';
    default:
      return error.message || 'Ошибка сервера';
  }
}
