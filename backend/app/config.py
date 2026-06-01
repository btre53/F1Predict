"""Application configuration via environment variables.

All settings are overridable through a local ``.env`` file (see ``.env.example``).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="F1P_", extra="ignore"
    )

    # API
    app_name: str = "F1Predict"
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Database
    database_url: str = "postgresql+psycopg://f1predict:***REMOVED***@localhost:5432/f1predict"

    # Data / ETL
    fastf1_cache_dir: str = ".cache/fastf1"
    jolpica_base_url: str = "https://api.jolpi.ca/ergast/f1"
    openf1_base_url: str = "https://api.openf1.org/v1"

    # Simulation defaults
    default_iterations: int = 10_000

    # Post-race auto-refresh (in-app weekly scheduler -> app.etl.refresh).
    # OFF by default so dev/tests never hit FastF1; enable in prod via
    # F1P_REFRESH_ENABLED=true. Runs after race weekends (Mon 06:00 UTC).
    refresh_enabled: bool = False
    refresh_day_of_week: str = "mon"
    refresh_hour: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
