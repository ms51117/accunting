# Configuration settings
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "مدیریت مالی شخصی"
    SECRET_KEY: str = "CHANGE_THIS_TO_A_SECURE_RANDOM_KEY_123456"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "MS511@secure"  # پسورد ورود را تغییر دهید

    # برای SQLite از این مسیر استفاده می‌شود.
    # در آینده فقط کافیست این مقدار را با PostgreSQL عوض کنید:
    # DATABASE_URL: str = "postgresql://user:pass@localhost:5432/dbname"
    DATABASE_URL: str = "sqlite:///./data/accounting.db"

    class Config:
        env_file = ".env"


settings = Settings()
