## ADDED Requirements

### Requirement: Configurable check-in runtime
The system SHALL run all configured accounts through a common runner and a site adapter selected by configuration.

#### Scenario: Process multiple accounts independently
- **WHEN** the credential payload contains multiple valid accounts separated by `@` or newline
- **THEN** the runner attempts each account independently and produces one result per account

#### Scenario: One account fails
- **WHEN** an account has invalid credentials or its site interaction fails
- **THEN** the runner records a failure result for that account, continues with remaining accounts, and returns a non-zero process status after the run

### Requirement: Stable account result contract
The system SHALL expose a stable status and sanitized message for every account without including passwords, cookies, CAPTCHA data, or raw HTTP bodies.

#### Scenario: Successful sign-in
- **WHEN** the adapter confirms a new sign-in
- **THEN** the result status is `SUCCESS` and includes available sign-in statistics

#### Scenario: Already signed in
- **WHEN** the sign-in page indicates the account has already signed in today
- **THEN** the result status is `ALREADY_CHECKED_IN`

### Requirement: Bounded external interactions
The system SHALL apply configured timeouts and bounded retries to discovery, login, CAPTCHA retrieval, and page waits.

#### Scenario: Site cannot be reached
- **WHEN** all discovery candidates fail within the retry budget
- **THEN** the adapter returns `SITE_UNAVAILABLE` with a user-actionable summary and does not loop indefinitely

### Requirement: Adapter extension point
The system SHALL allow a new site adapter to be added without changing runner, account parsing, result aggregation, or notification code.

#### Scenario: Select a future adapter
- **WHEN** configuration names a registered adapter
- **THEN** the factory constructs that adapter with the shared runtime configuration
