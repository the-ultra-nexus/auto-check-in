## MODIFIED Requirements

### Requirement: Per-account log line
When an account finishes, the runtime SHALL emit a log line containing the site, the masked account username (never the full username), status, and duration.

#### Scenario: Per-account log line with masked username
- **WHEN** an account finishes processing
- **THEN** a log line contains the site, the masked username, status, and duration, and does not contain the full username

### Requirement: Unexpected adapter errors are observable
When a site adapter encounters an unexpected exception, the runtime SHALL log the redacted cause and SHALL include a redacted, truncated cause in the account result message surfaced in the notification. HTTP and network failures SHALL map to a meaningful failure status rather than a generic error, while preserving the redacted detail: HTTP/network failures outside the login submission step (e.g. dialog fetch, sign-in request, connection refused, timeout, TLS failure) SHALL map to `site-unavailable`, while an HTTP 4xx (typically 403) on the login submission step SHALL map to `login-blocked` with an actionable message.

#### Scenario: Unexpected exception logged and surfaced
- **WHEN** an adapter run raises an unexpected exception during check-in
- **THEN** the log contains a redacted description of the exception and the account result message includes the redacted cause instead of only a generic error text

#### Scenario: HTTP failure classified as site unavailable
- **WHEN** the site returns an HTTP error status (e.g. 503) outside the login submission step
- **THEN** the account result uses `site-unavailable` and the message includes the status/detail

#### Scenario: Login submission rejected maps to login blocked
- **WHEN** the site returns an HTTP 4xx status (e.g. 403) on the login submission request
- **THEN** the account result uses `login-blocked` with a message that names the HTTP status and explains likely causes (anti-bot/WAF, blocked egress IP, credentials to verify)

#### Scenario: Credentials never leak
- **WHEN** an exception message or response text contains credential-like values (passwords, cookies, long hex tokens)
- **THEN** the logged and notified content has those values redacted

## ADDED Requirements

### Requirement: Login submission is observable
When a login submission is rejected or debug logging is enabled, the runtime SHALL identify the failed step (dialog fetch, login submit, or sign-in) and SHALL confirm that the login form fields were filled using only field names and fill-state indicators, never credential values.

#### Scenario: Rejected login identifies the step and form state
- **WHEN** the login submission request is rejected
- **THEN** the log and result message identify the login-submit step and confirm the form fields (formhash, username, password) were filled, without printing any credential value

#### Scenario: Debug mode logs the form state
- **WHEN** debug logging is enabled before a login submission
- **THEN** a log line confirms the login form field names and their filled state without credential values
