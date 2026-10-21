"""Resolve accounting ownership from a verified CLI bearer, never a supplied ID."""

import os
import re
from pathlib import Path
from uuid import UUID

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException, Request


def authenticated_account_id(request: Request):
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    if not re.fullmatch(r"Bearer wa_[a-f0-9-]{36}\.[a-f0-9]{64}", authorization):
        raise HTTPException(401, "Invalid CLI credential")
    from backend.config import origin

    try:
        configured = dotenv_values(Path(__file__).resolve().parents[4] / ".env", interpolate=False)
        url = origin(
            os.environ.get("WIZARD_ACCOUNT_URL", configured.get("WIZARD_ACCOUNT_URL") or ""),
            os.environ.get("WIZARD_ACCOUNT_LOCAL_DEV", configured.get("WIZARD_ACCOUNT_LOCAL_DEV"))
            == "1",
        )
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            response = client.get(url + "/api/account/me", headers={"Authorization": authorization})
        if response.status_code == 401:
            raise HTTPException(401, "CLI credential expired or revoked")
        if response.status_code != 200:
            raise HTTPException(503, "Account verification is unavailable")
        return str(UUID(response.json()["account"]["id"]))
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OSError):
        raise HTTPException(503, "Account verification is unavailable") from None


def account_profile(account_id):
    return "account:" + account_id if account_id else None
