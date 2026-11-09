import {
  type CanActivate,
  type ExecutionContext,
  HttpStatus,
  Inject,
  Injectable,
  createParamDecorator,
} from '@nestjs/common';
import type { FastifyRequest } from 'fastify';
import { ApiException } from '../common/api-exception.js';
import type { DeviceRecord } from './device-repository.js';
import { DevicesService } from './devices.service.js';

declare module 'fastify' {
  interface FastifyRequest {
    /** Устройство из токена; есть у запросов под DeviceGuard. */
    device?: DeviceRecord;
  }
}

const BEARER = /^Bearer\s+(\S+)$/i;

/** Пропускает запрос только с действующим токеном устройства (`Authorization: Bearer …`). */
@Injectable()
export class DeviceGuard implements CanActivate {
  constructor(@Inject(DevicesService) private readonly devices: DevicesService) {}

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<FastifyRequest>();
    const token = BEARER.exec(req.headers.authorization ?? '')?.[1];
    const device = token ? this.devices.authenticate(token) : null;
    if (!device) {
      throw new ApiException(
        HttpStatus.UNAUTHORIZED,
        'unauthorized',
        token
          ? 'Токен устройства не найден: получите новый через POST /v1/devices'
          : 'Нужен заголовок Authorization: Bearer <токен> из POST /v1/devices',
      );
    }
    req.device = device;
    return true;
  }
}

/** Устройство текущего запроса. Только в обработчиках под DeviceGuard. */
export const CurrentDevice = createParamDecorator((_: unknown, context: ExecutionContext) => {
  const device = context.switchToHttp().getRequest<FastifyRequest>().device;
  if (!device) throw new Error('CurrentDevice без DeviceGuard');
  return device;
});
