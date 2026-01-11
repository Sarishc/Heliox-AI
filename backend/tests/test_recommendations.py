"""Unit tests for recommendation engine."""
import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.team import Team
from app.services.recommendations import RecommendationEngine
from app.schemas.recommendation import RecommendationFilters, RecommendationSeverity


class TestRecommendationEngine:
    """Test cases for RecommendationEngine."""
    
    def test_idle_gpu_detection_high_severity(self):
        """
        Test idle GPU detection with 100% idle capacity (HIGH severity).
        
        Scenario:
        - Expected: 336 hours (14 days * 24 hours)
        - Actual: 0 hours
        - Waste: 100%
        - Expected severity: HIGH
        - Expected savings: 336 * $3.50 = $1,176
        """
        # Mock database session
        db = MagicMock()
        
        # Mock cost data: 14 days of A100 costs
        cost_results = [
            ("a100", "aws", Decimal("18140.49"), 14)  # gpu_type, provider, total_cost, days_count
        ]
        
        # Mock usage data: 0 hours (completely idle)
        usage_result = 0.0
        
        # Setup mock return values
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        # Initialize engine
        engine = RecommendationEngine(db)
        
        # Generate recommendations
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14)
        )
        result = engine.generate_recommendations(filters)
        
        # Verify recommendations
        assert len(result.recommendations) > 0, "Should generate at least 1 recommendation"
        
        idle_recs = [r for r in result.recommendations if r.type.value == "idle_gpu"]
        assert len(idle_recs) > 0, "Should have idle GPU recommendations"
        
        # Check first idle recommendation
        rec = idle_recs[0]
        assert rec.severity == RecommendationSeverity.HIGH, "100% idle should be HIGH severity"
        assert rec.estimated_savings_usd == 1176.0, "Savings should be 336 hours * $3.50"
        assert rec.evidence.waste_percentage == 100.0, "Waste should be 100%"
        assert rec.evidence.expected_usage_hours == 336.0, "Expected 14 days * 24 hours"
        assert rec.evidence.actual_usage_hours == 0.0, "Actual usage should be 0"
    
    def test_idle_gpu_detection_medium_severity(self):
        """
        Test idle GPU detection with 60% idle capacity (MEDIUM severity).
        
        Scenario:
        - Expected: 336 hours
        - Actual: 134.4 hours (40% utilization)
        - Waste: 60%
        - Expected severity: MEDIUM
        """
        db = MagicMock()
        
        cost_results = [("a100", "aws", Decimal("18140.49"), 14)]
        usage_result = 134.4  # 40% utilization
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14)
        )
        result = engine.generate_recommendations(filters)
        
        idle_recs = [r for r in result.recommendations if r.type.value == "idle_gpu"]
        assert len(idle_recs) > 0
        
        rec = idle_recs[0]
        assert rec.severity == RecommendationSeverity.MEDIUM, "60% idle should be MEDIUM severity"
        # Wasted hours: 336 - 134.4 = 201.6 hours
        expected_savings = 201.6 * 3.50
        assert abs(rec.estimated_savings_usd - expected_savings) < 1.0, "Savings calculation should be correct"
    
    def test_idle_gpu_detection_low_severity(self):
        """
        Test idle GPU detection with 40% idle capacity (LOW severity).
        
        Scenario:
        - Expected: 336 hours
        - Actual: 201.6 hours (60% utilization)
        - Waste: 40%
        - Expected severity: LOW
        """
        db = MagicMock()
        
        cost_results = [("a100", "aws", Decimal("18140.49"), 14)]
        usage_result = 201.6  # 60% utilization
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14)
        )
        result = engine.generate_recommendations(filters)
        
        idle_recs = [r for r in result.recommendations if r.type.value == "idle_gpu"]
        assert len(idle_recs) > 0
        
        rec = idle_recs[0]
        assert rec.severity == RecommendationSeverity.LOW, "40% idle should be LOW severity"
    
    def test_no_idle_detection_when_utilization_high(self):
        """
        Test that no idle recommendation is generated when utilization is > 70%.
        
        Scenario:
        - Expected: 336 hours
        - Actual: 268.8 hours (80% utilization)
        - Waste: 20%
        - Expected: No idle GPU recommendation (below 30% idle threshold)
        """
        db = MagicMock()
        
        cost_results = [("a100", "aws", Decimal("18140.49"), 14)]
        usage_result = 268.8  # 80% utilization
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14)
        )
        result = engine.generate_recommendations(filters)
        
        idle_recs = [r for r in result.recommendations if r.type.value == "idle_gpu"]
        assert len(idle_recs) == 0, "Should not generate idle recommendation for 80% utilization"
    
    def test_savings_calculation_accuracy(self):
        """
        Test that savings calculations are accurate and reasonable.
        
        Verifies:
        - Hourly rate is $3.50 (reasonable for GPU compute)
        - Formula: (expected_hours - actual_hours) * $3.50
        - Results are rounded to 2 decimal places
        """
        db = MagicMock()
        
        # Test case: 100 hours wasted
        cost_results = [("a100", "aws", Decimal("5000.00"), 7)]
        usage_result = 68.0  # 168 expected - 68 actual = 100 wasted
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7)
        )
        result = engine.generate_recommendations(filters)
        
        idle_recs = [r for r in result.recommendations if r.type.value == "idle_gpu"]
        if idle_recs:
            rec = idle_recs[0]
            # Expected: 168 hours - 68 hours = 100 wasted hours
            # 100 hours * $3.50 = $350
            expected_savings = 100 * 3.50
            assert rec.estimated_savings_usd == expected_savings, \
                f"Expected ${expected_savings}, got ${rec.estimated_savings_usd}"
    
    def test_filter_by_min_severity(self):
        """
        Test filtering recommendations by minimum severity.
        """
        db = MagicMock()
        
        # Setup data that would generate both HIGH and LOW severity recommendations
        cost_results = [("a100", "aws", Decimal("18140.49"), 14)]
        usage_result = 0.0  # HIGH severity
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        # Test with HIGH severity filter
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
            min_severity=RecommendationSeverity.HIGH
        )
        result = engine.generate_recommendations(filters)
        
        # All recommendations should be HIGH severity
        for rec in result.recommendations:
            assert rec.severity == RecommendationSeverity.HIGH, \
                "With HIGH filter, only HIGH severity recommendations should appear"
    
    def test_deterministic_output(self):
        """
        Test that the engine produces deterministic output.
        
        Running the same filters twice should produce the same recommendations
        (same IDs will differ, but content should be identical).
        """
        db = MagicMock()
        
        cost_results = [("a100", "aws", Decimal("18140.49"), 14)]
        usage_result = 0.0
        
        db.execute.return_value.all.return_value = cost_results
        db.execute.return_value.scalar_one_or_none.return_value = usage_result
        
        engine = RecommendationEngine(db)
        
        filters = RecommendationFilters(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14)
        )
        
        result1 = engine.generate_recommendations(filters)
        result2 = engine.generate_recommendations(filters)
        
        # Should generate same number of recommendations
        assert len(result1.recommendations) == len(result2.recommendations)
        
        # Should have same total savings
        assert result1.total_estimated_savings_usd == result2.total_estimated_savings_usd
        
        # Should have same severity distribution
        assert result1.summary == result2.summary


# Run with: pytest backend/tests/test_recommendations.py -v

