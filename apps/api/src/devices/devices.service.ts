import { Inject, Injectable } from '@nestjs/common';
import { createHash, randomBytes } from 'node:crypto';
import type { DeviceRegistration } from '@piano/contracts';
import { uuidv7 } from '../common/uuid.js';
import { DeviceRepository, type DeviceRecord } from './device-repository.js';

/** last_seen_at пишется не чаще раза в час, чтобы не писать в базу на каждый запрос. */
const TOUCH_INTERVAL_MS = 60 * 60 * 1000;

const TOKEN_PREFIX = 'pt_';

const hashToken = (token: string) => createHash('sha256').update(token).digest('hex');

@Injectable()
export class DevicesService {
  constructor(@Inject(DeviceRepository) private readonly devices: DeviceRepository) {}

  /** Новое анонимное устройство. Токен нигде не хранится, только его хеш. */
  register(): DeviceRegistration {
    const token = TOKEN_PREFIX + randomBytes(32).toString('base64url');
    const device = this.devices.insert(uuidv7(), hashToken(token), new Date().toISOString());
    return { deviceId: device.id, token };
  }

  /** Устройство по токену; null — токен неизвестен. */
  authenticate(token: string): DeviceRecord | null {
    if (!token.startsWith(TOKEN_PREFIX)) return null;
    const device = this.devices.findByTokenHash(hashToken(token));
    if (!device) return null;
    const now = Date.now();
    this.devices.touch(
      device.id,
      new Date(now).toISOString(),
      new Date(now - TOUCH_INTERVAL_MS).toISOString(),
    );
    return device;
  }
}
