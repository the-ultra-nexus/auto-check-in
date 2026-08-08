## ADDED Requirements

### Requirement: Layered non-secret configuration
The system SHALL load non-secret defaults from a versioned TOML template and allow documented environment variables to override runtime settings.

#### Scenario: Use default configuration
- **WHEN** no custom config path is provided
- **THEN** the runner loads the repository template and applies environment overrides

#### Scenario: Invalid configuration
- **WHEN** a required setting has an invalid type or unsupported value
- **THEN** startup fails with a concise validation error before opening a browser

### Requirement: Secret-only credential injection
The system SHALL read account credentials and notification tokens from environment variables or the GitHub Actions Secrets context and SHALL reject real secrets in tracked configuration files.

#### Scenario: GitHub scheduled run
- **WHEN** the workflow starts with `XSIJISHE` configured as a repository secret
- **THEN** the secret is passed to the process through the environment and is not echoed in workflow logs

#### Scenario: Missing credentials
- **WHEN** no credential environment variable is present
- **THEN** the process exits with a configuration error and does not start Selenium

### Requirement: Sensitive artifact protection
The system SHALL prevent credentials, cookies, CAPTCHA images, screenshots, and debug logs from being tracked by default.

#### Scenario: Debug artifacts
- **WHEN** debug capture is enabled for a local run
- **THEN** artifacts are written only to the configured ignored runtime directory
