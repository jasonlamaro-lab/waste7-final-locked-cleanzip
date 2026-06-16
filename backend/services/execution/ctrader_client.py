"""
cTrader/Spotware Broker Client — Pepperstone Integration
OAuth 2.0 Authorization Code Flow for live trading.
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

CTRADER_CLIENT_ID = os.environ.get("CTRADER_CLIENT_ID", "")
CTRADER_CLIENT_SECRET = os.environ.get("CTRADER_CLIENT_SECRET", "")
CTRADER_ACCOUNT_ID = int(os.environ.get("CTRADER_ACCOUNT_ID", "0"))
CTRADER_REDIRECT_URI = os.environ.get("CTRADER_REDIRECT_URI", "")

TOKEN_FILE = Path("/app/backend/.ctrader_tokens.json")

_state = {
    "connected": False,
    "authenticated": False,
    "access_token": None,
    "refresh_token": None,
    "token_expiry": None,
    "account_id": CTRADER_ACCOUNT_ID,
    "auth_url": None,
    "last_error": None,
}


def _save_tokens():
    data = {
        "access_token": _state["access_token"],
        "refresh_token": _state["refresh_token"],
        "token_expiry": _state["token_expiry"],
        "account_id": _state["account_id"],
    }
    try:
        TOKEN_FILE.write_text(json.dumps(data))
        logger.info("cTrader tokens saved")
    except Exception as e:
        logger.error(f"Failed to save cTrader tokens: {e}")


def _load_tokens():
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            _state["access_token"] = data.get("access_token")
            _state["refresh_token"] = data.get("refresh_token")
            _state["token_expiry"] = data.get("token_expiry")
            if data.get("account_id"):
                _state["account_id"] = data["account_id"]
            logger.info("cTrader tokens loaded from disk")
            return True
        except Exception as e:
            logger.error(f"Failed to load cTrader tokens: {e}")
    return False


def get_auth_url() -> str:
    if not CTRADER_CLIENT_ID:
        return ""
    from urllib.parse import quote
    base = "https://openapi.ctrader.com/apps/auth"
    url = (
        f"{base}?client_id={quote(CTRADER_CLIENT_ID, safe='')}"
        f"&redirect_uri={quote(CTRADER_REDIRECT_URI, safe='')}"
        f"&scope=trading"
        f"&response_type=code"
    )
    _state["auth_url"] = url
    return url


async def exchange_code(code: str) -> Dict[str, Any]:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openapi.ctrader.com/apps/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CTRADER_CLIENT_ID,
                "client_secret": CTRADER_CLIENT_SECRET,
                "redirect_uri": CTRADER_REDIRECT_URI,
            },
        ) as resp:
            data = await resp.json()

    if "accessToken" in data:
        _state["access_token"] = data["accessToken"]
        _state["refresh_token"] = data.get("refreshToken")
        _state["token_expiry"] = data.get("expiresIn")
        _state["authenticated"] = True
        _state["last_error"] = None
        _save_tokens()
        logger.info(f"cTrader authenticated! Token expires in {data.get('expiresIn')}s")
        return {"success": True, "message": "Authenticated successfully"}
    else:
        error = data.get("description", data.get("errorCode", "Unknown error"))
        _state["last_error"] = error
        logger.error(f"cTrader auth failed: {error}")
        return {"success": False, "error": error}


async def refresh_access_token() -> bool:
    if not _state["refresh_token"]:
        return False
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openapi.ctrader.com/apps/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": _state["refresh_token"],
                    "client_id": CTRADER_CLIENT_ID,
                    "client_secret": CTRADER_CLIENT_SECRET,
                },
            ) as resp:
                data = await resp.json()
        if "accessToken" in data:
            _state["access_token"] = data["accessToken"]
            _state["refresh_token"] = data.get("refreshToken", _state["refresh_token"])
            _state["token_expiry"] = data.get("expiresIn")
            _state["authenticated"] = True
            _save_tokens()
            logger.info("cTrader token refreshed")
            return True
        else:
            _state["last_error"] = data.get("description", "Refresh failed")
            return False
    except Exception as e:
        _state["last_error"] = str(e)
        return False


def get_status() -> Dict[str, Any]:
    # If we have a refresh token but not authenticated, check if we already tried
    return {
        "connected": _state["connected"],
        "authenticated": _state["authenticated"],
        "account_id": _state["account_id"],
        "has_refresh_token": _state["refresh_token"] is not None,
        "last_error": _state["last_error"],
        "auth_url": get_auth_url() if not _state["authenticated"] else None,
    }


async def ensure_authenticated() -> bool:
    """If we have a refresh_token but aren't authenticated, refresh now."""
    if _state["authenticated"]:
        return True
    if _state["refresh_token"]:
        return await refresh_access_token()
    return False


def init():
    _load_tokens()
    if _state["refresh_token"]:
        logger.info("cTrader has saved refresh token — attempting auto-refresh on startup")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(refresh_access_token())
            else:
                loop.run_until_complete(refresh_access_token())
        except Exception as e:
            logger.warning(f"cTrader startup refresh deferred: {e}")
    else:
        logger.info(
            "cTrader not authenticated. User must visit auth URL to connect. "
            f"Client ID configured: {'YES' if CTRADER_CLIENT_ID else 'NO'}"
        )
