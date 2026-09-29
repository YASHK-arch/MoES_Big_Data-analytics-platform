import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings


def create_application() -> FastAPI:
    is_prod = settings.ENVIRONMENT.lower() == "production"
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="National Weather Big Data Analytics Platform (SIH26069) Backend API",
        version="0.1.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else f"{settings.API_V1_STR}/openapi.json",
    )

    # CORS Middleware configuration
    if settings.ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.ALLOWED_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Custom Exception Handlers adhering to API_CONTRACT.md
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        code = "HTTP_ERROR"
        message = str(detail)
        details: list[Any] = []

        if isinstance(detail, dict):
            code = detail.get("code", "HTTP_ERROR")
            message = detail.get("message", str(detail))
            details = detail.get("details", detail.get("errors", []))

        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "success": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details if isinstance(details, list) else [details],
                },
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": f"req_{uuid.uuid4().hex[:12]}",
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request parameters or payload structure",
                    "details": exc.errors(),
                },
                "meta": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": f"req_{uuid.uuid4().hex[:12]}",
                },
            },
        )

    # Register API v1 routes
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": "0.1.0",
            "docs": "/docs",
            "health": f"{settings.API_V1_STR}/health",
        }

    return app


app = create_application()
