import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from esl.config import settings

# Declared as a security scheme so /docs renders an Authorize box for the
# admin routes; it parses the same 'Authorization: Bearer <token>' the
# dashboard already sends.
_bearer = HTTPBearer(auto_error=False, description="Auth0 access token")

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"https://{settings.auth0_domain}/.well-known/jwks.json"
        )
    return _jwks_client


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict:
    """Gates the admin dashboard's own routes.

    Unrelated to the gateway's X-Store-Key auth (see tags.py's
    get_current_store) — gateways are software polling a fixed endpoint,
    not humans who can complete an OAuth redirect.
    """
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(status_code=503, detail="Auth0 not configured")

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = credentials.credentials

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    return claims
