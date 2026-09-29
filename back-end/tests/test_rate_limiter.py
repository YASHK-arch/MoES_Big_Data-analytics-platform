"""Tests for rate limiting logic and trusted proxy extraction."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.rate_limiter import SlidingWindowRateLimiter, get_client_ip


def test_get_client_ip_default_ignores_forwarded_for():
    """When TRUSTED_PROXY_COUNT == 0, client IP must strictly come from request.client.host."""
    request = MagicMock()
    request.client.host = "192.168.1.10"
    request.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18"}

    with patch.object(settings, "TRUSTED_PROXY_COUNT", 0):
        ip = get_client_ip(request)
        assert ip == "192.168.1.10"


def test_get_client_ip_trusted_proxy_nth_from_right():
    """When TRUSTED_PROXY_COUNT > 0, extract the Nth IP from the right of X-Forwarded-For."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}

    # 1 proxy from right -> 150.172.238.178
    with patch.object(settings, "TRUSTED_PROXY_COUNT", 1):
        assert get_client_ip(request) == "150.172.238.178"

    # 2 proxies from right -> 70.41.3.18
    with patch.object(settings, "TRUSTED_PROXY_COUNT", 2):
        assert get_client_ip(request) == "70.41.3.18"

    # 3 proxies from right -> 203.0.113.195
    with patch.object(settings, "TRUSTED_PROXY_COUNT", 3):
        assert get_client_ip(request) == "203.0.113.195"


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_fail_open_on_redis_error(caplog):
    """When Redis is unavailable, rate limiter must fail OPEN and log a warning."""
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)

    with patch("app.core.redis.redis_client.incr", new_callable=AsyncMock) as mock_incr:
        mock_incr.side_effect = ConnectionError("Redis is down")
        with caplog.at_level("WARNING"):
            allowed = await limiter.is_allowed_async("test_client_key")
            assert allowed is True
            assert any("Redis unavailable for rate limiter; failing OPEN" in record.message for record in caplog.records)
