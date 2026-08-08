## ADDED Requirements

### Requirement: HTTP-only login and sign-in
The system SHALL perform login and sign-in through a single HTTP session per account, without collecting sign-in statistics.

#### Scenario: API sign-in for one account
- **WHEN** the runner processes an account through the sijishe adapter
- **THEN** the flow performs HTTP login and sign-in only and returns a stable account result

#### Scenario: No statistics collection
- **WHEN** the sign-in flow completes
- **THEN** the result contains status and sanitized reason only, with no statistics payload

### Requirement: Direct base URL
The system SHALL require each enabled site's base URL from configuration or environment.

#### Scenario: Missing base URL
- **WHEN** `base_url` is not provided for an enabled site
- **THEN** startup fails with a configuration error before any network request

#### Scenario: Sign-in uses configured URL
- **WHEN** a site has a configured `base_url`
- **THEN** all login and sign-in requests use that URL as the site root

### Requirement: Dynamic formhash resolution
The system SHALL parse the sign-in formhash from the sign-in page HTML on every run and use it in the sign-in request.

#### Scenario: Sign-in request uses fresh formhash
- **WHEN** the adapter fetches `k_misign-sign.html`
- **THEN** it extracts `input[name=formhash]` and passes that value to the sign-in endpoint

#### Scenario: Missing formhash
- **WHEN** the sign-in page contains no formhash
- **THEN** the adapter returns `check-in-failed` with an actionable message and does not call the sign-in endpoint

### Requirement: HTTP login flow
The system SHALL log in over HTTP by loading the login dialog, resolving formhash, referer, and loginhash from its form, and submitting credentials through the Discuz login endpoint, retaining session cookies in the shared HTTP session.

#### Scenario: Login success
- **WHEN** the adapter submits valid credentials from the dialog form
- **THEN** the HTTP session retains authentication cookies and the sign-in page is fetched in the same session

#### Scenario: Password submitted as digest
- **WHEN** the adapter submits the login form
- **THEN** the password field contains the MD5 digest of the plaintext password and the plaintext never appears in the request or logs

#### Scenario: Empty login response
- **WHEN** the login POST returns an empty body
- **THEN** the adapter treats it as the expected response and verifies login by fetching the sign-in page in the same session

#### Scenario: Login failure with retry
- **WHEN** the login response does not confirm success
- **THEN** the adapter re-fetches the login dialog and retries within the configured budget, then returns `login-failed`

#### Scenario: Login page unparseable
- **WHEN** formhash, referer, or loginhash cannot be resolved from the login dialog
- **THEN** the adapter returns `login-failed` without submitting credentials

### Requirement: Outcome mapping
The system SHALL map sign-in responses to stable statuses: success, already checked in, invalid session, and failure.

#### Scenario: Already signed in
- **WHEN** the response is an XML fragment containing `今日已签` in its CDATA section
- **THEN** the result status is `already-checked-in`

#### Scenario: Successful sign-in
- **WHEN** the response is an XML fragment whose CDATA text is empty
- **THEN** the result status is `success`

#### Scenario: Session invalid
- **WHEN** the response is a Discuz System Error HTML page
- **THEN** the result status is `login-failed` with a sanitized reason

#### Scenario: Sign-in failure retry
- **WHEN** the first sign-in attempt is not confirmed
- **THEN** the adapter refreshes the sign-in page, resolves a new formhash, and retries once before reporting failure

### Requirement: Exit code contract
The process SHALL exit with 0 when all accounts succeeded or were already checked in, 1 when any account failed, and 2 when configuration is invalid.

#### Scenario: Partial failure
- **WHEN** at least one account result is unsuccessful
- **THEN** the process exits with code 1 after notification

#### Scenario: Configuration error
- **WHEN** required configuration or credentials are missing or invalid
- **THEN** the process exits with code 2 without opening an HTTP session

### Requirement: Credential redaction
Results, logs, and notifications SHALL NOT include passwords, cookies, or CAPTCHA text.

#### Scenario: Redaction verified by tests
- **WHEN** a result is rendered or logged
- **THEN** a redaction test asserts that no credential material is present

### Requirement: Session cache reuse
The system SHALL reuse a valid cached login session and only re-login when the session is invalid or expired.

#### Scenario: Valid cached session skips login
- **WHEN** cached cookies are loaded and the sign-in page confirms a logged-in state
- **THEN** the adapter proceeds directly to sign-in without a login POST

#### Scenario: Invalid session triggers re-login
- **WHEN** sign-in returns `login-failed`
- **THEN** the adapter clears cookies, logs in again once, retries sign-in, and updates the cache
