"""Resto-AI environment loading with a private project .env as the preferred file."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment(base_dir: str | Path) -> None:
    """Load the project .env first, then legacy runtime settings as fallbacks.

    Values already supplied by the process environment are preserved. The systemd
    unit loads .env.runtime first and .env second, so .env has priority there too.
    """
    root = Path(base_dir)
    load_dotenv(root / ".env", override=False)

    runtime_file = os.getenv("RESTO_ENV_FILE") or str(root / ".env.runtime")
    load_dotenv(runtime_file, override=False)
