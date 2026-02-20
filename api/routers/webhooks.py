import json
from fastapi import APIRouter, Request, status, HTTPException
from core.logger import logger
from worker.queue_manager import event_queue


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/{provider_name}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a raw status webhook payload",
    response_description="Payload accepted and queued for processing.",
)
async def receive_webhook(provider_name: str, request: Request) -> dict:

    raw_bytes: bytes = await request.body()

    # Decode JSON
    try:
        payload: dict = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        logger.warning(f"[{provider_name}] Received non-JSON body: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request body must be valid JSON. Parse error: {exc}",
        )
    
    # Enqueue the payload for processing by the background worker.
    queue_item = {
        "provider": provider_name.lower(),
        "payload":  payload,
    }
    await event_queue.enqueue(queue_item)

    logger.info(
        f"[{provider_name}] Payload enqueued. "
        f"Queue depth: {event_queue.qsize()} item(s)."
    )

    # Return 202 Accepted immediately – the caller is not blocked waiting for processing to complete.
    return {
        "accepted": True,
        "provider": provider_name,
        "queued_items": event_queue.qsize(),
    }