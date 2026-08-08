# smtp-channel-reliability Specification (Delta)

## ADDED Requirements

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
