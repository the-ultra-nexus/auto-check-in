"""Shared adapter error types."""


class LoginError(Exception):
    """Raised when a site login cannot be completed."""


class CheckInError(Exception):
    """Raised when a site sign-in cannot be completed."""


class SiteUnavailableError(Exception):
    """Raised when no usable site endpoint can be reached."""
