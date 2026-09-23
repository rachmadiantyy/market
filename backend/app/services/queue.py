import json
from uuid import uuid4

from app.core.redis import get_redis

DEFAULT_QUEUE = "affiliate:jobs"


async def enqueue(queue: str, task: str, payload: dict | None = None) -> str:
    """Push a job onto a Redis list. Returns the generated job id."""
    job_id = str(uuid4())
    message = json.dumps(
        {"id": job_id, "task": task, "payload": payload or {}}
    )
    await get_redis().lpush(f"{DEFAULT_QUEUE}:{queue}", message)
    return job_id


async def dequeue(queue: str, timeout: int = 5) -> dict | None:
    """Blocking pop from a Redis list. Returns None on timeout."""
    result = await get_redis().brpop(f"{DEFAULT_QUEUE}:{queue}", timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)


async def queue_depth(queue: str) -> int:
    return int(await get_redis().llen(f"{DEFAULT_QUEUE}:{queue}"))
