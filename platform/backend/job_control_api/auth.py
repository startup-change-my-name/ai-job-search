import secrets

from fastapi import HTTPException, status

from .settings import Settings


def require_proxy_token(settings: Settings, supplied: str | None) -> None:
    expected = settings.internal_proxy_token.get_secret_value()
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid internal proxy token required",
        )
