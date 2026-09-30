"""IMD Station Provider slot (Disabled / Mock-only).

Enforces Product Rule P9:
"The IMD adapter is mock-only (credentials/IP whitelisting). Do not claim IMD station support.
Provide a disabled provider slot that can plug in later."
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from app.intelligence.physical_corroboration.models import (
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)
from app.intelligence.physical_corroboration.providers.base import BaseWeatherProvider


class IMDStationProviderSlot(BaseWeatherProvider):
    """Disabled slot for official IMD AWS/ARG station ingestion.

    When official credentials and IP whitelisting are procured from IMD / MoES,
    this provider can be activated by setting `is_enabled=True` and implementing
    the secure authenticated API calls.
    """

    def __init__(
        self,
        is_enabled: bool = False,
        api_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="IMD_AWS",
            source_type=PhysicalSourceType.STATION,
            is_enabled=is_enabled,
        )
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    async def _execute_fetch(
        self,
        lat: float,
        lon: float,
        target_time: datetime,
        category: str,
    ) -> Tuple[Optional[PhysicalObservation], ProviderStatus, Optional[str]]:
        if not self.is_enabled:
            return (
                None,
                ProviderStatus.DISABLED,
                "IMD station provider slot is disabled pending official credentials and IP whitelisting (P9)",
            )
        return (
            None,
            ProviderStatus.NO_DATA,
            "IMD station data ingestion not yet implemented for live calls",
        )
