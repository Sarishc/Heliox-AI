"""
Server-side CAPTCHA verification via hCaptcha API.

POST https://api.hcaptcha.com/siteverify
Only clears brute-force requirement when response.success == True.
"""
import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

HCAPTCHA_VERIFY_URL = "https://api.hcaptcha.com/siteverify"


def verify_captcha_token(token: str, remote_ip: Optional[str] = None) -> bool:
    """
    Verify CAPTCHA token via hCaptcha siteverify API.

    Args:
        token: The h-captcha-response token from the client
        remote_ip: Client IP (recommended for accuracy)

    Returns:
        True if verification succeeded (response.success == True), False otherwise.
    """
    settings = get_settings()
    secret = getattr(settings, "HCAPTCHA_SECRET_KEY", None) or ""

    if not secret:
        logger.warning("HCAPTCHA_SECRET_KEY not configured; CAPTCHA verification disabled")
        return False

    if not token or not token.strip():
        logger.warning("CAPTCHA verification failed: empty token")
        return False

    payload = {
        "secret": secret,
        "response": token.strip(),
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(HCAPTCHA_VERIFY_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("CAPTCHA verification HTTP error: %s", e)
        return False
    except Exception as e:
        logger.warning("CAPTCHA verification failed: %s", e)
        return False

    success = data.get("success", False)
    error_codes = data.get("error-codes", [])

    if not success:
        logger.warning(
            "CAPTCHA verification failed",
            extra={
                "error_codes": error_codes,
                "hostname": data.get("hostname"),
            },
        )
        return False

    return True
