"""Demo environment routes.

Mounted at /api/v1/admin/demo (admin-gated) and /api/v1/demo (public status).
Available when ENV=dev OR DEMO_MODE=True.
"""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.admin_auth import require_admin
from app.core.config import get_settings
from app.core.db import get_db
from app.models.budget import BudgetEnvironment, BudgetEvent, BudgetPolicy
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.inference import InferenceSpan
from app.models.job import Job
from app.models.recommendation_action import RecommendationAction
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()
public_router = APIRouter()  # mounted at /api/v1/demo (no auth)

# ── constants ─────────────────────────────────────────────────────────────────

DEMO_TEAM_NAME = "Acme ML Platform"
DEMO_USER_EMAIL = "demo@heliox.ai"
DEMO_USER_PASSWORD = "demo"

# (provider=cluster_name, gpu_type, base_weekday_cost, base_weekend_cost, volatility)
COST_CONFIGS = [
    ("prod-training", "A100", 720.0, 180.0, 0.15),
    ("prod-training", "V100", 180.0, 45.0, 0.10),
    ("prod-inference", "V100", 450.0, 450.0, 0.05),
    ("prod-inference", "A10G", 225.0, 225.0, 0.05),
    ("dev-experiments", "T4", 90.0, 10.0, 0.20),
    ("dev-experiments", "A100", 60.0, 5.0, 0.25),
]

# (provider, gpu_type, environment, project, weekday_hours, weekend_hours)
USAGE_CONFIGS = [
    ("prod-training", "A100", "prod", "nlp-team", 10.0, 2.5),
    ("prod-training", "A100", "prod", "cv-team", 6.0, 1.0),
    ("prod-training", "V100", "prod", "nlp-team", 6.0, 1.5),
    ("prod-inference", "V100", "prod", "nlp-team", 8.0, 8.0),
    ("prod-inference", "A10G", "prod", "cv-team", 6.0, 6.0),
    ("dev-experiments", "T4", "dev", "platform-team", 4.0, 0.5),
    ("dev-experiments", "A100", "dev", "cv-team", 2.0, 0.2),
    ("prod-training", "V100", "prod", "platform-team", 3.0, 0.5),
]

