import asyncio
from typing import Any

class QueueManager:
    """A simple in-memory async queue manager for demonstration purposes."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, item: dict[str, Any]) -> None:
        """Add an item to the queue."""
        await self._queue.put(item)

    async def dequeue(self) -> dict[str, Any]:
        """Remove and return an item from the queue. Waits if the queue is empty."""
        return await self._queue.get()
    
    def task_done(self) -> None:
        """Indicate that a formerly enqueued task is complete."""
        self._queue.task_done()

    def qsize(self) -> int:
        """Return the approximate size of the queue."""
        return self._queue.qsize()
    

event_queue: QueueManager = QueueManager()