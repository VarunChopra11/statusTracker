from adapters.base import BaseAdapter, NormalizedEvent


class OpenAIAdapter(BaseAdapter):
    """Parses pre-formatted incident envelopes from the OpenAI poller."""

    provider_name = "openai"

    def parse(self, payload: dict) -> NormalizedEvent:
        # From openai_poller: "incident_type" + "incident" 
        if "incident_type" in payload:
            inc      = payload.get("incident", {})
            inc_type = payload.get("incident_type", "unknown").upper()
            comps    = inc.get("components", [])

            # Product: component names or fallback to title
            if len(comps) == 1:
                product = f"OpenAI {comps[0]['name']}"
            elif comps:
                product = f"OpenAI ({len(comps)} components affected)"
            else:
                product = inc.get("title", "OpenAI")

            # Status: [TYPE] (Status) message
            status_label = inc.get("status", "unknown").replace("_", " ").title()
            message      = inc.get("message", "") or inc.get("title", "No details.")
            status_str   = f"[{inc_type}] ({status_label}) {message}"

            return NormalizedEvent(
                product=product,
                status=status_str,
                provider=self.provider_name,
                raw=payload,
            )

        # Legacy format (Atlassian webhook): "page" / "component" / "incident" 
        page = payload.get("page", {}).get("name", "Unknown Page")
        comp = payload.get("component", {}).get("name", "Unknown Component")
        inc  = payload.get("incident", {})

        return NormalizedEvent(
            product=f"{page} {comp}",
            status=inc.get("body") or inc.get("name") or "No status message provided.",
            provider=self.provider_name,
            raw=payload,
        )