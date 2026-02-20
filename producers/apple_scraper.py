import asyncio
import hashlib
import json
import sys
from datetime import datetime

import httpx
from core.logger import logger
from producers.config import GATEWAY_WEBHOOK_BASE_URL


APPLE_STATUS_URL    = "https://www.apple.com/support/systemstatus/data/system_status_en_US.js"
GATEWAY_WEBHOOK_URL = f"{GATEWAY_WEBHOOK_BASE_URL}/webhooks/apple"
POLL_INTERVAL_SECS  = 120
REQUEST_TIMEOUT     = 20.0
MAX_CONSECUTIVE_ERRORS = 5


def _extract_json(text: str) -> dict | None:
    """Parse the response as plain JSON, or unwrap JSONP if present."""
    # Try plain JSON first.
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back to JSONP-style: callback({...});
    start = text.find("(")
    end = text.rfind(")")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start + 1 : end])
        except json.JSONDecodeError:
            return None
    return None

def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [apple_scraper] {msg}", flush=True)


def _md5(data: bytes) -> str:
    """Return the hex MD5 hash of `data` for change detection."""
    return hashlib.md5(data).hexdigest()

async def scrape_apple_status() -> None:
    """Main scraping loop.  Runs indefinitely until cancelled."""

    last_hash: str      = ""   # MD5 of the last-seen HTML body.
    consecutive_errors  = 0

    _log(f"Scraper started. Fetching {APPLE_STATUS_URL} every {POLL_INTERVAL_SECS}s.")

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={
            # Mimic a real browser so Apple's CDN doesn't block us.
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
        },
    ) as client:
        while True:
            try:
                _log("Fetching Apple status data…")
                response = await client.get(APPLE_STATUS_URL)
                response.raise_for_status()

                # Always extract and log the JSON (for development)
                data = _extract_json(response.text)
                if data:
                    logger.info(f"[apple_scraper] Extracted JSON:\n{json.dumps(data, indent=2)}")
                else:
                    logger.warning("[apple_scraper] Could not parse JSON from response.")

                current_hash = _md5(response.content)

                if current_hash == last_hash:
                    _log("No change detected. Skipping.")
                else:
                    _log(f"Change detected (hash {last_hash[:8] or 'none'} → {current_hash[:8]}). Forwarding…")
                    last_hash = current_hash

                    envelope = json.dumps({
                        "provider": "apple",
                        "data":     data,
                    })

                    forward_resp = await client.post(
                        GATEWAY_WEBHOOK_URL,
                        content=envelope.encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    _log(f"Gateway response: HTTP {forward_resp.status_code}")
                    forward_resp.raise_for_status()

                consecutive_errors = 0

            except httpx.ConnectError:
                consecutive_errors += 1
                _log(
                    f"Connection error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}). "
                    f"Is the gateway running at {GATEWAY_WEBHOOK_URL}?"
                )
            except httpx.HTTPStatusError as exc:
                consecutive_errors += 1
                _log(f"HTTP error {exc.response.status_code}: {exc} ({consecutive_errors}).")
            except httpx.TimeoutException:
                consecutive_errors += 1
                _log(f"Request timed out ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")
            except Exception as exc:
                consecutive_errors += 1
                _log(f"Unexpected error: {exc} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                _log("Too many consecutive errors. Stopping scraper.")
                sys.exit(1)

            _log(f"Sleeping {POLL_INTERVAL_SECS}s until next scrape…")
            await asyncio.sleep(POLL_INTERVAL_SECS)


if __name__ == "__main__":
    try:
        asyncio.run(scrape_apple_status())
    except KeyboardInterrupt:
        _log("Scraper stopped by user.")
