## ADDED Requirements

### Requirement: Site adapter registry
The system SHALL expose a registry mapping adapter names to implementations so a new site can be added without modifying the runner, result model, notification, or CLI code.

#### Scenario: Register and select a new site
- **WHEN** a new adapter is registered under a unique name and an enabled site selects it
- **THEN** the runner constructs that adapter and processes its accounts

#### Scenario: Unknown adapter name
- **WHEN** an enabled site names an adapter that is not registered
- **THEN** startup fails with a configuration error before any network request

### Requirement: Multi-site parallel orchestration
The system SHALL process enabled sites concurrently within one process, isolating failures so one site does not stop the others.

#### Scenario: Multiple sites in one run
- **WHEN** `CHECK_IN_SITES` enables two sites
- **THEN** the runner processes both sites concurrently, each with its own HTTP session, and aggregates all account results

#### Scenario: One site fails
- **WHEN** one site returns failures
- **THEN** the remaining sites are still processed and the final exit code is 1

#### Scenario: Configurable parallelism
- **WHEN** `CHECK_IN_MAX_WORKERS` is set
- **THEN** the runner uses it as the concurrency limit for sites

### Requirement: Per-site environment isolation
The system SHALL read each enabled site's base URL and credentials from dedicated environment variables (`SITE_<NAME>_BASE_URL`, `SITE_<NAME>_ACCOUNTS`), keeping site data isolated and secrets out of tracked files.

#### Scenario: Distinct site credentials
- **WHEN** two sites are enabled with different `SITE_<NAME>_*` environment values
- **THEN** each site's adapter uses only its own environment values

#### Scenario: Missing per-site credentials
- **WHEN** an enabled site has no `SITE_<NAME>_ACCOUNTS`
- **THEN** startup fails with a configuration error for that site before any network request

### Requirement: Shared result contract
All site adapters SHALL return `AccountResult` with stable `CheckInStatus` values.

#### Scenario: Future adapter returns shared statuses
- **WHEN** a future site adapter completes a run
- **THEN** the runner aggregates its `AccountResult` with the same exit-code and notification behavior

### Requirement: Generic multi-site workflow configuration
The workflow SHALL configure all sites through a single `SITE_CONFIGS` JSON secret, with `CHECK_IN_SITES` selecting all or a subset, without hardcoding site names in the workflow.

#### Scenario: All configured sites run
- **WHEN** `CHECK_IN_SITES` is empty and `SITE_CONFIGS` defines two sites
- **THEN** both sites are enabled

#### Scenario: Subset selection
- **WHEN** `CHECK_IN_SITES` names one of two configured sites
- **THEN** only that site is enabled
