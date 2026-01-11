"""API routers for Heliox-AI."""
from fastapi import APIRouter

from app.core.config import get_settings
from app.api import auth, teams, jobs, costs, usage, analytics
from app.api.routes import admin, recommendations, demo, forecast, alert_settings, daily_digest, public

settings = get_settings()

api_router = APIRouter()

# Include all routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(teams.router, prefix="/teams", tags=["Teams"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(costs.router, prefix="/costs", tags=["Costs"])
api_router.include_router(usage.router, prefix="/usage", tags=["Usage"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])

# Demo routes only available in dev environment (security: prevents demo endpoints in production)
if settings.ENV == "dev":
    api_router.include_router(demo.router, prefix="/admin/demo", tags=["Demo"])

api_router.include_router(forecast.router, prefix="/forecast", tags=["Forecast"])
api_router.include_router(alert_settings.router, prefix="/alert-settings", tags=["Alert Settings"])
api_router.include_router(daily_digest.router, prefix="/daily-digest", tags=["Daily Digest"])
api_router.include_router(public.router, prefix="/public", tags=["Public"])

