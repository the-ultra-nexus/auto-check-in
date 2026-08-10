# operations-and-observability Specification

## Purpose
TBD - created by archiving change hardening-and-gap-fixes. Update Purpose after archive.
## Requirements
### Requirement: Structured logging
The runtime SHALL emit redacted structured log lines per site and per account using stdlib logging, with level controlled by `CHECK_IN_LOG_LEVEL` or `--debug`.

#### Scenario: Debug logs are redacted
- **WHEN** debug logging is enabled
- **THEN** log lines include sanitized response summaries without passwords, cookies, or CAPTCHA text

#### Scenario: Per-account log line
- **WHEN** an account finishes
- **THEN** a log line contains the site, the masked account username (never the full username), status, and duration

### Requirement: Site-grouped summary
The rendered summary SHALL group account results by site with site headers.

#### Scenario: Two sites in output
- **WHEN** two sites are processed
- **THEN** the rendered output contains separate `【site】` blocks for each site

### Requirement: Manual site selection
The workflow SHALL accept a `workflow_dispatch` sites input that overrides `CHECK_IN_SITES`.

#### Scenario: Manual run with one site
- **WHEN** an operator dispatches the workflow with `sijishe` only
- **THEN** only `sijishe` is processed

### Requirement: Configurable request pacing
The system SHALL support an optional per-account delay (`CHECK_IN_REQUEST_DELAY`, default 3) with small random jitter.

#### Scenario: Delay configured
- **WHEN** `CHECK_IN_REQUEST_DELAY` is greater than zero
- **THEN** the adapter waits between accounts within a site

#### Scenario: Delay disabled
- **WHEN** `CHECK_IN_REQUEST_DELAY` is zero
- **THEN** no artificial wait is inserted

### Requirement: Per-site timing
The runner SHALL record and log the elapsed time of each site.

#### Scenario: Duration logged
- **WHEN** a site finishes processing
- **THEN** its elapsed time appears in the logs

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

### Requirement: Login submission is observable
When a login submission is rejected or debug logging is enabled, the runtime SHALL identify the failed step (dialog fetch, login submit, or sign-in) and SHALL confirm that the login form fields were filled using only field names and fill-state indicators, never credential values.

#### Scenario: Rejected login identifies the step and form state
- **WHEN** the login submission request is rejected
- **THEN** the log and result message identify the login-submit step and confirm the form fields (formhash, username, password) were filled, without printing any credential value

#### Scenario: Debug mode logs the form state
- **WHEN** debug logging is enabled before a login submission
- **THEN** a log line confirms the login form field names and their filled state without credential values

### Requirement: Session cache reuse observability
The runtime SHALL record per-account session-cache events and SHALL aggregate restored / rejected / saved counters into the rendered run summary, with usernames masked and cookie values never logged, so whether cached sessions were actually reused is auditable in logs and notifications.

#### Scenario: Restore hit logged
- **WHEN** an account's cached cookies exist and are loaded
- **THEN** the log records a hit with the masked username and cookie count, and the restored counter increments

#### Scenario: Restore miss logged
- **WHEN** an account has no cached cookies
- **THEN** the log records a miss with the masked username and no cookies are loaded

#### Scenario: Persist saved logged
- **WHEN** an account finishes with an `*_auth` cookie and the session file is written
- **THEN** the log records the save with the masked username and the saved counter increments

#### Scenario: Restored session rejected triggers relogin
- **WHEN** a restored session exists but the sign-in returns `login-failed`
- **THEN** the runtime clears the cookies, re-logins, logs the rejection with the masked username, and increments the rejected counter

#### Scenario: Summary renders cache counters
- **WHEN** the run finishes and the summary is rendered
- **THEN** it includes a fixed-format line with the aggregated restored / rejected / saved counters
