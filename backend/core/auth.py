"""Clerk session verification, local development identity, and HTTP authentication."""
from functools import lru_cache
import base64
import json
import os
import re
import traceback
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.core.config import CLERK_HINTS, FRONTEND_DIR


PROTECTED_EXACT_PATHS = (
    "/upload",
    "/api/my-clips",
    "/api/session",
    "/api/settings",
)


DEV_AUTH = os.environ.get("CASCADE_DEV_AUTH") == "1"
DEV_USER_ID = "dev-user"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def is_dev_auth_request(request: Request):
    """Only credential-free requests from a local peer may use dev identity."""
    return (
        DEV_AUTH
        and request.client is not None
        and request.client.host in LOCAL_HOSTS
        and "authorization" not in request.headers
        and "__session" not in request.cookies
    )


def warn_dev_auth():
    if DEV_AUTH:
        try:
            print("⚠️  CASCADE_DEV_AUTH is ON – never use this in production", flush=True)
        except UnicodeEncodeError:  # Windows consoles may use a legacy encoding.
            print("WARNING: CASCADE_DEV_AUTH is ON - never use this in production", flush=True)


def clerk_profile(user_id):
    secret = (
        os.environ.get("CLERK_SECRET_KEY", "")
        .strip()
        .strip("\"'")
        .strip()
    )

    if not re.fullmatch(
        r"sk_(?:test|live)_[A-Za-z0-9_-]+",
        secret,
    ):
        return (
            None,
            "CLERK_SECRET_KEY is missing or invalid.",
        )

    try:
        public_key, _ = clerk_configuration()
    except HTTPException:
        return (
            None,
            "The Clerk publishable key could not be read.",
        )

    if (
        public_key.startswith("pk_test_")
        != secret.startswith("sk_test_")
    ):
        return (
            None,
            "The publishable and secret keys use different environments.",
        )

    request = URLRequest(
        (
            "https://api.clerk.com/v1/users/"
            + quote(user_id, safe="")
        ),
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json",
            "User-Agent": "Cascade/1.0",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            profile = json.load(response)

    except HTTPError as error:
        body = (
            error.read()
            .decode("utf-8", errors="replace")
            .replace(secret, "[redacted]")
        )

        error.close()

        print(
            "CLERK HTTP STATUS:",
            error.code,
            flush=True,
        )

        print(
            "CLERK RESPONSE:",
            body[:800],
            flush=True,
        )

        hint = CLERK_HINTS.get(error.code, "")

        return (
            None,
            (
                f"Clerk profile request failed "
                f"(HTTP {error.code}). {hint}"
            ).strip(),
        )

    except (URLError, TimeoutError, ValueError) as error:
        print(
            "Clerk profile error:",
            type(error).__name__,
            str(error).replace(secret, "[redacted]"),
            flush=True,
        )

        return (
            None,
            "Could not get a valid response from Clerk.",
        )

    if (
        not isinstance(profile, dict)
        or profile.get("id") != user_id
    ):
        return (
            None,
            "Clerk returned an unexpected user profile.",
        )

    return profile, None


# --------------------------------------------------
# Clerk configuration and token verification
# --------------------------------------------------

def clerk_configuration():
    key = os.environ.get(
        "CLERK_PUBLISHABLE_KEY",
        "",
    ).strip()

    # Preserve the legacy publishable-key fallback in the consolidated template.
    if not key:
        login_path = FRONTEND_DIR / "index.html"

        if login_path.is_file():
            match = re.search(
                (
                    r"legacy_clerk_publishable_key"
                    r"\s*=\s*[\"']"
                    r"(pk_(?:test|live)_[^\"']+)"
                    r"[\"']"
                ),
                login_path.read_text(
                    encoding="utf-8"
                ),
            )

            if match:
                key = match.group(1)

    try:
        if not key.startswith(
            ("pk_test_", "pk_live_")
        ):
            raise ValueError(
                "Invalid publishable key."
            )

        encoded = key.split("_", 2)[2]
        encoded += "=" * (-len(encoded) % 4)

        decoded = base64.b64decode(
            encoded
        ).decode()

        if not decoded.endswith("$"):
            raise ValueError(
                "Invalid Clerk domain."
            )

        domain = decoded[:-1]

        if not re.fullmatch(
            r"[a-zA-Z0-9.-]+",
            domain,
        ):
            raise ValueError(
                "Invalid Clerk domain."
            )

    except (
        ValueError,
        IndexError,
        UnicodeError,
    ):
        raise HTTPException(
            503,
            (
                "Set CLERK_PUBLISHABLE_KEY in .env "
                "or restore the original publishable-key "
                "fallback in the website template."
            ),
        )

    return key, domain


def authorized_parties():
    return {
        value.strip()
        for value in os.environ.get(
            "CLERK_AUTHORIZED_PARTIES",
            (
                "http://127.0.0.1:8000,"
                "http://localhost:8000,"
                "http://127.0.0.1:5173,"
                "http://localhost:5173"
            ),
        ).split(",")
        if value.strip()
    }


@lru_cache(maxsize=4)
def clerk_jwks(domain):
    return jwt.PyJWKClient(
        (
            f"https://{domain}"
            "/.well-known/jwks.json"
        ),
        timeout=10,
    )


def verify_clerk_token(token):
    _, domain = clerk_configuration()

    try:
        signing_key = (
            clerk_jwks(domain)
            .get_signing_key_from_jwt(token)
            .key
        )

        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=f"https://{domain}",
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "sub",
                    "sid",
                ],
                "verify_aud": False,
            },
        )

        if (
            claims.get("azp")
            not in authorized_parties()
            or not claims.get("sub")
            or not claims.get("sid")
        ):
            raise jwt.InvalidTokenError(
                "Invalid session or authorized party."
            )

        return claims["sub"]

    except jwt.PyJWKClientConnectionError as error:
        print(
            "Clerk signing-key connection failed:",
            str(error),
            flush=True,
        )

        traceback.print_exc()

        raise HTTPException(
            503,
            (
                "Could not reach Clerk to verify "
                "your session. Try again."
            ),
        ) from error

    except jwt.PyJWTError:
        raise HTTPException(
            401,
            "Please sign in again.",
        )


async def authenticate_request(
    request: Request,
    call_next,
):
    protected = (
        request.url.path
        in PROTECTED_EXACT_PATHS
        or request.url.path.startswith(
            ("/jobs/", "/clips/", "/api/projects", "/api/features/")
        )
    )

    if protected:
        origin = request.headers.get("origin")

        if (
            origin
            and origin not in authorized_parties()
        ):
            return JSONResponse(
                {"detail": "Origin not allowed."},
                status_code=403,
            )

        if is_dev_auth_request(request):
            request.state.user_id = DEV_USER_ID
            request.state.dev_auth = True
        else:
            authorization = request.headers.get(
                "authorization",
                "",
            )

            if authorization.startswith("Bearer "):
                token = authorization[7:]
            else:
                token = request.cookies.get(
                    "__session"
                )

            if not token:
                return JSONResponse(
                    {
                        "detail": "Please sign in first."
                    },
                    status_code=401,
                )

            try:
                request.state.user_id = (
                    await run_in_threadpool(
                        verify_clerk_token,
                        token,
                    )
                )

            except HTTPException as error:
                return JSONResponse(
                    {"detail": error.detail},
                    status_code=error.status_code,
                )

    response = await call_next(request)

    if protected:
        response.headers[
            "Cache-Control"
        ] = "no-store"

    return response


