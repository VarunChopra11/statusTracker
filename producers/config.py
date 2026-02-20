import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the producers/ directory
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

GATEWAY_WEBHOOK_BASE_URL: str = os.getenv("GATEWAY_WEBHOOK_BASE_URL", "http://localhost:8000")
