import asyncio
import hashlib
import json
import sys
from datetime import datetime

import httpx
from core.logger import logger
from producers.config import GATEWAY_WEBHOOK_BASE_URL

OPENAI_COMPONENTS_URL = "https://status.openai.com/api/v2/components.json"
OPENAI_INCIDENTS_URL  = "https://status.openai.com/api/v2/incidents.json"

GATEWAY_WEBHOOK_URL   = f"{GATEWAY_WEBHOOK_BASE_URL}/webhooks/openai"
POLL_INTERVAL_SECS    = 60
REQUEST_TIMEOUT       = 20.0
MAX_CONSECUTIVE_ERRORS = 5


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [openai_poller] {msg}", flush=True)


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _fmt(status: str) -> str:
    """'degraded_performance' → 'Degraded Performance'."""
    return status.replace("_", " ").title()


def _map_component_type(status: str) -> str:
    """Map Atlassian component status → our incident type."""
    return {
        "operational":          "resolved",
        "degraded_performance": "degradation",
        "partial_outage":       "outage",
        "major_outage":         "outage",
        "under_maintenance":    "maintenance",
    }.get(status, "unknown")


def _classify_incident(incident: dict) -> str:
    """Classify an incident → outage | degradation | new_incident."""
    impact      = incident.get("impact", "").lower()
    title_lower = incident.get("name", "").lower()

    if incident.get("status", "").lower() == "resolved":
        return "resolved"
    if impact == "critical" or any(kw in title_lower for kw in ("outage", "down", "unavailable")):
        return "outage"
    if impact == "major" or any(kw in title_lower for kw in ("degraded", "error", "latency")):
        return "degradation"
    return "new_incident"


async def _forward(client: httpx.AsyncClient, envelope: dict) -> None:
    resp = await client.post(
        GATEWAY_WEBHOOK_URL,
        content=json.dumps(envelope).encode(),
        headers={"Content-Type": "application/json"},
    )
    _log(f"Gateway response: HTTP {resp.status_code}")
    resp.raise_for_status()


