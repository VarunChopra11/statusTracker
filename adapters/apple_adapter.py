import json

from adapters.base import BaseAdapter, NormalizedEvent
from core.logger import logger


class AppleAdapter(BaseAdapter):
    """Adapter that parses structured JSON data from Apple's status API."""

    provider_name = "apple"

    def parse(self, payload: dict) -> NormalizedEvent:
        """Parse the Apple status JSON data and return a NormalizedEvent."""
        # logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # logger.info(f"[apple_adapter] Parsing payload: {json.dumps(payload, indent=2)}")
        # logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        
        data = payload.get("data")

        if not data:
            return NormalizedEvent(
                product="Apple Services",
                status="No status data received.",
                provider=self.provider_name,
                raw=payload,
            )

        # logger.info(f"[apple_adapter] Received data: {json.dumps(data, indent=2)}")

        services = data.get("services", [])

        # Apple signals issues solely via non-empty "events" lists.
        issues = [
            s for s in services
            if s.get("events")  # non-empty list = active issue
        ]

        if issues:
            # Report all affected services, not just the first one
            summaries = []
            for svc in issues:
                name = svc.get("serviceName", "Unknown Service")
                events = svc.get("events", [])
                event = events[0] if events else {}
                status_type = event.get("statusType", "Issue")
                event_status = event.get("eventStatus", "ongoing")
                users = event.get("usersAffected", "")
                summary = f"{name}: {status_type} ({event_status})"
                if users:
                    summary += f" - {users}"
                summaries.append(summary)

            return NormalizedEvent(
                product=f"Apple Services ({len(issues)} affected)",
                status=" | ".join(summaries),
                provider=self.provider_name,
                raw=payload,
            )

        return NormalizedEvent(
            product="Apple Services",
            status="All services are operating normally.",
            provider=self.provider_name,
            raw=payload,
        )