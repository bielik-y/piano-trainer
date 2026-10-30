import { Controller, Get, NotImplementedException, Param, Post } from '@nestjs/common';
import type { CreateOmrJobResponse, OmrJob } from '@piano/contracts';

@Controller('omr/jobs')
export class OmrController {
  @Post()
  create(): CreateOmrJobResponse {
    throw new NotImplementedException();
  }

  @Post(':id/submit')
  submit(@Param('id') _id: string): OmrJob {
    throw new NotImplementedException();
  }

  @Get(':id')
  get(@Param('id') _id: string): OmrJob {
    throw new NotImplementedException();
  }
}
