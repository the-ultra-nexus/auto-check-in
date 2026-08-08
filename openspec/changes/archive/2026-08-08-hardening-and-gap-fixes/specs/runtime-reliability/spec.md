## ADDED Requirements

### Requirement: Packaged notification module
The system SHALL deliver notification sending inside the installable package so the installed CLI can import it from any working directory.

#### Scenario: Installed CLI imports notifications
- **WHEN** the installed `auto-check-in` entry point runs outside the repository root
- **THEN** the notification module imports successfully from the package

### Requirement: Notification failure isolation
The system SHALL keep the process exit code driven by sign-in results even when notification delivery fails, and SHALL NOT append an external quote API response to the notification payload.

#### Scenario: Notification raises
- **WHEN** `send` raises an exception
- **THEN** the CLI prints a warning and returns the sign-in exit code unchanged

#### Scenario: No external quote appended
- **WHEN** a notification is sent
- **THEN** the payload contains no quote fetched from an external API

### Requirement: Bounded channel delivery
The notification module SHALL send through each enabled channel with a per-channel timeout and without module-level mutable configuration or a print monkeypatch.

#### Scenario: Channel timeout
- **WHEN** a channel request does not respond
- **THEN** delivery returns or raises within the configured timeout and the sign-in exit code is unchanged

#### Scenario: Multiple channels
- **WHEN** several channel environment variables are set
- **THEN** each channel is invoked with its own configuration snapshot

### Requirement: Workflow session cache correctness
The workflow SHALL restore the latest session cache and save a fresh entry without same-key collisions.

#### Scenario: Consecutive daily runs
- **WHEN** a second daily run restores the previous cache
- **THEN** it saves the updated cache under a new unique key and does not fail the job

### Requirement: Dry-run adapter validation
The `--dry-run` mode SHALL validate adapter registration and account formats before reporting success.

#### Scenario: Unknown adapter in dry-run
- **WHEN** an enabled site names an unregistered adapter and `--dry-run` is used
- **THEN** the process exits with configuration error without network access

### Requirement: Shared session provider
Adapters SHALL obtain HTTP sessions from a shared provider that applies a randomly selected user agent from the shared pool, timeouts, and retry defaults.

#### Scenario: Adapter uses provider
- **WHEN** an adapter creates a session through the provider
- **THEN** the session carries a user agent selected from the shared pool and network timeout defaults from configuration

### Requirement: Shared user-agent pool
HTTP sessions and notification channel requests SHALL select their user agent from the same built-in pool on each request, and SHALL NOT require user-agent configuration or define an independent hardcoded value.

#### Scenario: Random selection
- **WHEN** an HTTP session or notification request is created
- **THEN** its `User-Agent` header is one of the entries in the shared pool

#### Scenario: No configuration required
- **WHEN** no user-agent setting is provided
- **THEN** requests still send a valid user agent from the shared pool

### Requirement: Config validation completeness
Unknown configuration keys SHALL be reported as warnings, and required-value or type errors SHALL be aggregated across sites and reported together before any network activity.

#### Scenario: Multiple invalid sites
- **WHEN** two enabled sites both lack required values
- **THEN** startup reports both errors in a single configuration failure

#### Scenario: Unknown keys
- **WHEN** configuration contains unknown keys
- **THEN** the loader prints warnings and continues

### Requirement: Session cache staleness
Session cache entries SHALL store a saved timestamp, and entries older than `CHECK_IN_SESSION_MAX_AGE` SHALL be treated as invalid and re-login performed.

#### Scenario: Expired cache
- **WHEN** a cached session is older than the configured maximum age
- **THEN** the adapter ignores it and logs in again

### Requirement: Planning documents reflect runtime
The planning documents SHALL describe the persistent session cache and the generic multi-site workflow configuration.

#### Scenario: Session cache documented
- **WHEN** reading the migrated change design and specs
- **THEN** they cover `.runtime/sessions` reuse and re-login fallback

#### Scenario: Multi-site workflow documented
- **WHEN** reading the migrated change design and specs
- **THEN** they cover `SITE_CONFIGS` JSON and `CHECK_IN_SITES` selection
