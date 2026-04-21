from pathlib import Path
from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_PASSWORD: str
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = ""
    REPLY_TO: str = ""
    BASE_URL: str = "https://couldyoumake.app"

    # Legacy SMTP settings — kept here so existing .env / Railway vars
    # don't cause a ValidationError during the Resend rollout. No longer
    # read by the code. Safe to delete these env vars, and this block,
    # once the migration is confirmed working in production.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 0
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    model_config = {"env_file": str(ENV_FILE), "extra": "ignore"}


settings = Settings()
