import asyncio
import sys
from datetime import datetime
# from core.logger import logger

import httpx
from producers.config import GATEWAY_WEBHOOK_BASE_URL

DISCORD_STATUS_URL  = "https://discordstatus.com/api/v2/status.json"
GATEWAY_WEBHOOK_URL = f"{GATEWAY_WEBHOOK_BASE_URL}/webhooks/discord"
POLL_INTERVAL_SECS  = 60
REQUEST_TIMEOUT     = 15.0
MAX_CONSECUTIVE_ERRORS = 5

def _log(msg: str) -> None:
    """Simple prefixed stdout logger for the standalone poller."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [discord_poller] {msg}", flush=True)


async def poll_discord_status() -> None:
    """
    Main polling loop.  Runs indefinitely until cancelled or too many errors.
    """
    # Conditional-request cache.  Empty strings mean "first request ever".
    last_etag: str          = ""
    last_modified: str      = ""
    consecutive_errors: int = 0

    _log(f"Poller started. Fetching {DISCORD_STATUS_URL} every {POLL_INTERVAL_SECS}s.")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        while True:
            try:
                headers: dict[str, str] = {
                    "Accept":     "application/json",
                    "User-Agent": "StatusPageTracker/1.0",
                }
                if last_etag:
                    headers["If-None-Match"] = last_etag
                if last_modified:
                    headers["If-Modified-Since"] = last_modified

                _log("Sending GET request…")
                response = await client.get(DISCORD_STATUS_URL, headers=headers)

                if response.status_code == 304:
                    _log("304 Not Modified - no changes detected, skipping.")

                elif response.status_code == 200:
                    # Cache new conditional-request tokens.
                    last_etag     = response.headers.get("etag", last_etag)
                    last_modified = response.headers.get("last-modified", last_modified)

                    payload = response.json()
                    # logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++")
                    # logger.info(payload)
                    # logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++")
                    _log(
                        f"200 OK - change detected. "
                        f"Indicator: {payload.get('status', {}).get('indicator', 'unknown')}. "
                        f"Forwarding to gateway…"
                    )

                    # POST the raw JSON body to the ingestion gateway.
                    forward_resp = await client.post(
                        GATEWAY_WEBHOOK_URL,
                        content=response.content,         # raw bytes – no re-encoding
                        headers={"Content-Type": "application/json"},
                    )
                    _log(f"Gateway response: HTTP {forward_resp.status_code}")
                    forward_resp.raise_for_status()

                else:
                    _log(f"Unexpected HTTP {response.status_code} - skipping this cycle.")

                consecutive_errors = 0  # Reset error counter on any successful cycle.

            except httpx.ConnectError:
                consecutive_errors += 1
                _log(
                    f"Connection error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}). "
                    f"Is the gateway running at {GATEWAY_WEBHOOK_URL}?"
                )
            except httpx.TimeoutException:
                consecutive_errors += 1
                _log(f"Request timed out ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")
            except Exception as exc:
                consecutive_errors += 1
                _log(f"Unexpected error: {exc} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                _log(f"Too many consecutive errors ({MAX_CONSECUTIVE_ERRORS}). Stopping poller.")
                sys.exit(1)

            # Wait before the next poll.
            _log(f"Sleeping {POLL_INTERVAL_SECS}s until next poll…")
            await asyncio.sleep(POLL_INTERVAL_SECS)

if __name__ == "__main__":
    try:
        asyncio.run(poll_discord_status())
    except KeyboardInterrupt:
        _log("Poller stopped by user.")