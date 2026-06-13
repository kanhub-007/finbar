"""Edge case tests for CoinGlassClient retry behaviour."""

import pytest
import requests

from finbar.infrastructure.services.coinglass_client import CoinGlassClient
from finbar.infrastructure.services.coinglass_rate_limiter import (
    CoinGlassRateLimiter,
)


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {"code": "0", "data": []}
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    """Records calls and returns scripted responses or raises."""

    def __init__(self, behaviours):
        # behaviours: list of either _FakeResponse or Exception instances.
        self._behaviours = list(behaviours)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        item = self._behaviours.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_client(fake_session):
    client = CoinGlassClient(
        api_key="test-key",
        rate_limiter=CoinGlassRateLimiter(),
    )
    client._session = fake_session
    return client


def test_connection_error_on_first_attempt_does_not_raise_nameerror(monkeypatch):
    """Regression: when session.get raises before assigning `resp`, the old
    code referenced an unbound `resp` in the except block, raising NameError
    instead of retrying. It must now retry and surface a RuntimeError."""
    monkeypatch.setattr(
        "finbar.infrastructure.services.coinglass_client.time.sleep",
        lambda _: None,
    )
    # Every attempt raises a ConnectionError (a RequestException subclass).
    session = _FakeSession([requests.ConnectionError("boom")] * 3)
    client = _make_client(session)

    with pytest.raises(RuntimeError, match="CoinGlass request failed"):
        client._get("/api/futures/supported-exchange-pairs", {})

    assert session.calls == 3  # all retries were used


def test_retry_succeeds_after_connection_error(monkeypatch):
    """A transient connection error followed by a success returns data."""
    monkeypatch.setattr(
        "finbar.infrastructure.services.coinglass_client.time.sleep",
        lambda _: None,
    )
    session = _FakeSession(
        [
            requests.ConnectionError("transient"),
            _FakeResponse(200, {"code": "0", "data": [{"a": 1}]}),
        ]
    )
    client = _make_client(session)

    data = client._get("/api/futures/supported-exchange-pairs", {})
    assert data == [{"a": 1}]
    assert session.calls == 2


def test_permanent_client_error_is_not_retried(monkeypatch):
    """Regression: a 4xx client error (except 429) must not be retried.

    Retrying a permanent error (400/403/404) wastes up to ~14s of backoff
    sleeps on a request that will never succeed. It should raise immediately.
    """
    # Avoid any real sleeping if the guard ever fails.
    monkeypatch.setattr(
        "finbar.infrastructure.services.coinglass_client.time.sleep",
        lambda _: pytest.fail("must not sleep/backoff on a permanent error"),
    )
    session = _FakeSession([_FakeResponse(404)])
    client = _make_client(session)

    with pytest.raises(RuntimeError, match="not retryable"):
        client._get("/api/futures/supported-exchange-pairs", {})
    # Exactly one attempt — no retries.
    assert session.calls == 1


def test_server_error_is_still_retried(monkeypatch):
    """5xx server errors remain retryable."""
    monkeypatch.setattr(
        "finbar.infrastructure.services.coinglass_client.time.sleep",
        lambda _: None,
    )
    session = _FakeSession(
        [
            _FakeResponse(503),
            _FakeResponse(200, {"code": "0", "data": [{"a": 1}]}),
        ]
    )
    client = _make_client(session)
    data = client._get("/api/futures/supported-exchange-pairs", {})
    assert data == [{"a": 1}]
    assert session.calls == 2