# Polling Loop
async def poll_openai_status() -> None:
    """
    Hash-based polling loop with conditional requests (ETag / If-Modified-Since).

    Checks two endpoints every cycle:
      1. /api/v2/components.json  — per-service health
      2. /api/v2/incidents.json   — active / new incidents

    On first run the current state is seeded silently (no forwarding).
    Subsequent runs detect changes via MD5 of response body + per-incident
    content hashes, then forward pre-formatted envelopes to the gateway.
    """

    comp_etag = comp_modified = ""
    inc_etag  = inc_modified  = ""

    # Body-level hash caches (skip parsing when unchanged)
    last_comp_body_hash: str = ""
    last_inc_body_hash:  str = ""

    last_component_statuses: dict[str, str] = {}
    last_incident_hashes:    dict[str, str] = {}
    first_run = True
    consecutive_errors = 0

    _log(f"Poller started.  Polling every {POLL_INTERVAL_SECS}s.")

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "StatusTracker/1.0"},
    ) as client:
        while True:
            try:
                hdrs: dict[str, str] = {}
                if comp_etag:
                    hdrs["If-None-Match"] = comp_etag
                if comp_modified:
                    hdrs["If-Modified-Since"] = comp_modified

                comp_resp = await client.get(OPENAI_COMPONENTS_URL, headers=hdrs)

                if comp_resp.status_code == 304:
                    _log("Components: 304 Not Modified.")
                elif comp_resp.status_code == 200:
                    comp_etag    = comp_resp.headers.get("etag", comp_etag)
                    comp_modified = comp_resp.headers.get("last-modified", comp_modified)
                    body_hash = _md5(comp_resp.content)

                    if body_hash != last_comp_body_hash:
                        last_comp_body_hash = body_hash
                        comp_data = comp_resp.json()

                        current: dict[str, str] = {}
                        for c in comp_data.get("components", []):
                            if c.get("group", False):
                                continue
                            current[c.get("name", "?")] = c.get("status", "operational")

                        if not first_run:
                            for name, status in current.items():
                                old = last_component_statuses.get(name)
                                if old and status != old:
                                    _log(f"⚡ {name}: {_fmt(old)} → {_fmt(status)}")
                                    await _forward(client, {
                                        "provider":      "openai",
                                        "incident_type": _map_component_type(status),
                                        "incident": {
                                            "title":      f"{name} — {_fmt(status)}",
                                            "status":     status,
                                            "impact":     "component_change",
                                            "message":    f"{name} changed from {_fmt(old)} to {_fmt(status)}.",
                                            "components": [{"name": name, "status": status}],
                                        },
                                    })

                        last_component_statuses = current

                        degraded = {n: s for n, s in current.items() if s != "operational"}
                        if degraded:
                            for n, s in degraded.items():
                                _log(f"⚠️  {n}: {_fmt(s)}")
                        else:
                            _log("✅ All components operational.")
                    else:
                        _log("Components: body hash unchanged.")

                hdrs = {}
                if inc_etag:
                    hdrs["If-None-Match"] = inc_etag
                if inc_modified:
                    hdrs["If-Modified-Since"] = inc_modified

                inc_resp = await client.get(OPENAI_INCIDENTS_URL, headers=hdrs)

                if inc_resp.status_code == 304:
                    _log("Incidents: 304 Not Modified.")
                elif inc_resp.status_code == 200:
                    inc_etag    = inc_resp.headers.get("etag", inc_etag)
                    inc_modified = inc_resp.headers.get("last-modified", inc_modified)
                    body_hash = _md5(inc_resp.content)

                    if body_hash != last_inc_body_hash:
                        last_inc_body_hash = body_hash
                        inc_data = inc_resp.json()

                        current_hashes: dict[str, str] = {}

                        for inc in inc_data.get("incidents", []):
                            inc_id     = inc.get("id", "")
                            inc_status = inc.get("status", "unknown")
                            updated_at = inc.get("updated_at", "")

                            if inc_status == "resolved":
                                continue

                            content_hash = _md5(f"{inc_id}:{updated_at}".encode())
                            current_hashes[inc_id] = content_hash

                            if first_run:
                                _log(f"📋 Existing: {inc.get('name', '?')} [{inc_status}]")
                                continue

                            old_hash = last_incident_hashes.get(inc_id)
                            if old_hash is None:
                                inc_type = _classify_incident(inc)
                                _log(f"🔴 NEW: {inc.get('name')}")
                            elif old_hash != content_hash:
                                inc_type = "update"
                                _log(f"🔄 UPDATED: {inc.get('name')}")
                            else:
                                continue

                            updates = inc.get("incident_updates", [])
                            message = updates[0].get("body", "") if updates else ""
                            affected = [
                                {"name": c.get("name", "?"), "status": c.get("status", "?")}
                                for c in inc.get("components", [])
                            ]

                            logger.info(
                                f"[openai_poller] [{inc_type.upper()}] {inc.get('name')}\n"
                                f"  Status : {inc_status} | Impact: {inc.get('impact')}\n"
                                f"  Message: {message[:120]}"
                            )

                            await _forward(client, {
                                "provider":      "openai",
                                "incident_type": inc_type,
                                "incident": {
                                    "title":      inc.get("name", "Unknown"),
                                    "status":     inc_status,
                                    "impact":     inc.get("impact", "none"),
                                    "message":    message,
                                    "components": affected,
                                },
                            })

                        # Detect resolved (was tracked, now gone from unresolved)
                        if not first_run:
                            for old_id in last_incident_hashes:
                                if old_id not in current_hashes:
                                    _log(f"✅ RESOLVED: {old_id}")
                                    await _forward(client, {
                                        "provider":      "openai",
                                        "incident_type": "resolved",
                                        "incident": {
                                            "title":      "Incident Resolved",
                                            "status":     "resolved",
                                            "impact":     "none",
                                            "message":    "This incident has been resolved.",
                                            "components": [],
                                        },
                                    })

                        last_incident_hashes = current_hashes
                        if not current_hashes:
                            _log("✅ No active incidents.")
                    else:
                        _log("Incidents: body hash unchanged.")

                first_run = False
                consecutive_errors = 0

            except httpx.ConnectError:
                consecutive_errors += 1
                _log(f"Connection error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")
            except httpx.HTTPStatusError as exc:
                consecutive_errors += 1
                _log(f"HTTP {exc.response.status_code} ({consecutive_errors}).")
            except httpx.TimeoutException:
                consecutive_errors += 1
                _log(f"Timeout ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")
            except Exception as exc:
                consecutive_errors += 1
                _log(f"Error: {exc} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}).")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                _log("Too many errors. Stopping.")
                sys.exit(1)

            _log(f"Sleeping {POLL_INTERVAL_SECS}s…")
            await asyncio.sleep(POLL_INTERVAL_SECS)


if __name__ == "__main__":
    try:
        asyncio.run(poll_openai_status())
    except KeyboardInterrupt:
        _log("Stopped by user.")
