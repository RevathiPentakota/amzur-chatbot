from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import bcrypt
import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User


class AuthService:
    @staticmethod
    def validate_allowed_email(email: str) -> str:
        normalized_email = email.strip()
        if not normalized_email.lower().endswith("@amzur.com"):
            raise HTTPException(status_code=403, detail="Only Amzur employees allowed")
        return normalized_email

    async def register(self, db: AsyncSession, email: str, password: str) -> User:
        email = self.validate_allowed_email(email)
        existing_user = await db.scalar(select(User).where(User.email == email))
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(email=email, hashed_password=self.hash_password(password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def login(self, db: AsyncSession, email: str, password: str) -> User:
        email = self.validate_allowed_email(email)
        user = await db.scalar(select(User).where(User.email == email))
        if not user or not self.verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return user

    async def login_or_create_google_user(
        self,
        db: AsyncSession,
        email: str,
        google_id: str,
    ) -> User:
        email = self.validate_allowed_email(email)
        user = await db.scalar(select(User).where(User.email == email))
        if user:
            if user.google_id != google_id:
                user.google_id = google_id
                await db.commit()
                await db.refresh(user)
            return user

        generated_password = self.hash_password(google_id + email)
        user = User(email=email, google_id=google_id, hashed_password=generated_password)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    def google_login_url() -> str:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
            raise HTTPException(status_code=500, detail="Google OAuth is not configured")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def fetch_google_user_info(self, code: str) -> dict:
        if not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Google OAuth is not configured")

        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Google token exchange failed")

            access_token = token_response.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="Google access token missing")

            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Google user info fetch failed")

            userinfo = userinfo_response.json()
            if not userinfo.get("email") or not userinfo.get("sub"):
                raise HTTPException(status_code=400, detail="Google user info is incomplete")
            return userinfo

    @staticmethod
    def hash_password(password: str) -> str:
        password_bytes = password.encode("utf-8")
        return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )

    @staticmethod
    def create_access_token(subject: str) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {"sub": subject, "exp": expire}
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


auth_service = AuthService()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = await db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
