## ADDED Requirements

### Requirement: Standalone notify-only mode
The CLI SHALL provide a `--notify-only` mode that sends a test notification through all enabled channels without performing check-in, accessing sites, or requiring site credentials.

#### Scenario: Test notification sent
- **WHEN** the user runs `auto-check-in --notify-only` with at least one notification channel enabled
- **THEN** a test notification is sent through every enabled channel, no site is accessed, and no sign-in runs

#### Scenario: No site credentials required
- **WHEN** `--notify-only` runs without `SITE_CONFIGS` or `SITE_*_ACCOUNTS`
- **THEN** the command still sends the test notification using only notification settings

### Requirement: Run-mode flag mutual exclusion
`--notify-only` SHALL be mutually exclusive with `--dry-run` and `--no-notify`.

#### Scenario: Conflicting flags rejected
- **WHEN** `--notify-only` is combined with `--dry-run` or `--no-notify`
- **THEN** the CLI rejects the invocation before any notification is sent

### Requirement: Channel availability reporting
The `--notify-only` mode SHALL report clearly when no notification channel is enabled and SHALL return a non-zero exit code in that case.

#### Scenario: No channels enabled
- **WHEN** `--notify-only` runs with no notification channel environment variables set
- **THEN** the CLI prints an explicit message that no channel is enabled and exits with code 2

#### Scenario: At least one channel enabled
- **WHEN** `--notify-only` runs with one or more channels enabled and no fatal error occurs
- **THEN** the command exits with code 0
