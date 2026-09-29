from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.citizen import router as citizen_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.events import router as events_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.geo import router as geo_router
from app.api.v1.health import router as health_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.relief_centers import router as relief_centers_router
from app.api.v1.reports import router as reports_router
from app.api.v1.routes import router as routes_router
from app.api.v1.verification import router as verification_router

api_v1_router = APIRouter()

# Register endpoint routers
api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(citizen_router, prefix="/citizen", tags=["Citizen Portal"])
api_v1_router.include_router(events_router, prefix="/events", tags=["Realtime Events"])
api_v1_router.include_router(incidents_router, prefix="/incidents", tags=["Incidents"])
api_v1_router.include_router(feedback_router, prefix="/incidents", tags=["Community Feedback"])
api_v1_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_v1_router.include_router(routes_router, prefix="/routes", tags=["Routes"])
api_v1_router.include_router(verification_router, prefix="/verification", tags=["Verification"])
api_v1_router.include_router(geo_router, prefix="/geo", tags=["Geospatial"])
api_v1_router.include_router(relief_centers_router, prefix="/geo/relief-centers", tags=["Relief Centers"])
api_v1_router.include_router(relief_centers_router, prefix="/relief-centers", tags=["Relief Centers"])
api_v1_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_v1_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
