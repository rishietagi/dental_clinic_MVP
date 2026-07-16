"""Application settings, loaded from environment variables.

Nothing here is hardcoded: local and production differ by config only.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Not used until step 0.5, when the database is wired up.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/clinic"

    environment: str = "development"

    # Comma-separated list of allowed browser origins, e.g.
    # CORS_ORIGINS=http://localhost:3000,http://localhost
    # Kept as a string rather than list[str] because pydantic-settings parses
    # list fields as JSON, which would reject the plain comma-separated form.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
