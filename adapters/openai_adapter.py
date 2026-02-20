from adapters.base import BaseAdapter, NormalizedEvent


class OpenAIAdapter(BaseAdapter):
    provider_name = "openai"

    def parse(self, payload: dict) -> NormalizedEvent:
        """Parse the raw OpenAI status payload and return a NormalizedEvent."""
        
        page_name      = payload.get("page", {}).get("name", "Unknown Page")
        component_name = payload.get("component", {}).get("name", "Unknown Component")
        incident       = payload.get("incident", {})

        # Build the human-friendly product string: "OpenAI API - Chat Completions"
        product = f"{page_name} {component_name}"

        # Prefer the long-form body text; fall back to the short incident name.
        status = incident.get("body") or incident.get("name") or "No status message provided."

        return NormalizedEvent(
            product=product,
            status=status,
            provider=self.provider_name,
            raw=payload,
        )