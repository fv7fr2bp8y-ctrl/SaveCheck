"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "SAVECHECK_DATABASE_URL",
        "postgresql+psycopg://savecheck:savecheck@localhost:5432/savecheck",
    )
    # Base URL of the official open-data endpoint. Kept configurable because the
    # exact path/format is finalised once the host is reachable (see
    # ingest/kolkostruva.py).
    kolkostruva_base_url: str = os.getenv(
        "SAVECHECK_KOLKOSTRUVA_URL", "https://kolkostruva.bg/opendata_files"
    )


settings = Settings()
