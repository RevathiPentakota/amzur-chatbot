from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserInfo
from app.services.auth_service import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await auth_service.register(db, payload.email, payload.password)
    token = auth_service.create_access_token(subject=str(user.id))
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return AuthResponse(message="Registered successfully", user=UserInfo.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await auth_service.login(db, payload.email, payload.password)
    token = auth_service.create_access_token(subject=str(user.id))
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return AuthResponse(message="Logged in successfully", user=UserInfo.model_validate(user))


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    return RedirectResponse(url=auth_service.google_login_url())


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    google_user = await auth_service.fetch_google_user_info(code)
    email = auth_service.validate_allowed_email(google_user["email"])

    user = await auth_service.login_or_create_google_user(
        db,
        email=email,
        google_id=google_user["sub"],
    )
    token = auth_service.create_access_token(subject=str(user.id))

    response = RedirectResponse(url=settings.FRONTEND_URL)
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response
