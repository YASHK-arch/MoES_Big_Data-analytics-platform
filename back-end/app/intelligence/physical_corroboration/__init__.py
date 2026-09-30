"""Physical meteorological corroboration module for SIH26069."""

from app.intelligence.physical_corroboration.config import (
    PhysicalCorroborationConfig,
    default_physical_config,
)
from app.intelligence.physical_corroboration.evaluator import (
    compute_grid_hour_cache_key,
    evaluate,
    haversine_distance_km,
)
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationResult,
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
    ProviderStatus,
)

__all__ = [
    "PhysicalCorroborationConfig",
    "default_physical_config",
    "compute_grid_hour_cache_key",
    "evaluate",
    "haversine_distance_km",
    "PhysicalCorroborationResult",
    "PhysicalCorroborationVerdict",
    "PhysicalObservation",
    "PhysicalSourceType",
    "ProviderStatus",
]