RECOMMENDATIONS = [
    {
        "fingerprint": "idle-gpu-llama3-prod-training",
        "action_type": "idle_gpu",
        "savings": 8400.0,
        "provider": "prod-training",
        "gpu_type": "A100",
        "snapshot": {
            "title": "Rightsize llama-3-70b training: A100 → A10G",
            "description": (
                "llama-3-70b training jobs are running at 34% average GPU utilization on A100s. "
                "Migrating to A10G instances would reduce cost by ~$8,400/month with no throughput impact."
            ),
            "evidence": {
                "avg_utilization_pct": 34,
                "current_gpu": "A100",
                "recommended_gpu": "A10G",
                "estimated_monthly_savings_usd": 8400,
                "model": "llama-3-70b",
            },
        },
    },
    {
        "fingerprint": "off-hours-dev-experiments-idle",
        "action_type": "off_hours_usage",
        "savings": 2100.0,
        "provider": "dev-experiments",
        "gpu_type": "T4",
        "snapshot": {
            "title": "Auto-shutdown dev-experiments cluster overnight",
            "description": (
                "dev-experiments cluster accumulates 847 GPU-hours idle overnight (11 PM–7 AM). "
                "Enabling auto-shutdown would save ~$2,100/month."
            ),
            "evidence": {
                "idle_gpu_hours_per_month": 847,
                "idle_window": "23:00–07:00",
                "estimated_monthly_savings_usd": 2100,
                "cluster": "dev-experiments",
            },
        },
    },
    {
        "fingerprint": "spot-sdxl-inference-prod",
        "action_type": "long_running_job",
        "savings": 3200.0,
        "provider": "prod-inference",
        "gpu_type": "A10G",
        "snapshot": {
            "title": "Move stable-diffusion-xl inference to Spot instances",
            "description": (
                "stable-diffusion-xl inference workload tolerates interruption and reruns cheaply. "
                "Migrating to Spot/preemptible instances is estimated to save ~$3,200/month."
            ),
            "evidence": {
                "model": "stable-diffusion-xl",
                "interruption_tolerance": True,
                "spot_discount_pct": 68,
                "estimated_monthly_savings_usd": 3200,
            },
        },
    },
    {
        "fingerprint": "duplicate-embedding-runs-cv",
        "action_type": "idle_gpu",
        "savings": 1450.0,
        "provider": "prod-training",
        "gpu_type": "V100",
        "snapshot": {
            "title": "Deduplicate embeddings-service fine-tune jobs in cv-team",
            "description": (
                "cv-team is running identical embeddings-service fine-tune jobs 3× per week "
                "with the same dataset hash. Caching results would save ~$1,450/month."
            ),
            "evidence": {
                "duplicate_runs_per_week": 3,
                "dataset_hash_collision_rate": 0.91,
                "model": "embeddings-service",
                "estimated_monthly_savings_usd": 1450,
            },
        },
    },
    {
        "fingerprint": "yolo-v8-oversized-instances",
        "action_type": "idle_gpu",
        "savings": 980.0,
        "provider": "dev-experiments",
        "gpu_type": "A100",
        "snapshot": {
            "title": "yolo-v8 experiments using A100 when T4 is sufficient",
            "description": (
                "yolo-v8 model experiments in dev-experiments show <20% memory utilization on A100. "
                "Switching to T4 for dev runs would save ~$980/month with equivalent iteration speed."
            ),
            "evidence": {
                "avg_memory_utilization_pct": 18,
                "current_gpu": "A100",
                "recommended_gpu": "T4",
                "model": "yolo-v8",
                "estimated_monthly_savings_usd": 980,
            },
        },
    },
]


# ── helpers ───────────────────────────────────────────────────────────────────


def _fp(val: str) -> str:
    """Stable 16-char fingerprint for deduplication."""
    return hashlib.sha256(val.encode()).hexdigest()[:16]


