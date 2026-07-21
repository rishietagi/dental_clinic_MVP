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

    # Admin to seed into staff_user (see app/seed.py). admin_user_id is the
    # Supabase Auth user's UUID — copy it from the Supabase dashboard
    # (Authentication → Users → the user). Empty by default so the app runs
    # without it; the seed script fails loud if it's missing when run.
    admin_user_id: str = ""
    admin_email: str = ""
    admin_name: str = ""

    # Base Supabase project URL, e.g. https://<ref>.supabase.co (no trailing
    # path). Used to verify access tokens: we derive the JWKS URL and the
    # expected issuer from it. Empty by default so the app imports without it;
    # the auth dependency fails loud if a request needs it and it's unset.
    supabase_url: str = ""

    # Where uploaded patient files (X-rays, photos, docs) are stored on disk
    # (5.6). A local path in dev, backed by a Docker named volume; Phase 7 swaps
    # the storage implementation (Supabase Storage / S3) by config, not by
    # changing call sites. Never hardcoded — differs local vs prod by env only.
    upload_dir: str = "/data/uploads"

    # Max accepted upload size in bytes (default 15 MB) — a dental X-ray/photo is
    # comfortably under this; the router rejects anything larger with 413.
    max_upload_bytes: int = 15 * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        """Where Supabase publishes the public keys that sign access tokens."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        """The `iss` claim every Supabase access token carries."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


settings = Settings()
