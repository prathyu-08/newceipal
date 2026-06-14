"""
config/settings.py
------------------
Centralised configuration loaded from .env file.
All secrets and base URLs are read once here and reused across the app.

TTL Reference (all in seconds):
  stats_cache_ttl_seconds          = 60         (dashboard card counts)
  status_cache_ttl_seconds         = 600         (10 min — recruiting status)
  today_submissions_cache_ttl_sec  = 300         (5 min — live submissions)
  bdm_performance_cache_ttl_sec    = 600         (10 min — BDM aggregation)
  high_priority_cache_ttl_seconds  = 1800        (30 min — expensive query)
  submissions_cache_ttl_seconds    = 300         (5 min — raw submissions)
  jobs_date_cache_ttl_seconds      = 300         (5 min — jobs by date)
  jobposts_screen_cache_ttl_sec    = 600         (10 min — web-scrape data)
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    # CEIPAL credentials
    ceipal_base_url: str = "https://api.ceipal.com"
    ceipal_web_base_url: str = "https://talenthirecls2.ceipal.com"
    ceipal_username: str = ""
    ceipal_password: str = ""
    ceipal_api_key: str = ""

    # App settings
    app_env: str = "development"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    redis_url: str = ""
    request_dedupe_ttl_seconds: int = 30

    # Auth — set to a strong random secret in production.
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    # Leave empty only in local development.
    dashboard_api_key: str = ""

    # Where to persist job-detail cache across restarts.
    job_detail_cache_dir: str = ".cache"

    # -----------------------------------------------------------------
    # Cache TTL values — all in seconds.
    # Documented in module docstring above.
    # -----------------------------------------------------------------
    # FIX 9: was hardcoded as 60 in routes/dashboard.py
    stats_cache_ttl_seconds: int = 60

    high_priority_cache_ttl_seconds: int = 30 * 60      # 30 min
    status_cache_ttl_seconds: int = 10 * 60              # 10 min
    bdm_performance_cache_ttl_seconds: int = 10 * 60     # 10 min
    today_submissions_cache_ttl_seconds: int = 5 * 60    # 5 min
    submissions_cache_ttl_seconds: int = 5 * 60          # 5 min
    jobs_date_cache_ttl_seconds: int = 5 * 60            # 5 min
    jobposts_screen_cache_ttl_seconds: int = 10 * 60     # 10 min

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of Settings."""
    return Settings()