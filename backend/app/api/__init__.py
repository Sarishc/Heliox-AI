"""API routers for Heliox-AI."""
from fastapi import APIRouter

from app.core.config import get_settings
from app.api import auth, teams, jobs, costs, usage, analytics
from app.api.routes import admin, recommendations, demo, forecast, alert_settings, daily_digest, public, ingest, onboarding, me, optimize, schedule, finance, experiments, assistant, plugins, alerts_webhook, anomalies, budgets, reports, integrations, billing_usage, billing, auth_oauth, team_sso

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
api_router.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Onboarding"])
api_router.include_router(me.router, tags=["Me"])
api_router.include_router(optimize.router, prefix="/optimize", tags=["Optimizer"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["Scheduling"])
api_router.include_router(finance.router, prefix="/finance", tags=["Finance"])
api_router.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
api_router.include_router(plugins.router, prefix="/plugins", tags=["Plugins"])
api_router.include_router(alerts_webhook.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(anomalies.router, prefix="/anomalies", tags=["Anomalies"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
api_router.include_router(billing_usage.router, prefix="/billing", tags=["Billing & Usage"])
api_router.include_router(billing.router, prefix="/billing", tags=["Stripe Billing"])
api_router.include_router(auth_oauth.router, prefix="/auth", tags=["OAuth Authentication"])
api_router.include_router(team_sso.router, prefix="/teams/sso", tags=["Team SSO"])

# Demo routes only available in dev environment (security: prevents demo endpoints in production)
if settings.ENV == "dev":
    api_router.include_router(demo.router, prefix="/admin/demo", tags=["Demo"])

api_router.include_router(forecast.router, prefix="/forecast", tags=["Forecast"])
api_router.include_router(alert_settings.router, prefix="/alert-settings", tags=["Alert Settings"])
api_router.include_router(daily_digest.router, prefix="/daily-digest", tags=["Daily Digest"])
api_router.include_router(public.router, prefix="/public", tags=["Public"])

