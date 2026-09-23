"""Redis-queue worker loop.

Handlers live in app.workers.handlers; this module only owns the consume loop
so failures can never crash the worker process.
"""

import asyncio

from app.core.logging import get_logger
from app.services import queue
from app.workers.handlers import dispatch

logger = get_logger(__name__)

IDLE_LOG_EVERY = 60


async def main() -> None:
    logger.info("Worker started, listening on queue 'default'")
    idle_cycles = 0
    while True:
        try:
            job = await queue.dequeue("default", timeout=5)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to read from queue; retrying")
            await asyncio.sleep(1)
            continue

        if job is None:
            idle_cycles += 1
            if idle_cycles % IDLE_LOG_EVERY == 0:
                logger.info("Worker idle")
            continue

        idle_cycles = 0
        try:
            outcome = await dispatch(job)
            logger.debug("Job %s -> %s", job.get("id"), outcome)
        except Exception:  # noqa: BLE001
            # A handler must never take down the worker.
            logger.exception("Unhandled error processing job %s", job.get("id"))


if __name__ == "__main__":
    asyncio.run(main())
