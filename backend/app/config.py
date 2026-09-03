"""Application settings, loaded from environment variables.

Nothing here is hardcoded: local and production differ by config only.
"""

from pydantic import field_validator
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

    # The ONE staff row every action is attributed to (10.1 — there is no login).
    # A fixed UUID rather than "whichever row exists" so the identity is stable
    # across reseeds and across a reinstall: audit_log.actor_id and
    # visit.dentist_id point at it, and those references must not move.
    # `app/seed.py` creates the row with exactly this id.
    #
    # Note the validator below: docker-compose passes `${LOCAL_STAFF_ID:-}`, which
    # is an EMPTY STRING when unset, not an absent key — and an empty string would
    # otherwise override the default and crash the seed. Blank means "use the
    # default", which is what every dev environment wants.
    local_staff_id: str = "00000000-0000-4000-8000-000000000001"
    local_staff_email: str = "clinic@localhost"
    local_staff_name: str = "Clinic"

    @field_validator("local_staff_id", "local_staff_email", "local_staff_name", mode="before")
    @classmethod
    def _blank_means_default(cls, v, info):
        """Treat an empty env var as unset, so the field default applies."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return cls.model_fields[info.field_name].default
        return v.strip() if isinstance(v, str) else v

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


settings = Settings()
