from typing import Any

from adapters.base import BaseAdapter, NormalizedEvent
from adapters.openai_adapter import OpenAIAdapter
from adapters.discord_adapter import DiscordAdapter
from adapters.apple_adapter import AppleAdapter
from core.logger import logger
from worker.queue_manager import event_queue



ADAPTER_REGISTRY: dict[str, BaseAdapter] = {
    "openai":  OpenAIAdapter(),
    "discord": DiscordAdapter(),
    "apple":   AppleAdapter(),
}

def _log_event(event: NormalizedEvent) -> None:
    """Log the event in a structured format for easy parsing and debugging."""

    logger.info({
        "product":   event.product,
        "status":    event.status,
        "timestamp": event.timestamp,
    })


async def _process_item(item: dict[str, Any]) -> None:
    """Process a single item from the queue: normalize it and log the result."""

    provider_name: str  = item.get("provider", "unknown").lower()
    payload: dict       = item.get("payload", {})

    adapter = ADAPTER_REGISTRY.get(provider_name)

    if adapter is None:
        logger.warning(
            f"No adapter registered for provider '{provider_name}'. "
            f"Dropping item. Register an adapter in worker/tasks.py to handle it."
        )
        return
    event: NormalizedEvent = adapter.parse(payload)
    _log_event(event)


async def start_worker() -> None:
    """Main worker loop that continuously processes events from the queue."""

    logger.info("Worker started, waiting for events...")

    while True:
        item: dict[str, Any] = await event_queue.dequeue()
        
        try:
            await _process_item(item)
        except Exception as exc:
            # Log the exception but DO NOT re-raise – the worker must keep running.
            logger.exception(
                f"Unhandled error while processing item from provider "
                f"'{item.get('provider', 'unknown')}': {exc}"
            )
        finally:
            event_queue.task_done()