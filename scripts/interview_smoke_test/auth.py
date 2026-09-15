"""
scripts/interview_smoke_test/auth.py

Mints a real Firebase ID token for a designated test account, without a
browser OAuth round-trip.

Firebase Admin SDK (the same service-account.json backend/src/services/
firebase_auth.py verifies tokens with) can mint a CUSTOM token for any
known uid, but get_current_user verifies an ID TOKEN, not a custom one --
they are different things. The standard way to turn one into the other
outside a browser is Identity Toolkit's signInWithCustomToken REST
endpoint, using the project's public Web API key: the same key the
frontend ships client-side as NEXT_PUBLIC_FIREBASE_API_KEY. It is not a
secret by Firebase's own design -- it identifies the project to Google's
servers, it does not authorize anything on its own -- but it lives only
in frontend/.env.local, so it is read from there rather than duplicated
into a backend .env file.

The resulting token is indistinguishable from one the browser would send:
verify_id_token cannot tell a mint-and-exchange token from a real sign-in.

TEST_ACCOUNT_EMAIL defaults to an admin-exempt account (ADMIN_EMAILS in
dependencies/rate_limit.py), so repeated runs of this script never trip
the one-interview-per-week limit real accounts are held to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

TEST_ACCOUNT_EMAIL = "kevintandon123@gmail.com"


def _web_api_key() -> str:
    values = dotenv_values(REPO_ROOT / "frontend" / ".env.local")
    key = values.get("NEXT_PUBLIC_FIREBASE_API_KEY")
    if not key:
        raise RuntimeError(
            "NEXT_PUBLIC_FIREBASE_API_KEY not found in frontend/.env.local -- "
            "needed to exchange a custom token for a real ID token."
        )
    return key


def _admin_app():
    """
    The default Firebase Admin app, initialized once. Deliberately NOT
    importing backend.src.services.firebase_auth for this side effect --
    that module also wires telemetry and relative imports meant for the
    running server, and importing it here would double-initialize the
    default app if this script later imports anything that also triggers
    it. This stays self-contained.
    """
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        service_account = BACKEND_ROOT / "src" / "services" / "service-account.json"
        if not service_account.exists():
            raise RuntimeError(f"service account not found at {service_account}")
        return firebase_admin.initialize_app(credentials.Certificate(str(service_account)))


def mint_custom_token(email: str = TEST_ACCOUNT_EMAIL) -> tuple[str, str]:
    """
    Returns (custom_token, firebase_uid) -- the RAW custom token, not
    exchanged for an ID token. For the Playwright runner: the browser
    signs itself in with this directly via signInWithCustomToken against
    the app's own real `auth` singleton (see firebase.ts's __TEST_AUTH__
    hook), which is what a real client-side session actually looks like.
    mint_id_token below is for scripts calling the backend HTTP API
    directly, which need an already-exchanged ID token instead.
    """
    _admin_app()
    from firebase_admin import auth as fb_auth

    user = fb_auth.get_user_by_email(email)
    custom_token = fb_auth.create_custom_token(user.uid)
    if isinstance(custom_token, bytes):
        custom_token = custom_token.decode()
    return custom_token, user.uid


def mint_id_token(email: str = TEST_ACCOUNT_EMAIL) -> tuple[str, str]:
    """Returns (id_token, firebase_uid)."""
    custom_token, uid = mint_custom_token(email)

    resp = httpx.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": _web_api_key()},
        json={"token": custom_token, "returnSecureToken": True},
        timeout=15,
    )
    resp.raise_for_status()
    id_token = resp.json()["idToken"]
    print(f"[auth] minted a real ID token for {email} (uid={uid})")
    return id_token, uid


if __name__ == "__main__":
    # Standalone check: mint a token and print nothing sensitive.
    token, uid = mint_id_token()
    print(f"[auth] OK -- token length {len(token)} chars, uid={uid}")
