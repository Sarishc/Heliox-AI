"""Tests for recommendation apply/dismiss action system."""

from unittest.mock import MagicMock, patch


from app.schemas.recommendation import (
    Recommendation,
    RecommendationEvidence,
    RecommendationSeverity,
    RecommendationType,
)
from app.services.recommendation_actions import (
    recommendation_fingerprint,
    apply_recommendation,
    get_action_status,
)


def test_recommendation_fingerprint_deterministic():
    """Same recommendation yields same fingerprint."""
    rec = Recommendation(
        type=RecommendationType.IDLE_GPU,
        title="Idle A100 on AWS",
        description="Test",
        severity=RecommendationSeverity.HIGH,
        estimated_savings_usd=100.0,
        evidence=RecommendationEvidence(
            provider="aws",
            gpu_type="a100",
            date_range={"start_date": "2024-01-01", "end_date": "2024-01-14"},
        ),
    )
    fp1 = recommendation_fingerprint(rec)
    fp2 = recommendation_fingerprint(rec)
    assert fp1 == fp2
    assert len(fp1) == 32


def test_recommendation_fingerprint_differs_by_type():
    """Different types yield different fingerprints."""
    evidence = RecommendationEvidence(provider="aws", gpu_type="a100")
    rec1 = Recommendation(
        type=RecommendationType.IDLE_GPU,
        title="A",
        description="B",
        severity=RecommendationSeverity.HIGH,
        estimated_savings_usd=0,
        evidence=evidence,
    )
    rec2 = Recommendation(
        type=RecommendationType.LONG_RUNNING_JOB,
        title="A",
        description="B",
        severity=RecommendationSeverity.HIGH,
        estimated_savings_usd=0,
        evidence=RecommendationEvidence(
            job_id="job-123",
            provider="aws",
            gpu_type="a100",
        ),
    )
    assert recommendation_fingerprint(rec1) != recommendation_fingerprint(rec2)


def test_recommendation_fingerprint_from_dict():
    """Fingerprint works when recommendation is a dict."""
    rec_dict = {
        "type": "idle_gpu",
        "title": "Test",
        "description": "Test",
        "severity": "high",
        "estimated_savings_usd": 50.0,
        "evidence": {
            "provider": "gcp",
            "gpu_type": "h100",
            "date_range": {"start_date": "2024-02-01", "end_date": "2024-02-14"},
        },
    }
    rec = Recommendation.model_validate(rec_dict)
    fp = recommendation_fingerprint(rec)
    assert len(fp) == 32


def test_apply_recommendation_requires_valid_rec():
    """apply_recommendation validates recommendation shape."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.add = MagicMock()

    rec = {
        "type": "idle_gpu",
        "title": "Test",
        "description": "D",
        "severity": "high",
        "estimated_savings_usd": 10.0,
        "evidence": {"provider": "aws", "gpu_type": "a100"},
    }
    from uuid import uuid4

    team_id = uuid4()

    with patch("app.services.recommendation_actions.RecommendationAction") as MockAction:
        mock_action = MagicMock()
        mock_action.id = uuid4()
        MockAction.return_value = mock_action
        action, created = apply_recommendation(db, team_id, rec, status="applied", user_id=None)
        assert action is not None
        assert created is True


def test_get_action_status_empty():
    """get_action_status returns empty dict for no fingerprints."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    from uuid import uuid4

    status_map = get_action_status(db, uuid4(), [])
    assert status_map == {}
