"""Unit tests for CAPTCHA verification via hCaptcha siteverify API."""

from unittest.mock import patch, MagicMock

from app.auth.captcha_verify import verify_captcha_token


@patch("app.auth.captcha_verify.httpx.Client")
def test_valid_captcha_clears_requirement(mock_client_class):
    """Valid CAPTCHA token returns True when provider response.success == True."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "hostname": "localhost"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = "test-secret"

        result = verify_captcha_token("valid-token-from-hcaptcha", remote_ip="127.0.0.1")

    assert result is True
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://api.hcaptcha.com/siteverify"
    assert call_args[1]["data"]["secret"] == "test-secret"
    assert call_args[1]["data"]["response"] == "valid-token-from-hcaptcha"
    assert call_args[1]["data"]["remoteip"] == "127.0.0.1"


@patch("app.auth.captcha_verify.httpx.Client")
def test_invalid_captcha_returns_false(mock_client_class):
    """Invalid CAPTCHA token returns False when provider response.success == False."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": False,
        "error-codes": ["invalid-input-response"],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = "test-secret"

        result = verify_captcha_token("invalid-token", remote_ip="127.0.0.1")

    assert result is False


@patch("app.auth.captcha_verify.httpx.Client")
def test_expired_captcha_returns_false(mock_client_class):
    """Expired CAPTCHA token returns False when provider returns expired error."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": False,
        "error-codes": ["token-expired"],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = "test-secret"

        result = verify_captcha_token("expired-token", remote_ip="127.0.0.1")

    assert result is False


@patch("app.auth.captcha_verify.httpx.Client")
def test_empty_token_returns_false(mock_client_class):
    """Empty token returns False without calling provider API."""
    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = "test-secret"

        result = verify_captcha_token("", remote_ip="127.0.0.1")
        assert result is False

        result = verify_captcha_token("   ", remote_ip="127.0.0.1")
        assert result is False

    mock_client_class.assert_not_called()


def test_no_secret_key_returns_false():
    """When HCAPTCHA_SECRET_KEY is not configured, returns False."""
    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = ""

        result = verify_captcha_token("any-token", remote_ip="127.0.0.1")

    assert result is False


@patch("app.auth.captcha_verify.httpx.Client")
def test_http_error_returns_false(mock_client_class):
    """HTTP error during verification returns False."""
    import httpx

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.HTTPError("Connection failed")
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with patch("app.auth.captcha_verify.get_settings") as mock_settings:
        mock_settings.return_value.HCAPTCHA_SECRET_KEY = "test-secret"

        result = verify_captcha_token("token", remote_ip="127.0.0.1")

    assert result is False


@patch("app.auth.captcha_verify.verify_captcha_token")
def test_clear_captcha_requirement_only_clears_on_valid_verification(mock_verify):
    """clear_captcha_requirement only clears Redis when verify_captcha_token returns True."""
    from app.auth.brute_force import clear_captcha_requirement

    mock_verify.return_value = False
    result = clear_captcha_requirement("192.168.1.1", "invalid-token")
    assert result is False

    mock_verify.return_value = True
    with patch("app.auth.brute_force.get_redis", return_value=None):
        result = clear_captcha_requirement("192.168.1.1", "valid-token")
        assert result is True

    mock_verify.return_value = True
    mock_redis = MagicMock()
    with patch("app.auth.brute_force.get_redis", return_value=mock_redis):
        result = clear_captcha_requirement("192.168.1.1", "valid-token")
        assert result is True
        mock_redis.delete.assert_called_once()


def test_clear_captcha_requirement_rejects_empty_token():
    """clear_captcha_requirement returns False for empty token without calling verify."""
    with patch("app.auth.captcha_verify.verify_captcha_token") as mock_verify:
        from app.auth.brute_force import clear_captcha_requirement

        result = clear_captcha_requirement("192.168.1.1", "")
        assert result is False
        mock_verify.assert_not_called()

        result = clear_captcha_requirement("192.168.1.1", "   ")
        assert result is False
