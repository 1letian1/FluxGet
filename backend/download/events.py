"""In-process event bus used to broadcast persisted task changes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DownloadEvent:
    type: str
    data: dict[str, Any]
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "occurred_at": self.occurred_at}


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[DownloadEvent]] = set()

    def subscribe(self, maxsize: int = 256) -> asyncio.Queue[DownloadEvent]:
        queue: asyncio.Queue[DownloadEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[DownloadEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = DownloadEvent(event_type, data, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
