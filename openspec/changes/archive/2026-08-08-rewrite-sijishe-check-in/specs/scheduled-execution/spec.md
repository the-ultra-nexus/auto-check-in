## ADDED Requirements

### Requirement: GitHub Actions scheduler
The repository SHALL provide a GitHub Actions workflow that supports a daily schedule and manual dispatch for the same CLI entry point.

#### Scenario: Scheduled execution
- **WHEN** the daily cron trigger fires
- **THEN** the workflow installs the locked dependencies, provides repository secrets as environment variables, runs the check-in command, and exposes the exit status

#### Scenario: Manual execution
- **WHEN** an authorized user selects workflow dispatch
- **THEN** the same job runs without requiring code changes or plaintext credentials

### Requirement: Failure observability
The workflow SHALL preserve sanitized command output and fail visibly when any account cannot be checked in.

#### Scenario: Partial account failure
- **WHEN** at least one account result is unsuccessful
- **THEN** the workflow step fails after sending the configured notification and the log contains only account-safe summaries