def _seed_demo_team_and_user(db: Session) -> tuple[Team, User, str]:
    """Create or refresh demo team + user. Returns (team, user, raw_api_key)."""
    # Team
    team = db.query(Team).filter(Team.name == DEMO_TEAM_NAME).first()
    if not team:
        team = Team(id=uuid4(), name=DEMO_TEAM_NAME, monthly_budget_usd=Decimal("50000.00"))
        db.add(team)
    else:
        team.monthly_budget_usd = Decimal("50000.00")
    db.flush()

    # User
    from app.auth.security import hash_password

    user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
    if not user:
        user = User(
            id=uuid4(),
            email=DEMO_USER_EMAIL,
            hashed_password=hash_password(DEMO_USER_PASSWORD),
            full_name="Demo User",
            is_active=True,
            is_platform_admin=False,
            email_verified=True,
        )
        db.add(user)
    db.flush()

    # Membership (viewer role)
    membership = db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == user.id).first()
    if not membership:
        membership = TeamMember(
            id=uuid4(),
            team_id=team.id,
            user_id=user.id,
            role=TeamRole.VIEWER,
        )
        db.add(membership)

    # API key (expires 30 days, read-only label)
    db.query(TeamAPIKey).filter(
        TeamAPIKey.team_id == team.id,
        TeamAPIKey.key_name == "demo-readonly",
    ).update({"is_active": False})
    raw_key = TeamAPIKey.generate_key()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    api_key = TeamAPIKey(
        id=uuid4(),
        team_id=team.id,
        key_name="demo-readonly",
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.flush()

    return team, user, raw_key


def _clear_demo_data(db: Session, team_id) -> dict:
    """Delete all mutable demo data for a team; keep the team/user/key rows."""
    counts = {}
    counts["recommendation_actions"] = db.execute(
        delete(RecommendationAction).where(RecommendationAction.team_id == team_id)
    ).rowcount
    counts["budget_events"] = db.execute(delete(BudgetEvent).where(BudgetEvent.team_id == team_id)).rowcount
    counts["budget_policies"] = db.execute(delete(BudgetPolicy).where(BudgetPolicy.team_id == team_id)).rowcount
    counts["usage_snapshots"] = db.execute(delete(UsageSnapshot).where(UsageSnapshot.team_id == team_id)).rowcount
    counts["cost_snapshots"] = db.execute(delete(CostSnapshot).where(CostSnapshot.team_id == team_id)).rowcount
    counts["jobs"] = db.execute(delete(Job).where(Job.team_id == team_id)).rowcount
    counts["inference_spans"] = db.execute(delete(InferenceSpan).where(InferenceSpan.team_id == team_id)).rowcount
    db.flush()
    return counts


def _seed_costs(db: Session, team_id, today: date) -> int:
    """Seed 90 days of cost snapshots. Returns number of records inserted."""
    rng = random.Random(42)  # deterministic for reproducible demo
    start = today - timedelta(days=90)
    anomaly_day = today - timedelta(days=21)
    count = 0

    current = start
    while current <= today:
        is_weekend = current.weekday() >= 5
        for provider, gpu_type, base_wd, base_we, vol in COST_CONFIGS:
            base = base_we if is_weekend else base_wd
            jitter = 1.0 + rng.uniform(-vol, vol)
            cost = round(base * jitter, 2)

            # Anomaly spike 3 weeks ago on prod-training A100
            if current == anomaly_day and provider == "prod-training" and gpu_type == "A100":
                cost = round(base_wd * 2.5, 2)

            db.add(
                CostSnapshot(
                    id=uuid4(),
                    team_id=team_id,
                    date=current,
                    provider=provider,
                    gpu_type=gpu_type,
                    cost_usd=Decimal(str(cost)),
                )
            )
            count += 1
        current += timedelta(days=1)

    db.flush()
    return count


def _seed_usage(db: Session, team_id, today: date) -> int:
    """Seed 90 days of usage snapshots. Returns number of records inserted."""
    rng = random.Random(99)
    start = today - timedelta(days=90)
    count = 0

    current = start
    while current <= today:
        is_weekend = current.weekday() >= 5
        for provider, gpu_type, env, project, wday_hrs, wend_hrs in USAGE_CONFIGS:
            base_hrs = wend_hrs if is_weekend else wday_hrs
            hrs = round(base_hrs * (1.0 + rng.uniform(-0.1, 0.1)), 2)
            db.add(
                UsageSnapshot(
                    id=uuid4(),
                    team_id=team_id,
                    date=current,
                    provider=provider,
                    gpu_type=gpu_type,
                    environment=env,
                    project=project,
                    gpu_hours=Decimal(str(hrs)),
                )
            )
            count += 1
        current += timedelta(days=1)

    db.flush()
    return count


def _seed_budgets(db: Session, team_id, today: date) -> dict:
    """Seed budget policies and events. Returns created counts."""
    policies_created = 0
    events_created = 0

    # Budget policies: org-wide + per sub-team
    budget_defs = [
        # (environment, project, monthly_usd, thresholds)
        (BudgetEnvironment.prod, None, 50_000.0, [75, 90, 100]),
        (BudgetEnvironment.prod, "nlp-team", 20_000.0, [80, 100]),
        (BudgetEnvironment.prod, "cv-team", 15_000.0, [80, 100]),
        (BudgetEnvironment.dev, "platform-team", 10_000.0, [90, 100]),
    ]

    created_policies = []
    for env, project, monthly, thresholds in budget_defs:
        policy = BudgetPolicy(
            id=uuid4(),
            team_id=team_id,
            environment=env,
            project=project,
            monthly_budget_usd=Decimal(str(monthly)),
            alert_thresholds=thresholds,
            is_enabled=True,
        )
        db.add(policy)
        created_policies.append((policy, monthly))
        policies_created += 1
    db.flush()

    # Org-wide policy is first in list
    org_policy, org_budget = created_policies[0]

    # Resolved anomaly event — 21 days ago when the spike hit 78% of month budget
    anomaly_day = today - timedelta(days=21)
    spike_spend = round(org_budget * 0.78, 2)
    db.add(
        BudgetEvent(
            id=uuid4(),
            team_id=team_id,
            budget_policy_id=org_policy.id,
            date=anomaly_day,
            threshold=Decimal("0.75"),
            spend_usd=Decimal(str(spike_spend)),
            budget_usd=Decimal(str(org_budget)),
            predicted_breach_date=anomaly_day + timedelta(days=4),
            delivered_via="slack",
        )
    )
    events_created += 1

    # Active warning — current month at ~85% of budget
    mtd_spend = round(org_budget * 0.85, 2)
    db.add(
        BudgetEvent(
            id=uuid4(),
            team_id=team_id,
            budget_policy_id=org_policy.id,
            date=today,
            threshold=Decimal("0.90"),
            spend_usd=Decimal(str(mtd_spend)),
            budget_usd=Decimal(str(org_budget)),
            predicted_breach_date=today + timedelta(days=3),
            delivered_via="none",
        )
    )
    events_created += 1
    db.flush()

    return {"policies": policies_created, "events": events_created}


def _seed_inference_spans(db: Session, team_id, today: date) -> int:
    """Seed 30 days of inference spans for llama-3-70b and stable-diffusion-xl.

    Generates ~10,000 spans total with realistic token counts, durations,
    and attributed costs so the inference dashboard has data to display.
    """
    rng = random.Random(77)
    start = today - timedelta(days=30)
    count = 0

    models = [
        # (model_name, cluster_name, base_reqs_per_day, avg_duration_ms, avg_input, avg_output, cost_per_span)
        ("llama-3-70b", "prod-inference", 200, 1400.0, 512, 256, 0.0025),
        ("stable-diffusion-xl", "prod-inference", 80, 4500.0, 0, 0, 0.0180),
        ("llama-3-70b", "dev-experiments", 20, 900.0, 256, 128, 0.0012),
    ]

    for days_ago in range(30, -1, -1):
        day = today - timedelta(days=days_ago)
        is_weekend = day.weekday() >= 5

        for (
            model_name,
            cluster,
            base_reqs,
            avg_dur,
            avg_in,
            avg_out,
            cost_per,
        ) in models:
            load = 0.4 if is_weekend else 1.0
            n = max(1, int(base_reqs * load * rng.uniform(0.8, 1.2)))

            for _ in range(n):
                hour = rng.randint(0, 23)
                minute = rng.randint(0, 59)
                second = rng.randint(0, 59)
                started_at = datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    minute,
                    second,
                    tzinfo=timezone.utc,
                )
                dur = max(50.0, rng.gauss(avg_dur, avg_dur * 0.3))
                ended_at = started_at + timedelta(milliseconds=dur)

                in_tok = max(0, int(rng.gauss(avg_in, avg_in * 0.2))) if avg_in else None
                out_tok = max(0, int(rng.gauss(avg_out, avg_out * 0.2))) if avg_out else None
                total_tok = ((in_tok or 0) + (out_tok or 0)) or None

                cost = round(cost_per * rng.uniform(0.7, 1.3), 8)
                cost_per_1k = round((cost / total_tok) * 1000, 8) if total_tok else None

                db.add(
                    InferenceSpan(
                        id=uuid4(),
                        team_id=team_id,
                        model_name=model_name,
                        serving_framework="vllm" if "llama" in model_name else "custom",
                        cluster_name=cluster,
                        request_id=f"demo-{uuid4().hex[:16]}",
                        duration_ms=round(dur, 2),
                        started_at=started_at,
                        ended_at=ended_at,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        total_tokens=total_tok,
                        gpu_type="V100" if cluster == "prod-inference" else "T4",
                        cost_usd=cost,
                        cost_per_1k_tokens=cost_per_1k,
                    )
                )
                count += 1

    db.flush()
    return count


