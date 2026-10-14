"""Settings come from environment variables; there is no config file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    model: str
    top_k: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=Path(os.environ.get("BRAIN_DB", "brain.db")).expanduser(),
            model=os.environ.get("BRAIN_MODEL", DEFAULT_MODEL),
            top_k=int(os.environ.get("BRAIN_TOP_K", "6")),
        )


def make_client() -> Anthropic:
    """Create the Claude client lazily so search/ingest never need the SDK or a key."""
    from anthropic import Anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set; it is needed for `ask` only")
    return Anthropic()
