"""Environment-backed server settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> Settings:
        env_file = os.getenv("OTTERAI_MCP_ENV_FILE")
        load_dotenv(env_file) if env_file else load_dotenv()
        username = os.getenv("OTTERAI_USERNAME") or os.getenv("OTTER_USERNAME")
        password = os.getenv("OTTERAI_PASSWORD") or os.getenv("OTTER_PASSWORD")
        if not username or not password:
            raise RuntimeError(
                "set OTTERAI_USERNAME and OTTERAI_PASSWORD, or configure "
                "OTTERAI_MCP_ENV_FILE"
            )
        return cls(username=username, password=password)

