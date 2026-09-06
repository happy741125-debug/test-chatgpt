from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import redis


@dataclass(frozen=True)
class QueueMessage:
    job_id: str


class JobQueue(Protocol):
    def publish(self, job_id: str) -> None: ...

    def pop(self, timeout_seconds: int = 1) -> QueueMessage | None: ...

    def schedule_retry(self, job_id: str, available_at: float) -> None: ...

    def promote_due_retries(self) -> int: ...

    def dead_letter(self, job_id: str, error: str) -> None: ...

    def ping(self) -> bool: ...


class RedisJobQueue:
    def __init__(
        self,
        url: str,
        *,
        queue_key: str,
        retry_key: str,
        dlq_key: str,
    ) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.queue_key = queue_key
        self.retry_key = retry_key
        self.dlq_key = dlq_key

    def publish(self, job_id: str) -> None:
        self.client.rpush(self.queue_key, json.dumps({"job_id": job_id}))

    def pop(self, timeout_seconds: int = 1) -> QueueMessage | None:
        self.promote_due_retries()
        item = self.client.blpop(self.queue_key, timeout=timeout_seconds)
        if item is None:
            return None
        payload = json.loads(item[1])
        return QueueMessage(job_id=str(payload["job_id"]))

    def schedule_retry(self, job_id: str, available_at: float) -> None:
        self.client.zadd(self.retry_key, {json.dumps({"job_id": job_id}): available_at})

    def promote_due_retries(self) -> int:
        now = time.time()
        items = self.client.zrangebyscore(self.retry_key, "-inf", now)
        promoted = 0
        for item in items:
            if self.client.zrem(self.retry_key, item):
                self.client.rpush(self.queue_key, item)
                promoted += 1
        return promoted

    def dead_letter(self, job_id: str, error: str) -> None:
        self.client.rpush(
            self.dlq_key,
            json.dumps({"job_id": job_id, "error": error}, ensure_ascii=False),
        )

    def ping(self) -> bool:
        return bool(self.client.ping())


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.ready: list[QueueMessage] = []
        self.retries: list[tuple[float, QueueMessage]] = []
        self.dead_letters: list[dict[str, str]] = []

    def publish(self, job_id: str) -> None:
        self.ready.append(QueueMessage(job_id=job_id))

    def pop(self, timeout_seconds: int = 1) -> QueueMessage | None:
        del timeout_seconds
        self.promote_due_retries()
        if not self.ready:
            return None
        return self.ready.pop(0)

    def schedule_retry(self, job_id: str, available_at: float) -> None:
        self.retries.append((available_at, QueueMessage(job_id=job_id)))

    def promote_due_retries(self) -> int:
        now = time.time()
        due = [item for item in self.retries if item[0] <= now]
        self.retries = [item for item in self.retries if item[0] > now]
        self.ready.extend(message for _, message in sorted(due, key=lambda item: item[0]))
        return len(due)

    def dead_letter(self, job_id: str, error: str) -> None:
        self.dead_letters.append({"job_id": job_id, "error": error})

    def ping(self) -> bool:
        return True
