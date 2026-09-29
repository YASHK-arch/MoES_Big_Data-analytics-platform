"""Authentication API Router for Citizen & Operator Login and Token Management."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_operator, get_current_user
from app.core.rate_limiter import login_rate_limiter
from app.core.security import (
    create_access_token,
    create_sse_ticket,
    get_password_hash,
    revoke_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    TokenResponseData,
    UserProfile,
)

router = APIRouter()


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Citizen Self-Registration",
    description="Registers a new citizen account with email and password, forcing role='CITIZEN' server-side, and returns an authenticated JWT session.",
)
async def signup_citizen(
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register new citizen account (forces role=CITIZEN)."""
    clean_email = payload.email.strip().lower()

    # 1. Check if email already registered
    stmt = select(User).where(User.email.ilike(clean_email))
    res = await db.execute(stmt)
    existing_user = res.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_ALREADY_EXISTS",
                "message": f"An account with email '{clean_email}' already exists. Please log in instead.",
            },
        )

    # 2. Basic password strength check
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "WEAK_PASSWORD",
                "message": "Password must be at least 8 characters long.",
            },
        )

    if payload.password.lower() == clean_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "WEAK_PASSWORD",
                "message": "Password cannot be identical to your email address.",
            },
        )

    # 3. Create citizen user (ALWAYS server-enforced role CITIZEN)
    hashed_pwd = get_password_hash(payload.password)
    user = User(
        email=clean_email,
        full_name=payload.full_name.strip(),
        hashed_password=hashed_pwd,
        role="CITIZEN",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 4. Generate JWT access token
    access_token = create_access_token(
        subject=str(user.id),
        role="CITIZEN",
        extra_claims={
            "email": user.email,
            "full_name": user.full_name,
        },
    )

    profile = UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role="CITIZEN",
        jurisdiction_code=None,
        home_location_lat=user.home_location_lat,
        home_location_lng=user.home_location_lng,
        home_location_name=user.home_location_name,
        alert_radius_km=user.alert_radius_km or 25.0,
    )

    return TokenResponse(
        success=True,
        data=TokenResponseData(
            access_token=access_token,
            token_type="bearer",
            expires_in_seconds=86400,
            user=profile,
            operator=profile,
        ),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Unified User & Operator Login Authentication",
    description="Authenticates credentials for both citizens and operators, returning a signed 24h JWT bearer token and user profile.",
)
async def login_user(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user/operator by email/username and password with rate limiting protection."""
    # 1. Rate Limiting Check (Client IP bucket)
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"login:{client_ip}"
    if not login_rate_limiter.is_allowed(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many failed login attempts. Please wait 60 seconds before trying again.",
            },
        )

    email_or_user = payload.username.strip().lower()

    stmt = select(User).where(
        User.email.ilike(email_or_user),
        User.is_active.is_(True),
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "Incorrect email or password. Access denied.",
            },
        )

    # Successful login: reset rate limit counter
    login_rate_limiter.reset(rate_key)

    # Generate JWT token
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        extra_claims={
            "email": user.email,
            "full_name": user.full_name,
        },
    )

    profile = UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        jurisdiction_code=user.jurisdiction_code or ("NATIONAL_DEOC" if user.role in ("OPERATOR", "ADMIN") else None),
        home_location_lat=user.home_location_lat,
        home_location_lng=user.home_location_lng,
        home_location_name=user.home_location_name,
        alert_radius_km=user.alert_radius_km or 25.0,
    )

    return TokenResponse(
        success=True,
        data=TokenResponseData(
            access_token=access_token,
            token_type="bearer",
            expires_in_seconds=86400,
            user=profile,
            operator=profile,
        ),
    )


@router.get(
    "/me",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
    summary="Get Authenticated User Profile",
    description="Returns the profile and saved preferences of the currently authenticated user.",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    """Retrieve current authenticated profile."""
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        jurisdiction_code=current_user.jurisdiction_code,
        home_location_lat=current_user.home_location_lat,
        home_location_lng=current_user.home_location_lng,
        home_location_name=current_user.home_location_name,
        alert_radius_km=current_user.alert_radius_km or 25.0,
    )


@router.post(
    "/sse-ticket",
    status_code=status.HTTP_200_OK,
    summary="Generate Single-Use SSE Ticket Nonce",
    description="Exchanges an authenticated operator session for a 30-second single-use ticket nonce to establish secure EventSource streams without leaking tokens in URLs.",
)
async def generate_sse_ticket(
    operator: User = Depends(get_current_operator),
) -> dict:
    """Generate a single-use nonce for SSE connection establishment."""
    ticket = create_sse_ticket(subject=str(operator.id), role=operator.role)
    return {
        "success": True,
        "data": {
            "ticket": ticket,
            "expires_in_seconds": 30,
        },
    }


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout & Token Revocation",
    description="Revokes the current JWT bearer access token, invalidating any active sessions across the platform.",
)
async def logout_user(
    authorization: str = Header(..., description="Bearer access token to revoke"),
    _user: User = Depends(get_current_user),
) -> dict:
    """Explicitly revoke token and terminate user session."""
    token = authorization.replace("Bearer ", "").strip()
    if token:
        revoke_token(token)
    return {
        "success": True,
        "data": {
            "message": "Session revoked successfully.",
        },
    }

