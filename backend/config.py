from pathlib import Path
from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_PASSWORD: str
    # Optional. When set, admin endpoints accept `Authorization: Bearer <key>`
    # in addition to the session cookie — used by the MCP server and other
    # programmatic callers. Leave empty to disable bearer-token auth entirely.
    API_KEY: str = ""
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = ""
    FROM_NAME: str = ""
    REPLY_TO: str = ""
    BASE_URL: str = "https://couldyoumake.app"
    # Optional. When set, post-submit ticket enrichment calls the Anthropic
    # API to draft a plan into clarifying_notes and pick a level_of_effort.
    # Leave empty to skip enrichment.
    ANTHROPIC_API_KEY: str = ""

    # extra=ignore so stray env vars (old SMTP_*, etc.) don't raise
    # ValidationError on startup.
    model_config = {"env_file": str(ENV_FILE), "extra": "ignore"}


settings = Settings()
