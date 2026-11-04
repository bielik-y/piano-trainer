import { HttpException, HttpStatus } from '@nestjs/common';
import type { ApiError, ApiErrorCode } from '@piano/contracts';

/** Ошибка запроса в формате контракта: тело ответа — `{code, message}`. */
export class ApiException extends HttpException {
  constructor(status: HttpStatus, code: ApiErrorCode, message: string) {
    const body: ApiError = { code, message };
    super(body, status);
  }
}

export const notFound = (message = 'Задача не найдена') =>
  new ApiException(HttpStatus.NOT_FOUND, 'not_found', message);
