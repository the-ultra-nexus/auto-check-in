"""Adapter contract for every check-in site."""

from __future__ import annotations

from typing import Protocol

from ..config import SiteConfig
from ..models import Account, AccountResult


class CheckInAdapter(Protocol):
    """Contract implemented by every site adapter."""

    def __init__(self, config: SiteConfig) -> None:
        """Create an adapter bound to one site's isolated configuration."""

    def run(self, account: Account) -> AccountResult:
        """Log in and check in one account, returning a sanitized result."""
