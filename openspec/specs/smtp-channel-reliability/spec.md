# smtp-channel-reliability Specification

## Purpose
TBD - created by archiving change fix-send-err. Update Purpose after archive.
## Requirements
### Requirement: SMTP host and port configuration
The SMTP channel SHALL derive the connection host and port from `SMTP_SERVER` (accepting `host` or `host:port`), allow an explicit `SMTP_PORT` override, and fall back to the mode default port when neither specifies a port. An invalid port value SHALL produce a clear error message.

#### Scenario: Port embedded in SMTP_SERVER
- **WHEN** `SMTP_SERVER` is `smtp.qq.com:465`
- **THEN** the channel connects to host `smtp.qq.com` on port `465`

#### Scenario: SMTP_PORT overrides server port
- **WHEN** `SMTP_SERVER` is `smtp.example.com` and `SMTP_PORT` is `2525`
- **THEN** the channel connects to port `2525`

#### Scenario: Invalid port value
- **WHEN** `SMTP_PORT` is not a number
- **THEN** the channel reports a clear error and does not attempt to send

### Requirement: SMTP connection modes
The SMTP channel SHALL support implicit TLS via `SMTP_SSL=true` (default port 465) and STARTTLS via `SMTP_STARTTLS=true` (default port 587), and SHALL treat truthy values (`1`, `true`, `yes`, `on`, case-insensitive) as enabled.

#### Scenario: Implicit SSL mode
- **WHEN** `SMTP_SSL=true` is set with no explicit port
- **THEN** the channel uses `SMTP_SSL` on port 465

#### Scenario: STARTTLS mode
- **WHEN** `SMTP_STARTTLS=true` is set with no explicit port
- **THEN** the channel connects with plain SMTP, upgrades via STARTTLS, and uses port 587

#### Scenario: Truthy SSL flag variants
- **WHEN** `SMTP_SSL` is `1`, `yes`, or `TRUE`
- **THEN** the channel uses implicit TLS

### Requirement: Automatic mode fallback
When neither `SMTP_SSL` nor `SMTP_STARTTLS` is enabled, the SMTP channel SHALL try connection modes in order (587 STARTTLS, 465 implicit TLS, 25 plain for an unspecified port) and SHALL fall back to the next mode on connection-level failures so a mismatched flag/server combination still sends. Deterministic failures such as authentication or recipient rejection SHALL NOT trigger a fallback.

#### Scenario: SSL flag mismatch still sends
- **WHEN** no mode flag is set and the server listens on 465 with implicit TLS
- **THEN** the channel first attempts plain/STARTTLS, then successfully sends via implicit TLS on 465

#### Scenario: Connection drops in first mode
- **WHEN** the first mode attempt fails with a connection-level error (e.g. `SMTPServerDisconnected`)
- **THEN** the channel retries with the next mode and sends successfully

#### Scenario: Authentication failure is not retried
- **WHEN** the server rejects the credentials with an authentication error
- **THEN** the channel surfaces the authentication error without trying other connection modes

### Requirement: SMTP recipient configuration
The SMTP channel SHALL send to the optional single recipient address from `SMTP_TO` when set, and SHALL fall back to sending to `SMTP_EMAIL` when `SMTP_TO` is unset, keeping the sender address unchanged.

#### Scenario: Explicit recipient
- **WHEN** `SMTP_EMAIL` is `sender@example.com` and `SMTP_TO` is `recipient@example.com`
- **THEN** the message is sent from `sender@example.com` to `recipient@example.com`

#### Scenario: Fallback to sender
- **WHEN** `SMTP_TO` is not set and `SMTP_EMAIL` is `sender@example.com`
- **THEN** the message is sent to `sender@example.com`, preserving current behavior

#### Scenario: Sender unchanged with recipient set
- **WHEN** `SMTP_TO` is set to a different address than `SMTP_EMAIL`
- **THEN** the `From` header remains `SMTP_EMAIL` and only the `To` header uses `SMTP_TO`
