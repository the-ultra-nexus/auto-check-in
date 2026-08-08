"""Extensible, configuration-driven check-in runtime."""

from .config import CheckInConfig, ConfigError, load_config, parse_accounts
from .models import Account, AccountResult, CheckInStatus, RunSummary
from .runner import run

__all__ = [
    "Account",
    "AccountResult",
    "CheckInConfig",
    "CheckInStatus",
    "ConfigError",
    "RunSummary",
    "load_config",
    "parse_accounts",
    "run",
]