def _seed_recommendations(db: Session, team_id, user_id) -> int:
    """Seed 5 recommendation actions. Returns count."""
    count = 0
    for rec in RECOMMENDATIONS:
        db.add(
            RecommendationAction(
                id=uuid4(),
                team_id=team_id,
                recommendation_fingerprint=_fp(rec["fingerprint"]),
                status="dismissed",  # visible as a past recommendation
                action_type=rec["action_type"],
                estimated_savings_usd=rec["savings"],
                recommendation_snapshot=rec["snapshot"],
                applied_by_user_id=None,
                provider=rec.get("provider"),
                gpu_type=rec.get("gpu_type"),
            )
        )
        count += 1
    db.flush()
    return count


# ── admin-gated routes ────────────────────────────────────────────────────────


class SeedResponse(BaseModel):
    status: str
    message: str
    results: dict
    demo_team_id: str
    demo_user_email: str
    demo_password: str
    demo_api_key: str | None = None
    load_test_api_key: str | None = None  # kept for backward compat


@router.post(
    "/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Seed database with rich demo data",
    description=(
        "Creates/refreshes the Acme ML Platform demo tenant with 90 days of realistic "
        "GPU cost data, budgets, and recommendations. "
        "Available when ENV=dev or DEMO_MODE=True. Requires admin auth."
    ),
)
def seed_demo_data(
    *,
    db: Session = Depends(get_db),
    create_load_test_key: bool = Query(False, description="Also create a LoadTest API key"),
    _: Any = Depends(require_admin),
) -> Any:
    if settings.ENV != "dev" and not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo seed requires ENV=dev or DEMO_MODE=True.",
        )

    logger.info("Starting demo seed for tenant '%s'", DEMO_TEAM_NAME)
    today = date.today()
    results: dict = {}

    try:
        # 1. Ensure team + user + API key exist
        team, user, raw_api_key = _seed_demo_team_and_user(db)
        results["team_id"] = str(team.id)

        # 2. Clear existing data for this demo tenant only (safe — never touches other tenants)
        cleared = _clear_demo_data(db, team.id)
        results["cleared"] = cleared

        # 3. Cost snapshots (90 days × 6 GPU combos = 546 rows)
        results["cost_snapshots"] = _seed_costs(db, team.id, today)

        # 4. Usage snapshots (90 days × 8 combos = 720 rows)
        results["usage_snapshots"] = _seed_usage(db, team.id, today)

        # 5. Budgets and events
        results["budgets"] = _seed_budgets(db, team.id, today)

        # 6. Recommendations
        results["recommendations"] = _seed_recommendations(db, team.id, user.id)

        # 7. Inference spans (~10,000 rows — 30 days of llama-3-70b + sd-xl traffic)
        results["inference_spans"] = _seed_inference_spans(db, team.id, today)

        db.commit()
        logger.info("Demo seed complete: %s", results)

    except Exception as exc:
        db.rollback()
        logger.error("Demo seed failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Demo seed failed: {exc}",
        )

    # Optional: LoadTest key
    load_test_api_key = None
    if create_load_test_key:
        try:
            lt_team = db.query(Team).filter(Team.name == "LoadTest").first()
            if not lt_team:
                lt_team = Team(id=uuid4(), name="LoadTest")
                db.add(lt_team)
                db.flush()
            db.query(TeamAPIKey).filter(
                TeamAPIKey.team_id == lt_team.id,
                TeamAPIKey.key_name == "load-test",
            ).update({"is_active": False})
            raw_lt = TeamAPIKey.generate_key()
            db.add(
                TeamAPIKey(
                    id=uuid4(),
                    team_id=lt_team.id,
                    key_name="load-test",
                    key_hash=TeamAPIKey.hash_key(raw_lt),
                    is_active=True,
                )
            )
            db.commit()
            load_test_api_key = raw_lt
        except Exception as e:
            logger.warning("Load test key creation failed: %s", e)

    total_records = (
        results["cost_snapshots"]
        + results["usage_snapshots"]
        + results["budgets"]["policies"]
        + results["budgets"]["events"]
        + results["recommendations"]
    )
    return SeedResponse(
        status="success",
        message=(
            f"Demo seeded: {results['cost_snapshots']} cost records, "
            f"{results['usage_snapshots']} usage records, "
            f"{results['budgets']['policies']} budget policies, "
            f"{results['recommendations']} recommendations, "
            f"{results.get('inference_spans', 0)} inference spans. "
            f"Total: {total_records} records."
        ),
        results=results,
        demo_team_id=str(team.id),
        demo_user_email=DEMO_USER_EMAIL,
        demo_password=DEMO_USER_PASSWORD,
        demo_api_key=raw_api_key,
        load_test_api_key=load_test_api_key,
    )


