"""Site-specific adapters."""

from __future__ import annotations

from .base import CheckInAdapter
from .sijishe_browser import SijisheBrowserAdapter

ADAPTERS: dict[str, type[CheckInAdapter]] = {"sijishe-browser": SijisheBrowserAdapter}

__all__ = ["ADAPTERS", "CheckInAdapter", "SijisheBrowserAdapter"]
