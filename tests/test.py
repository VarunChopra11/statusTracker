import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.openai_adapter import OpenAIAdapter
from adapters.discord_adapter import DiscordAdapter
from adapters.apple_adapter import AppleAdapter
from adapters.base import NormalizedEvent
from worker.queue_manager import QueueManager


class TestOpenAIAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = OpenAIAdapter()

    # Legacy format tests (backward compatibility) 

    def test_full_payload(self):
        """Parse a complete, well-formed legacy webhook payload."""
        payload = {
            "page":      {"name": "OpenAI"},
            "component": {"name": "API - Chat Completions"},
            "incident":  {
                "name":   "Degraded performance",
                "status": "investigating",
                "body":   "Degraded performance due to upstream issue.",
            },
        }
        event = self.adapter.parse(payload)

        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.product,  "OpenAI API - Chat Completions")
        self.assertEqual(event.status,   "Degraded performance due to upstream issue.")
        self.assertEqual(event.provider, "openai")

    def test_missing_component(self):
        """Adapter should not raise on missing optional keys."""
        payload = {
            "page":     {"name": "OpenAI"},
            "incident": {"name": "Short outage"},
        }
        event = self.adapter.parse(payload)
        self.assertIn("OpenAI", event.product)
        self.assertEqual(event.status, "Short outage")

    def test_empty_payload(self):
        """Adapter should return a valid NormalizedEvent for an empty dict."""
        event = self.adapter.parse({})
        self.assertIsInstance(event, NormalizedEvent)
        self.assertIsNotNone(event.product)
        self.assertIsNotNone(event.status)

    def test_body_preferred_over_name(self):
        """'body' should take precedence over incident 'name' for status text."""
        payload = {
            "page":      {"name": "OpenAI"},
            "component": {"name": "GPT-4"},
            "incident":  {
                "name": "Short name",
                "body": "Longer detailed body description.",
            },
        }
        event = self.adapter.parse(payload)
        self.assertEqual(event.status, "Longer detailed body description.")

    # New API format tests
    def test_api_new_incident(self):
        """Parse a new incident payload from the JSON API poller."""
        payload = {
            "provider": "openai",
            "incident_type": "new_incident",
            "incident": {
                "id":         "inc_abc123",
                "title":      "API Errors on Chat Completions",
                "status":     "investigating",
                "impact":     "major",
                "message":    "We are investigating elevated error rates.",
                "updated_at": "2026-02-20T10:30:00Z",
                "components": [
                    {"name": "API - Chat Completions", "status": "partial_outage"},
                ],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.provider, "openai")
        self.assertIn("Chat Completions", event.product)
        self.assertIn("[NEW_INCIDENT]", event.status)
        self.assertIn("Investigating", event.status)
        self.assertIn("elevated error rates", event.status)

    def test_api_degradation(self):
        """Degradation incident should contain the right type and message."""
        payload = {
            "provider": "openai",
            "incident_type": "degradation",
            "incident": {
                "id":         "inc_def456",
                "title":      "Degraded Performance on Embeddings",
                "status":     "identified",
                "impact":     "minor",
                "message":    "The issue has been identified.",
                "components": [
                    {"name": "API - Embeddings", "status": "degraded_performance"},
                ],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIn("[DEGRADATION]", event.status)
        self.assertIn("Embeddings", event.product)
        self.assertIn("Identified", event.status)

    def test_api_outage(self):
        """Outage incident with multiple affected components."""
        payload = {
            "provider": "openai",
            "incident_type": "outage",
            "incident": {
                "id":         "inc_ghi789",
                "title":      "Major API Outage",
                "status":     "investigating",
                "impact":     "critical",
                "message":    "All API endpoints are returning 500 errors.",
                "components": [
                    {"name": "API - Chat Completions", "status": "major_outage"},
                    {"name": "API - Embeddings", "status": "major_outage"},
                ],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIn("2 components", event.product)
        self.assertIn("[OUTAGE]", event.status)
        self.assertIn("500 errors", event.status)

    def test_api_resolved(self):
        """Resolved incident should contain resolved type."""
        payload = {
            "provider": "openai",
            "incident_type": "resolved",
            "incident": {
                "id":         "inc_resolved1",
                "title":      "Incident Resolved",
                "status":     "resolved",
                "impact":     "none",
                "message":    "This incident has been resolved.",
                "components": [],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIn("[RESOLVED]", event.status)
        self.assertIn("resolved", event.status.lower())

    def test_api_component_change(self):
        """Component status change detected by the poller."""
        payload = {
            "provider": "openai",
            "incident_type": "degradation",
            "incident": {
                "id":         "component-ChatGPT",
                "title":      "ChatGPT — Degraded Performance",
                "status":     "degraded_performance",
                "impact":     "component_change",
                "message":    "ChatGPT changed from Operational to Degraded Performance.",
                "components": [{"name": "ChatGPT", "status": "degraded_performance"}],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIn("ChatGPT", event.product)
        self.assertIn("Degraded Performance", event.status)

    def test_api_empty_incident(self):
        """API payload with missing incident data should not crash."""
        payload = {
            "provider": "openai",
            "incident_type": "unknown",
            "incident": {},
        }
        event = self.adapter.parse(payload)
        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.provider, "openai")


class TestDiscordAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = DiscordAdapter()

    def test_all_clear_payload(self):
        """Operational status with no incidents."""
        payload = {
            "page":   {"name": "Discord"},
            "status": {"indicator": "none", "description": "All Systems Operational"},
            "incidents": [],
        }
        event = self.adapter.parse(payload)
        self.assertEqual(event.provider, "discord")
        self.assertIn("Operational", event.status)

    def test_minor_outage(self):
        """Minor indicator should map to 'Degraded Performance'."""
        payload = {
            "page":      {"name": "Discord"},
            "status":    {"indicator": "minor", "description": "Partial System Outage"},
            "incidents": [],
        }
        event = self.adapter.parse(payload)
        self.assertIn("Degraded", event.status)

    def test_active_incident(self):
        """When incidents are present, the adapter should prefer incident data."""
        payload = {
            "page":   {"name": "Discord"},
            "status": {"indicator": "major", "description": "Major Outage"},
            "incidents": [
                {
                    "name":   "API Issues",
                    "status": "identified",
                    "incident_updates": [
                        {"body": "We are investigating issues with the Discord API."}
                    ],
                }
            ],
        }
        event = self.adapter.parse(payload)
        self.assertEqual(event.status, "We are investigating issues with the Discord API.")
        self.assertIn("API Issues", event.product)


class TestAppleAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = AppleAdapter()

    def test_all_services_normal(self):
        """All services operational should produce an all-clear event."""
        payload = {
            "provider": "apple",
            "data": {
                "services": [
                    {"serviceName": "iCloud", "status": "available"},
                    {"serviceName": "App Store", "status": "available"},
                ],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.provider, "apple")
        self.assertIn("operating normally", event.status)

    def test_no_data(self):
        """Missing 'data' key should return a fallback event."""
        event = self.adapter.parse({"provider": "apple"})
        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.status, "No status data received.")

    def test_empty_data(self):
        """None data should not raise an exception."""
        event = self.adapter.parse({"provider": "apple", "data": None})
        self.assertIsInstance(event, NormalizedEvent)
        self.assertEqual(event.status, "No status data received.")

    def test_service_with_issue(self):
        """A service with events should be detected as an issue."""
        payload = {
            "provider": "apple",
            "data": {
                "services": [
                    {
                        "serviceName": "iCloud Drive",
                        "events": [{"statusType": "Issue", "message": "Experiencing issues."}],
                    },
                    {"serviceName": "App Store", "events": []},
                ],
            },
        }
        event = self.adapter.parse(payload)
        self.assertIn("1 affected", event.product)
        self.assertIn("iCloud Drive", event.status)
        self.assertEqual(event.provider, "apple")

# Queue Manager Unit Tests
class TestQueueManager(unittest.IsolatedAsyncioTestCase):
    """Uses IsolatedAsyncioTestCase (Python 3.8+) to run async tests."""

    async def test_enqueue_dequeue(self):
        """Items enqueued should be dequeued in FIFO order."""
        q = QueueManager()
        item1 = {"provider": "openai",  "payload": {"a": 1}}
        item2 = {"provider": "discord", "payload": {"b": 2}}

        await q.enqueue(item1)
        await q.enqueue(item2)

        self.assertEqual(q.qsize(), 2)
        result1 = await q.dequeue()
        self.assertEqual(result1, item1)
        result2 = await q.dequeue()
        self.assertEqual(result2, item2)
        self.assertEqual(q.qsize(), 0)

    async def test_qsize_reflects_items(self):
        q = QueueManager()
        self.assertEqual(q.qsize(), 0)
        await q.enqueue({"provider": "test", "payload": {}})
        self.assertEqual(q.qsize(), 1)
        await q.dequeue()
        q.task_done()
        self.assertEqual(q.qsize(), 0)


# FastAPI Endpoint Integration Tests
class TestWebhookEndpoint(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests for the FastAPI webhook endpoint.

    We use httpx.AsyncClient with FastAPI's test transport so the tests run
    without needing a live server.
    """

    async def asyncSetUp(self):
        """Import and configure the FastAPI test client."""

        from httpx import AsyncClient, ASGITransport
        from api.main import app
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        await self.client.__aenter__()

    async def asyncTearDown(self):
        await self.client.__aexit__(None, None, None)

    async def test_health_endpoint(self):
        """Health check should return 200 with status ok."""
        resp = await self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    async def test_webhook_openai_returns_202(self):
        """A valid JSON payload should be accepted with HTTP 202."""
        payload = {
            "provider":      "openai",
            "incident_type": "new_incident",
            "incident": {
                "id":         "inc_test",
                "title":      "Test Incident",
                "status":     "investigating",
                "impact":     "minor",
                "message":    "Test message.",
                "components": [{"name": "API", "status": "degraded_performance"}],
            },
        }
        resp = await self.client.post("/webhooks/openai", json=payload)
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertTrue(data["accepted"])
        self.assertEqual(data["provider"], "openai")

    async def test_webhook_discord_returns_202(self):
        payload = {
            "page":      {"name": "Discord"},
            "status":    {"indicator": "minor", "description": "Partial Outage"},
            "incidents": [],
        }
        resp = await self.client.post("/webhooks/discord", json=payload)
        self.assertEqual(resp.status_code, 202)

    async def test_webhook_apple_returns_202(self):
        payload = {
            "provider": "apple",
            "data": {"services": [{"serviceName": "iCloud", "status": "available"}]},
        }
        resp = await self.client.post("/webhooks/apple", json=payload)
        self.assertEqual(resp.status_code, 202)

    async def test_webhook_invalid_json_returns_400(self):
        """Non-JSON body should return HTTP 400."""
        resp = await self.client.post(
            "/webhooks/openai",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

    async def test_webhook_unknown_provider_returns_202(self):
        """Unknown providers are accepted (202) and logged as warnings by the worker."""
        resp = await self.client.post("/webhooks/unknown_svc", json={"some": "data"})
        self.assertEqual(resp.status_code, 202)


if __name__ == "__main__":
    unittest.main(verbosity=2)