@router.post(
    "/reset",
    summary="Reset demo environment (delete + re-seed)",
    description="Idempotent. Safe to call multiple times or from a cron job.",
)
def reset_demo_data(
    *,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),
) -> Any:
    if settings.ENV != "dev" and not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset requires ENV=dev or DEMO_MODE=True.",
        )
    # Delegate to seed (which clears then re-seeds)
    return seed_demo_data(db=db, create_load_test_key=False, _=None)


@router.get(
    "/status",
    summary="Get demo data counts (admin)",
)
def get_admin_demo_status(db: Session = Depends(get_db)) -> Any:
    """Data counts for monitoring / CI assertions."""
    from sqlalchemy import func, select

    return {
        "environment": settings.ENV,
        "demo_mode": settings.DEMO_MODE,
        "demo_tenant_configured": bool(settings.DEMO_TENANT_ID),
        "data": {
            "cost_snapshots": db.execute(select(func.count(CostSnapshot.id))).scalar_one(),
            "usage_snapshots": db.execute(select(func.count(UsageSnapshot.id))).scalar_one(),
            "teams": db.execute(select(func.count(Team.id))).scalar_one(),
            "jobs": db.execute(select(func.count(Job.id))).scalar_one(),
        },
    }


@router.get(
    "/teams",
    summary="Get SSO-enabled team IDs (dev only)",
)
def get_demo_teams(
    *,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),
) -> Any:
    if settings.ENV != "dev":
        raise HTTPException(status_code=403, detail="Dev only.")
    teams = db.query(Team).filter(Team.sso_enabled.is_(True)).all()
    demo_team = db.query(Team).filter(Team.name == DEMO_TEAM_NAME).first()
    return {
        "teams": [{"id": str(t.id), "name": t.name} for t in teams],
        "demo_team_id": str(demo_team.id) if demo_team else None,
    }


# ── public routes (no auth) ───────────────────────────────────────────────────


@public_router.get(
    "/status",
    summary="Demo environment status (public)",
    tags=["Demo"],
)
def get_public_demo_status() -> Any:
    """Returns demo credentials and expiry. Used by the frontend banner."""
    if not settings.DEMO_MODE:
        return {"is_demo": False}

    expires_at = (
        datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ).isoformat()

    return {
        "is_demo": True,
        "demo_user_email": DEMO_USER_EMAIL,
        "demo_password": DEMO_USER_PASSWORD,
        "expires_at": expires_at,
        "signup_url": settings.DEMO_SIGNUP_URL,
    }
