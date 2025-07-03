"""Application settings and configuration."""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = Path(__file__).resolve().parents[3] / "docker" / ".env.dev"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "Project Backend"

    environment: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Runtime environment",
        alias="ENVIRONMENT",
    )

    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="password", alias="DB_PASSWORD")
    db_name: str = Field(default="project_db", alias="DB_NAME")
    db_url_env: str | None = Field(default=None, alias="DB_URL")

    @property
    def db_url(self) -> str:
        """Compute the full database URL from components if not explicitly set."""
        if self.db_url_env:
            return self.db_url_env
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}/{self.db_name}"



settings = Settings()
