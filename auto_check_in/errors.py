"""Shared adapter error types."""


class LoginError(Exception):
    """Raised when a site login cannot be completed."""


class LoginBlockedError(LoginError):
    """Raised when the site rejects the login submission itself (e.g. HTTP 4xx)."""


class CheckInError(Exception):
    """Raised when a site sign-in cannot be completed."""


class SiteUnavailableError(Exception):
    """Raised when no usable site endpoint can be reached."""
