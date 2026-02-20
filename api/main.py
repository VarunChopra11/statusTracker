import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routers.webhooks import router as webhook_router
from core.logger import logger
from worker.tasks import start_worker

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Status Page Tracker…")

    worker_task = asyncio.create_task(start_worker(), name="status-worker")
    logger.info("Background worker task created.")

    yield

    logger.info("Shutting down - cancelling worker task…")
    worker_task.cancel()

    try:
        await worker_task
    except asyncio.CancelledError:
        logger.info("Worker task cancelled cleanly.")

app = FastAPI(
    title="Status Page Tracker",
    lifespan=lifespan
)

app.include_router(webhook_router)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.get("/wakeup")
async def wakeup():
    return {"status": "awake", "message": "This server is awake."}

@app.head("/wakeup")
async def wakeup_head():
    return

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


