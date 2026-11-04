/**
 * Очередь распознавания. На сервере — BullMQ (Redis): enqueue кладёт jobId в очередь «omr».
 * Локально очередь — сама таблица omr_jobs: воркер забирает записи со статусом queued,
 * поэтому SqliteJobQueue ничего не делает.
 */
export abstract class JobQueue {
  abstract enqueue(jobId: string): Promise<void>;
}

export class SqliteJobQueue extends JobQueue {
  async enqueue(_jobId: string): Promise<void> {
    // Запись уже создана со статусом queued — воркер увидит её при следующем опросе.
  }
}
