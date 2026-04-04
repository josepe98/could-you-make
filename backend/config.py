from pathlib import Path
from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_PASSWORD: str
    SESSION_SECRET: str = "changeme-in-production"
    SMTP_HOST: str = "smtp.fastmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = ""
    BASE_URL: str = "https://couldyoumake.app"

    model_config = {"env_file": str(ENV_FILE)}


settings = Settings()
