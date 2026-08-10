## ADDED Requirements

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
