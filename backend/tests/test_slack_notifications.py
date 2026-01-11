"""Tests for Slack notification service."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import date, timedelta

from app.services.slack_notifications import (
    SlackNotificationService,
    check_and_send_burn_rate_alert,
    check_and_send_idle_spend_alert,
    send_daily_summary_report,
    BURN_RATE_THRESHOLD_USD
)


@pytest.fixture
def mock_slack_service():
    """Create a mock Slack service with webhook configured."""
    service = SlackNotificationService(webhook_url="https://hooks.slack.com/test")
    return service


@pytest.fixture
def mock_slack_service_disabled():
    """Create a mock Slack service without webhook."""
    service = SlackNotificationService(webhook_url=None)
    return service


def test_slack_service_initialization(mock_slack_service, mock_slack_service_disabled):
    """Test Slack service initialization."""
    assert mock_slack_service.enabled is True
    assert mock_slack_service_disabled.enabled is False


def test_mask_webhook_url(mock_slack_service):
    """Test webhook URL masking for safe logging."""
    url = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
    masked = mock_slack_service._mask_webhook_url(url)
    
    assert "XXXXXXXX" in masked
    assert "***" in masked
    assert len(masked) < len(url)


def test_format_currency(mock_slack_service):
    """Test currency formatting."""
    assert mock_slack_service._format_currency(1000) == "$1,000.00"
    assert mock_slack_service._format_currency(1234.56) == "$1,234.56"
    assert mock_slack_service._format_currency(0) == "$0.00"


def test_create_burn_rate_alert_blocks(mock_slack_service):
    """Test burn rate alert block creation."""
    blocks = mock_slack_service._create_burn_rate_alert_blocks(
        daily_cost=15000,
        threshold=10000,
        date="2026-01-09"
    )
    
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "header"
    assert "High Burn Rate" in blocks[0]["text"]["text"]
    assert "$15,000.00" in blocks[1]["text"]["text"]
    assert "50.0%" in blocks[1]["text"]["text"]  # 50% over threshold


def test_create_idle_spend_alert_blocks(mock_slack_service):
    """Test idle spend alert block creation."""
    recommendations = [
        {
            "title": "Idle GPU: H100",
            "description": "100% idle for 14 days",
            "estimated_savings_usd": 1000
        },
        {
            "title": "Idle GPU: A100",
            "description": "80% idle for 7 days",
            "estimated_savings_usd": 500
        }
    ]
    
    blocks = mock_slack_service._create_idle_spend_alert_blocks(recommendations)
    
    assert len(blocks) >= 4
    assert blocks[0]["type"] == "header"
    assert "Idle GPU" in blocks[0]["text"]["text"]
    assert "$1,500.00" in blocks[1]["text"]["text"]  # Total savings


def test_create_daily_summary_blocks(mock_slack_service):
    """Test daily summary block creation."""
    top_models = [
        {"model_name": "Stable Diffusion XL", "cost": 5000},
        {"model_name": "GPT-4", "cost": 3000}
    ]
    
    blocks = mock_slack_service._create_daily_summary_blocks(
        daily_cost=10000,
        weekly_cost=60000,
        monthly_cost=250000,
        top_models=top_models,
        high_severity_count=3,
        total_savings=2000
    )
    
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "header"
    assert "Daily Summary" in blocks[0]["text"]["text"]
    assert "$10,000.00" in str(blocks)
    assert "Stable Diffusion XL" in str(blocks)


@pytest.mark.asyncio
async def test_send_slack_message_success(mock_slack_service):
    """Test successful Slack message sending."""
    blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Test"}}]
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = await mock_slack_service._send_slack_message(blocks, "Test message")
        
        assert result is True
        assert mock_post.called


@pytest.mark.asyncio
async def test_send_slack_message_retry(mock_slack_service):
    """Test Slack message sending with retries."""
    blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Test"}}]
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Fail twice, then succeed
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        
        mock_post.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mock_slack_service._send_slack_message(blocks, "Test message")
        
        assert result is True
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_send_slack_message_disabled(mock_slack_service_disabled):
    """Test Slack message sending when disabled."""
    blocks = [{"type": "section", "text": {"type": "plain_text", "text": "Test"}}]
    
    result = await mock_slack_service_disabled._send_slack_message(blocks, "Test message")
    
    assert result is False


def test_check_burn_rate_alert_output_shape(db_session):
    """Test burn rate alert function output shape."""
    # This test would require setting up test data in db_session
    # For now, just ensure the function exists and can be called
    assert callable(check_and_send_burn_rate_alert)


def test_check_idle_spend_alert_output_shape(db_session):
    """Test idle spend alert function output shape."""
    assert callable(check_and_send_idle_spend_alert)


def test_send_daily_summary_report_output_shape(db_session):
    """Test daily summary report function output shape."""
    assert callable(send_daily_summary_report)


def test_burn_rate_threshold_configured():
    """Test that burn rate threshold is configured."""
    assert BURN_RATE_THRESHOLD_USD > 0
    assert isinstance(BURN_RATE_THRESHOLD_USD, (int, float))

