import uuid
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, is_token_revoked
from app.db.session import get_db
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT bearer token and retrieve authenticated User from DB."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Authentication required. Bearer token missing.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "REVOKED_TOKEN",
                "message": "Token has been revoked. Please log in again.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": str(err),
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "Token payload missing subject identifier.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id)
        stmt = select(User).where(User.id == user_uuid, User.is_active.is_(True))
    except ValueError:
        stmt = select(User).where(User.email == user_id, User.is_active.is_(True))

    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "USER_NOT_FOUND",
                "message": "User account inactive or not found in database.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional user dependency for public endpoints with personalized citizen tracking."""
    if not credentials or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory restricting endpoint access to specific user roles."""
    normalized_roles = {r.strip().upper() for r in allowed_roles}

    async def role_checker(user: User = Depends(get_current_user)) -> User:
        user_role = (user.role or "").strip().upper()
        if user_role != "ADMIN" and user_role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Access denied. Endpoint requires one of roles {list(normalized_roles)}, but current user has role '{user.role}'.",
                },
            )
        return user

    return role_checker


# Preconfigured role dependencies
get_current_operator = require_role("OPERATOR", "ADMIN")
get_current_admin = require_role("ADMIN")
get_current_citizen = require_role("CITIZEN", "ADMIN")
