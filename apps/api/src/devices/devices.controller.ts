import { Controller, HttpCode, HttpStatus, Inject, Post } from '@nestjs/common';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import type { DeviceRegistration } from '@piano/contracts';
import { schemaRef } from '../swagger.js';
import { DevicesService } from './devices.service.js';

@ApiTags('devices')
@Controller('devices')
export class DevicesController {
  constructor(@Inject(DevicesService) private readonly devices: DevicesService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({
    summary: 'Зарегистрировать устройство',
    description:
      'Выдаёт анонимный токен. Приложение получает его при первом запуске и хранит в ' +
      'защищённом хранилище; задачи распознавания и пьесы принадлежат устройству. Токен ' +
      'показывается только здесь. В Swagger: скопируйте token, нажмите **Authorize** и ' +
      'вставьте его.',
  })
  @ApiResponse({ status: 201, schema: schemaRef('DeviceRegistration') })
  register(): DeviceRegistration {
    return this.devices.register();
  }
}
