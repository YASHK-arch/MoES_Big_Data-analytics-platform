import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_application


def test_settings_infrastructure_defaults():
    """Verify that default settings configure correct local infrastructure targets."""
    settings = Settings()
    assert "postgresql+asyncpg://" in settings.DATABASE_URL
    assert "weather_platform" in settings.DATABASE_URL
    assert "redis://localhost:6379" in settings.REDIS_URL
    assert settings.S3_ENDPOINT_URL == "http://localhost:9000"
    assert settings.S3_BUCKET_NAME == "weather-media"
    assert settings.DEBUG is False


def test_settings_custom_infrastructure_env(monkeypatch):
    """Verify that environment variables override infrastructure connection settings."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://custom_user:custom_pass@db-host:5432/custom_db",
    )
    monkeypatch.setenv("REDIS_URL", "redis://redis-host:6380/2")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio-host:9000")
    monkeypatch.setenv("S3_BUCKET_NAME", "custom-bucket")

    settings = Settings()
    expected_db = "postgresql+asyncpg://custom_user:custom_pass@db-host:5432/custom_db"
    assert settings.DATABASE_URL == expected_db
    assert settings.REDIS_URL == "redis://redis-host:6380/2"
    assert settings.S3_ENDPOINT_URL == "http://minio-host:9000"
    assert settings.S3_BUCKET_NAME == "custom-bucket"


def test_production_fails_on_default_secret_key(monkeypatch):
    """Verify production fails startup if SECRET_KEY uses default insecure value."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "default-insecure-dev-secret-key-replace-in-production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://prod.weather.gov.in")

    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "SECRET_KEY must not use default insecure value" in str(exc.value)


def test_production_fails_on_debug_true(monkeypatch):
    """Verify production fails startup if DEBUG is True."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "super-secret-secure-production-key-12345")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://prod.weather.gov.in")

    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "DEBUG must be False" in str(exc.value)


def test_production_fails_on_wildcard_cors(monkeypatch):
    """Verify production fails startup if ALLOWED_ORIGINS contains wildcard '*'."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "super-secret-secure-production-key-12345")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")

    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "ALLOWED_ORIGINS cannot contain wildcard" in str(exc.value)


def test_production_passes_on_valid_config(monkeypatch):
    """Verify production initializes successfully with secure configuration."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "super-secret-secure-production-key-12345")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://prod.weather.gov.in")

    settings = Settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert settings.SECRET_KEY == "super-secret-secure-production-key-12345"


@pytest.mark.asyncio
async def test_production_disables_docs_and_openapi(monkeypatch):
    """Verify that /docs, /redoc, and /openapi.json are disabled in production."""
    monkeypatch.setattr("app.main.settings.ENVIRONMENT", "production")
    app = create_application()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_docs = await client.get("/docs")
        assert res_docs.status_code == 404

        res_redoc = await client.get("/redoc")
        assert res_redoc.status_code == 404

        res_openapi = await client.get("/api/v1/openapi.json")
        assert res_openapi.status_code == 404

        res_openapi_root = await client.get("/openapi.json")
        assert res_openapi_root.status_code == 404
