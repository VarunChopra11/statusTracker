# Status Page Tracker

A scalable, event driven Python application that monitors service status pages, detects incidents, outages, and degradations, and logs them in a clean, standardized format. Built with FastAPI and an internal asynchronous queue, it uses a decoupled **Producer-Consumer architecture** to handle concurrent updates efficiently.

---

## Contents

- [Problem](#problem)
- [Solution](#solution)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Hosting, Data & Recreation](#hosting-data--recreation)

---

## Problem

**Link:** [https://gist.github.com/prateeksachan/2930ec6bd8e2f97c2b0b81c1606cdea8](https://gist.github.com/prateeksachan/2930ec6bd8e2f97c2b0b81c1606cdea8)

> **NOTE:** Earlier, OpenAI provided webhook based status updates, but after moving to Incident.io, webhook support was removed.
> To handle this, we implement a polling system that fetches JSON data, processes incident updates, and forwards them to consumers.
> This keeps the system functional now, scalable and allows easy webhook integration again if support returns.

---

## Solution

Monitoring multiple status pages using continuous polling leads to rate limits, wasted resources, and dropped connections under load. A synchronous script would bottleneck when multiple providers update simultaneously.

**My approach** shifts from a "Pull" mindset to a "Push" mindset using an **Event-Driven, Producer-Consumer architecture**:

1. **Unified Ingestion** — A FastAPI gateway exposes a single endpoint. All updates, whether pushed via native webhooks or forwarded by our background pollers, enter through this gateway.

2. **Instant Acknowledgement** — The gateway does zero parsing. It accepts the JSON payload, drops it into an internal `asyncio.Queue`, and immediately returns `HTTP 202 Accepted`. This absorbs traffic bursts without timeouts.

3. **Decoupled Processing** — A background consumer pulls events from the queue at its own pace, routes them to the correct provider specific adapter, normalizes the data, and outputs a clean, standardized log.

4. **Smart Polling** — For services without webhooks, lightweight pollers use HTTP conditional headers (`ETag`, `If-Modified-Since`) and content hashing to only forward data when a genuine change has occurred, using near-zero resources when systems are stable.

**Output format:**

```
[2025-11-03 14:32:00] Product: OpenAI API - Chat Completions
Status: Degraded performance due to upstream issue.
```

---

## Architecture

The project is structured into isolated layers so that a change or failure in one provider never breaks the rest of the system.

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRODUCERS                                │
│                                                                 │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────────┐  │
│  │ openai_poller.py│ │discord_poller.py│ │apple_scraper.py  │  │
│  │ (Incident.io    │ │ (Atlassian API) │ │ (JSONP scraper)  │  │
│  │  JSON API)      │ │                 │ │                  │  │
│  └────────┬────────┘ └────────┬────────┘ └────────┬─────────┘  │
│           │                   │                    │            │
└───────────┼───────────────────┼────────────────────┼────────────┘
            │ HTTP POST         │ HTTP POST          │ HTTP POST
            ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                         │
│                                                                 │
│   POST /webhooks/{provider_name}  →  202 Accepted               │
│                        │                                        │
│                        ▼                                        │
│              ┌──────────────────┐                               │
│              │  asyncio.Queue   │  (Message Buffer)             │
│              └────────┬─────────┘                               │
│                       │                                         │
│                       ▼                                         │
│              ┌──────────────────┐                               │
│              │  Worker Loop     │  (worker/tasks.py)            │
│              │  routes by       │                               │
│              │  provider_name   │                               │
│              └────────┬─────────┘                               │
│                       │                                         │
│         ┌─────────────┼──────────────┐                          │
│         ▼             ▼              ▼                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                  │
│  │  OpenAI    │ │  Discord   │ │  Apple     │                  │
│  │  Adapter   │ │  Adapter   │ │  Adapter   │                  │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘                  │
│        └──────────────┼──────────────┘                          │
│                       ▼                                         │
│             ┌──────────────────┐                                │
│             │ NormalizedEvent  │  (Pydantic model)              │
│             └────────┬─────────┘                                │
│                      ▼                                          │
│             ┌──────────────────┐                                │
│             │  StatusFormatter │  (core/logger.py)              │
│             │  → stdout        │                                │
│             └──────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### 1. Producers (`producers/`)

Producers detect changes and send raw `HTTP POST` requests to the FastAPI gateway.

- **`openai_poller.py`** — Polls OpenAI's Incident.io API (`status.openai.com/api/v2/`). Tracks incident hashes and component status changes, forwarding structured envelopes only when updates occur.
- **`discord_poller.py`** — Fetches Discord's Atlassian-style status page, using `ETag` and `If-Modified-Since` headers to skip unchanged responses.
- **`apple_scraper.py`** — Scrapes Apple's custom JSONP status page, using MD5 content hashing for change detection.
- **Native Webhooks** — Any service that supports webhooks can POST directly to `/webhooks/{provider_name}`.

All producers read `GATEWAY_WEBHOOK_BASE_URL` from the environment to know where to send payloads.

### 2. Ingestion Gateway (`api/`)

A FastAPI server with a single dynamic endpoint: `POST /webhooks/{provider_name}`.

Its only job is to receive the payload, validate it as JSON, push it into the internal queue, and respond with `202 Accepted` immediately.

### 3. Message Buffer (`worker/queue_manager.py`)

An `asyncio.Queue` that acts as a buffer between ingestion and processing. If multiple payloads arrive simultaneously, they are held safely in the queue until the worker processes them.

### 4. Consumer & Adapters (`worker/tasks.py` & `adapters/`)

A background worker runs an infinite loop, pulling messages from the queue and routing them by `provider_name` to the appropriate adapter:

- **`OpenAIAdapter`** — Handles both the new Incident.io poller format and the legacy Atlassian webhook format.
- **`DiscordAdapter`** — Parses Atlassian status page JSON, extracting active incidents or page-level status.
- **`AppleAdapter`** — Parses Apple's service list, detecting issues from non-empty `events` arrays.

Each adapter normalizes vendor-specific JSON into a `NormalizedEvent` Pydantic model with `product`, `status`, `timestamp`, and `provider` fields.

---

## Deployment

The project is fully containerized using Docker. The API and each producer run as isolated containers, so a runaway poller can never consume resources needed by the API gateway.

### Prerequisites

- Docker and Docker Compose installed.

### One-Click Deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

Or manually:

```bash
docker compose up --build -d
```

### What Gets Deployed

| Container            | Role                        | Port |
|----------------------|-----------------------------|------|
| `api`                | FastAPI ingestion gateway   | 8000 |
| `discord-producer`   | Discord status poller       | —    |
| `openai-producer`    | OpenAI status poller        | —    |
| `apple-producer`     | Apple status scraper        | —    |

Producers wait for the API health check (`/health`) to pass before starting.

### Viewing Logs

```bash
# All services
docker compose logs -f

# API consumer logs only
docker compose logs -f api

# Specific producer
docker compose logs -f openai-producer
```

### Stopping

```bash
docker compose down
```

---

## Hosting, Data & Recreation

### Live Hosted Version

The application is hosted at: **[https://statustracker-3h55.onrender.com/](https://statustracker-3h55.onrender.com/)**

You can test it using:

```bash
# Health check
curl https://statustracker-3h55.onrender.com/health

# Wake up the server (Render free tier may sleep)
curl https://statustracker-3h55.onrender.com/wakeup

# Send a test webhook
curl -X POST https://statustracker-3h55.onrender.com/webhooks/openai \
  -H "Content-Type: application/json" \
  -d '{
    "page": {"name": "OpenAI"},
    "component": {"name": "API - Chat Completions"},
    "incident": {"name": "Test", "body": "Degraded performance due to upstream issue."}
  }'
```

### Data Flow

1. A producer container (e.g. `openai-producer`) polls the upstream status API and compares content hashes.
2. On detecting a change, it POSTs the JSON payload to `http://api:8000/webhooks/openai`.
3. The API container accepts the POST, pushes it into `asyncio.Queue`, and returns `202 Accepted`.
4. The background worker pulls the payload, passes it to `OpenAIAdapter`.
5. The adapter extracts product name and status message into a `NormalizedEvent`.
6. `StatusFormatter` in `core/logger.py` prints the formatted output to `stdout`.

### Local Development

Requires Python 3.11+.

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```bash
# Run tests
pytest tests/test.py -v
```

```bash
# Run the API gateway
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Run a producer (separate terminal, set GATEWAY_WEBHOOK_BASE_URL in producers/.env)
python -m producers.openai_poller
```
