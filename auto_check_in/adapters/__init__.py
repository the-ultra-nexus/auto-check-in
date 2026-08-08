"""Site-specific adapters."""

from __future__ import annotations

from .base import CheckInAdapter
from .sijishe import SijisheAdapter

ADAPTERS: dict[str, type[CheckInAdapter]] = {"sijishe": SijisheAdapter}

__all__ = ["ADAPTERS", "CheckInAdapter", "SijisheAdapter"]
