"""Application configuration loaded from environment variables."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        extra="ignore",
    )

    APP_NAME: str = "amzur-chatbot"
    DEBUG: bool = False

    DATABASE_URL: str = ""
    LITELLM_PROXY_URL: str = ""
    LITELLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"
    VISION_MODEL: str = "gemini-2.0-flash"
    LLM_TIMEOUT_SECONDS: int = 30
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 15
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    AUTH_COOKIE_NAME: str = "access_token"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    FRONTEND_URL: str = "http://localhost:5174"


settings = Settings()
