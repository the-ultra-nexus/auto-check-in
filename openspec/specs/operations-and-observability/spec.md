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
- **THEN** a log line contains the site, account, status, and duration

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

