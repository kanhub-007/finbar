"""Application configuration — paths, rate limits, and transport settings.

All values are sourced from environment variables with sensible defaults.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.getenv("FINBAR_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "finbar.db"

# ── yfinance rate limits ────────────────────────────────────────────────────

YF_REQUESTS_PER_SECOND = float(os.getenv("YF_REQUESTS_PER_SECOND", "2.0"))
YF_REQUESTS_PER_MINUTE = int(os.getenv("YF_REQUESTS_PER_MINUTE", "60"))
YF_MAX_RETRIES = int(os.getenv("YF_MAX_RETRIES", "3"))
YF_BASE_BACKOFF = float(os.getenv("YF_BASE_BACKOFF", "2.0"))

# ── Job manager ────────────────────────────────────────────────────────────

JOB_MAX_JOBS = int(os.getenv("FINBAR_JOB_MAX_JOBS", "50"))
JOB_TTL_SECONDS = int(os.getenv("FINBAR_JOB_TTL_SECONDS", "3600"))

# ── MCP transport ──────────────────────────────────────────────────────────

FINBAR_TRANSPORT = os.getenv("FINBAR_TRANSPORT", "stdio").lower()
FINBAR_HOST = os.getenv("FINBAR_HOST", "127.0.0.1")
FINBAR_PORT = int(os.getenv("FINBAR_PORT", "8003"))

# ── API server ─────────────────────────────────────────────────────────────

API_HOST = os.getenv("FINBAR_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("FINBAR_API_PORT", "8000"))
