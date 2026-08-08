## ADDED Requirements

### Requirement: Unexpected adapter errors are observable
When a site adapter encounters an unexpected exception, the runtime SHALL log the redacted cause and SHALL include a redacted, truncated cause in the account result message surfaced in the notification. HTTP and network failures (e.g. HTTP 403/5xx, connection refused, timeout, TLS failure) SHALL map to a meaningful failure status such as `site-unavailable` rather than a generic error, while preserving the redacted detail.

#### Scenario: Unexpected exception logged and surfaced
- **WHEN** an adapter run raises an unexpected exception during check-in
- **THEN** the log contains a redacted description of the exception and the account result message includes the redacted cause instead of only a generic error text

#### Scenario: HTTP failure classified
- **WHEN** the site returns an HTTP error status (e.g. 403 or 503)
- **THEN** the account result uses a meaningful failure status (`site-unavailable` or equivalent) and the message includes the status/detail

#### Scenario: Credentials never leak
- **WHEN** an exception message or response text contains credential-like values (passwords, cookies, long hex tokens)
- **THEN** the logged and notified content has those values redacted
