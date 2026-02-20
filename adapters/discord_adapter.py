from adapters.base import BaseAdapter, NormalizedEvent

# Map Atlassian page  indicator codes → friendly severity labels
_INDICATOR_MAP = {
    "none":     "Operational",
    "minor":    "Degraded Performance",
    "major":    "Partial Outage",
    "critical": "Major Outage",
}


class DiscordAdapter(BaseAdapter):
    provider_name = "discord"

    def parse(self, payload: dict) -> NormalizedEvent:
        """Parse the raw Discord status payload and return a NormalizedEvent."""
        
        # Extract the relevant fields from the payload, with fallbacks.
        page_name  = payload.get("page", {}).get("name", "Discord")
        incidents = payload.get("incidents", [])
        if incidents:
            active_incident = incidents[0]
            component_name  = active_incident.get("name", "Unknown Service")


            # Grab the latest update body for the richest status text.
            updates = active_incident.get("incident_updates", [])
            status_text = (
                updates[0].get("body") if updates else active_incident.get("name", "")
            ) or "No details available."

        else:
            # No open incidents – use the page-level status description.
            component_name = "Platform"
            status_obj     = payload.get("status", {})
            indicator      = status_obj.get("indicator", "none")
            description    = status_obj.get("description", "All Systems Operational")
            friendly_label = _INDICATOR_MAP.get(indicator, indicator.capitalize())
            status_text    = f"{friendly_label} - {description}"

        product = f"{page_name} {component_name}"


        return NormalizedEvent(
            product=product,
            status=status_text,
            provider=self.provider_name,
            raw=payload,
        )