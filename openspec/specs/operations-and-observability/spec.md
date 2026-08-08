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

