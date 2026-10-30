import { Controller, Get } from '@nestjs/common';
import type { HealthResponse } from '@piano/contracts';

@Controller('health')
export class HealthController {
  @Get()
  check(): HealthResponse {
    return { status: 'ok', version: process.env.npm_package_version ?? 'dev' };
  }
}
