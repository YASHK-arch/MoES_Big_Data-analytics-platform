"""Abstract provider interface and base class for physical weather providers."""

from __future__ import annotations

import abc
import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple

from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class BaseWeatherProvider(abc.ABC):
    """Abstract base class for all physical weather providers (stations, models, fixtures).

    Guarantees:
    - Non-blocking execution
    - Configurable timeouts
    - Exponential backoff retry on transient errors
    - Resilient NEUTRAL fallback: provider failure never crashes the pipeline (Product Rule P2).
    """

    def __init__(
        self,
        name: str,
        source_type: PhysicalSourceType,
        is_enabled: bool = True,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        initial_backoff_seconds: float = 0.2,
    ) -> None:
        self.name = name
        self.source_type = source_type
        self.is_enabled = is_enabled
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds

    @abc.abstractmethod
    async def _execute_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        """Provider-specific fetch implementation."""
        raise NotImplementedError

    async def fetch_observation(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        """Fetch weather observation with timeout, retry, and guaranteed fail-safe fallback."""
        if not self.is_enabled:
            return (
                None,
                ProviderStatus.DISABLED,
                f"Provider {self.name} is disabled by configuration.",
            )

        attempt = 0
        backoff = self.initial_backoff_seconds

        while attempt <= self.max_retries:
            try:
                obs, status, error_msg = await asyncio.wait_for(
                    self._execute_fetch(lat, lon, target_time, category),
                    timeout=self.timeout_seconds,
                )
                # If definitive status or client-side error, don't blindly retry
                if status in (
                    ProviderStatus.OK,
                    ProviderStatus.NO_DATA,
                    ProviderStatus.PROVIDER_RATE_LIMITED,
                    ProviderStatus.NOT_APPLICABLE,
                    ProviderStatus.MALFORMED_DATA,
                    ProviderStatus.DISABLED,
                ):
                    return obs, status, error_msg

                # On other transient failures, retry if attempts remain
                attempt += 1
                if attempt <= self.max_retries:
                    logger.warning(
                        "Provider %s attempt %d failed with status %s: %s. Retrying in %.2fs...",
                        self.name,
                        attempt,
                        status,
                        error_msg,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    return obs, status, error_msg

            except asyncio.TimeoutError:
                attempt += 1
                if attempt <= self.max_retries:
                    logger.warning(
                        "Provider %s attempt %d timed out after %.1fs. Retrying in %.2fs...",
                        self.name,
                        attempt,
                        self.timeout_seconds,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error(
                        "Provider %s timed out after %d attempts (%.1fs limit).",
                        self.name,
                        attempt,
                        self.timeout_seconds,
                    )
                    return (
                        None,
                        ProviderStatus.TIMEOUT,
                        f"Request timed out after {self.timeout_seconds}s across {attempt} attempts",
                    )

            except Exception as exc:
                attempt += 1
                if attempt <= self.max_retries:
                    logger.warning(
                        "Provider %s attempt %d raised exception: %s. Retrying in %.2fs...",
                        self.name,
                        attempt,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error(
                        "Provider %s failed with unexpected exception after %d attempts: %s",
                        self.name,
                        attempt,
                        exc,
                    )
                    return (
                        None,
                        ProviderStatus.PROVIDER_ERROR,
                        f"Unexpected exception: {type(exc).__name__}: {str(exc)}",
                    )

        return (
            None,
            ProviderStatus.PROVIDER_ERROR,
            "Max retries exhausted without a definitive result",
        )
