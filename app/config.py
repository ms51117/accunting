from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    APP_NAME: str = "سامانه حسابداری شخصی"
    SECRET_KEY: str = "test-public-reza-login"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"
    ADMIN_CHAT_ID:str="87384626"
    DATABASE_URL: str = "sqlite:///./data/accounting.db"

    # فیلدهای تلگرام و پروکسی (با حروف بزرگ و یکدست)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    HTTP_PROXY: Optional[str] = None
    HTTPS_PROXY: Optional[str] = None

    CLOUDFLARE_TUNNEL_ENABLED: bool = True
    APP_PORT: int = 8000

    # تنظیمات Pydantic V2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # متغیرهای اضافی در env باعث خطا نمی‌شوند
    )


settings = Settings()

print(getattr(settings, "ADMIN_USERNAME"))
