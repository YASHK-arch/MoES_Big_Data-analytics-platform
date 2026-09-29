from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Core Application Settings
    PROJECT_NAME: str = "National Weather Big Data Analytics Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "default-insecure-dev-secret-key-replace-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Primary Database (PostgreSQL + PostGIS)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform"
    DATABASE_ECHO: bool = False

    # Cache & Event Streaming (Redis)
    REDIS_URL: str = "redis://localhost:6379/0"
    REALTIME_STREAM_NAME: str = "stream:weather:realtime"
    REALTIME_STREAM_MAXLEN: int = 10000

    # Realtime Outbox Worker Configuration
    OUTBOX_WORKER_ENABLED: bool = True
    OUTBOX_WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    OUTBOX_WORKER_BATCH_SIZE: int = 50
    OUTBOX_WORKER_MAX_ATTEMPTS: int = 5
    OUTBOX_WORKER_PRUNE_INTERVAL_SECONDS: int = 3600
    OUTBOX_WORKER_RETENTION_HOURS: int = 72

    # Data Retention & Archival TTL Configuration (C2)
    DATA_RETENTION_ENABLED: bool = True
    DATA_RETENTION_DAYS: int = 6
    DATA_RETENTION_RUN_INTERVAL_SECONDS: float = 86400.0
    DATA_RETENTION_BATCH_SIZE: int = 500

    # Object Storage (MinIO / S3)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "weather-media"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False
    S3_PRESIGNED_EXPIRY_SECONDS: int = 3600

    # External APIs (Optional in Phase 1)
    DATA_GOV_API_KEY: str = ""
    IMD_API_ENDPOINT: str = "https://api.imd.gov.in/api/v1"
    IMD_API_KEY: str = ""
    IMD_REQUEST_TIMEOUT_SECONDS: float = 15.0
    NDMA_SACHET_RSS_URL: str = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
    NDMA_REQUEST_TIMEOUT_SECONDS: float = 15.0
    CWC_NWDP_API_ENDPOINT: str = "https://nwdp.nwic.gov.in/api/3/action/datastore_search"
    CWC_NWDP_RESOURCE_ID: str = "d80798b9-4b11-4626-8b63-964202ba7216"
    CWC_REQUEST_TIMEOUT_SECONDS: float = 15.0
    CWC_FETCH_LIMIT: int = 50
    GDELT_DOC_ENDPOINT: str = "http://api.gdeltproject.org/api/v2/doc/doc"
    GDELT_QUERY: str = (
        "sourcecountry:IN ("
        'flood OR "heavy rain" OR "waterlogging" OR cyclone OR '
        'landslide OR "heat wave" OR thunderstorm)'
    )
    GDELT_MAX_RECORDS: int = 50
    GDELT_TIMESPAN: str = "24h"
    GDELT_MIN_REQUEST_INTERVAL_SECONDS: float = 5.0
    GDELT_REQUEST_TIMEOUT_SECONDS: float = 15.0
    MASTODON_INSTANCE_URL: str = "https://mastodon.social"
    MASTODON_HASHTAGS: List[str] = [
        "mumbairains",
        "delhirains",
        "bengalururains",
        "chennairains",
        "assamfloods",
        "monsoon",
        "flood",
        "cyclone",
        "heatwave",
    ]
    MASTODON_MAX_RESULTS_PER_TAG: int = 20
    MASTODON_REQUEST_TIMEOUT_SECONDS: float = 15.0
    MASTODON_POLL_INTERVAL_SECONDS: float = 30.0
    MASTODON_MIN_REQUEST_INTERVAL_SECONDS: float = 1.0

    # Phase 3: Open-Meteo Hourly Weather Observation Adapter
    OPEN_METEO_ENDPOINT: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_TIMEOUT_SECONDS: float = 15.0
    OPEN_METEO_MIN_REQUEST_INTERVAL_SECONDS: float = 1.0

    # Phase 3: GDACS Global Disaster Alert and Coordination System Adapter
    GDACS_ENDPOINT: str = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    GDACS_EVENT_TYPES: List[str] = ["FL", "TC", "DR", "WF"]
    GDACS_COUNTRY_CODE: str = "IND"
    GDACS_LOOKBACK_DAYS: int = 7
    GDACS_MIN_REQUEST_INTERVAL_SECONDS: float = 5.0
    GDACS_REQUEST_TIMEOUT_SECONDS: float = 15.0

    # AI & Semantic Intelligence / Deduplication Engine (v1 Initial Parameters)
    DUPLICATE_SEMANTIC_METHOD: str = "sparse_tfidf_ngram_v1"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"  # Configured optional dense backend
    DUPLICATE_SPATIAL_RADIUS_METERS: float = 2500.0
    DUPLICATE_TIME_WINDOW_HOURS: float = 3.0
    DUPLICATE_SEMANTIC_THRESHOLD: float = 0.50
    DUPLICATE_CONFIRMED_THRESHOLD: float = 0.75
    DUPLICATE_POSSIBLE_THRESHOLD: float = 0.55
    DUPLICATE_CANDIDATE_LIMIT: int = 50
    DUPLICATE_ENGINE_VERSION: str = "v1"
    # Evidence Linking Engine (v1 Initial Parameters)
    EVIDENCE_LINK_ENGINE_VERSION: str = "v1"
    EVIDENCE_SPATIAL_RADIUS_METERS: float = 25000.0
    EVIDENCE_TIME_WINDOW_HOURS: float = 48.0
    EVIDENCE_SUPPORTING_THRESHOLD: float = 0.65
    EVIDENCE_RELATED_THRESHOLD: float = 0.45
    EVIDENCE_CONTEXTUAL_THRESHOLD: float = 0.35
    EVIDENCE_CANDIDATE_LIMIT: int = 50
    # Observation Corroboration Engine (v1 — Water Level Policy Defaults)
    CORROBORATION_ENGINE_VERSION: str = "v1"
    CORROBORATION_WL_SPATIAL_RADIUS_METERS: float = 35000.0
    CORROBORATION_WL_TIME_WINDOW_HOURS: float = 24.0
    CORROBORATION_WL_TREND_LOOKBACK_HOURS: float = 6.0
    CORROBORATION_WL_FRESHNESS_MAX_HOURS: float = 48.0
    CORROBORATION_WL_TEMPORAL_PRIOR_FULL_HOURS: float = 4.0
    CORROBORATION_WL_TEMPORAL_POST_DECAY_RATE: float = 0.7
    CORROBORATION_WL_CORROBORATING_THRESHOLD: float = 0.70
    CORROBORATION_WL_CONSISTENT_THRESHOLD: float = 0.45
    CORROBORATION_WL_WEAK_THRESHOLD: float = 0.25
    CORROBORATION_CANDIDATE_LIMIT: int = 50
    CORROBORATION_CWC_SOURCE_TRUST: float = 0.92
    # Incident Credibility Engine (v1 Canonical Parameters)
    CREDIBILITY_ENGINE_VERSION: str = "v1"
    CREDIBILITY_POLICY_VERSION: str = "v1"
    CREDIBILITY_QUALITY_FLOOR_FACTOR: float = 0.70
    CREDIBILITY_QUALITY_SCALE_FACTOR: float = 0.30
    CREDIBILITY_SUPPORT_CROWD_WEIGHT: float = 0.30
    CREDIBILITY_SUPPORT_EVIDENCE_WEIGHT: float = 0.50
    CREDIBILITY_SUPPORT_OBSERVATION_WEIGHT: float = 0.50
    CREDIBILITY_DIVERSITY_INCREMENT: float = 0.06
    CREDIBILITY_MAX_NEGATIVE_PENALTY: float = 0.50
    CREDIBILITY_DIAG_OBS_WEIGHT: float = 0.60
    CREDIBILITY_DIAG_EVI_WEIGHT: float = 0.40
    CREDIBILITY_CAP_UNCORROBORATED_CITIZEN: float = 0.65
    CREDIBILITY_CAP_UNCORROBORATED_OFFICIAL: float = 0.88
    CREDIBILITY_CAP_SINGLE_PROVENANCE: float = 0.82
    CREDIBILITY_CAP_PHYSICAL_ONLY: float = 0.85
    CREDIBILITY_CAP_MAX_MACHINE: float = 0.98
    LLM_PROVIDER: str = "none"
    LLM_API_KEY: str = ""

    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return [str(i) for i in v]
        elif isinstance(v, str):
            return [v]
        raise ValueError(v)


settings = Settings()
