# proxy-ip-access Specification

## Purpose
Site HTTP access can be routed through one or more configured proxy IPs (round-robin per session) to work around blocked exit IPs; proxy credentials are redacted in all output.

## Requirements
### Requirement: Proxy IP configuration
The runtime SHALL accept one or more HTTP/HTTPS proxy addresses from `CHECK_IN_PROXY_URLS` (global) and `SITE_<NAME>_PROXY_URLS` (per-site override, taking precedence), separated by commas, each in the form `http://host:port` or `http://user:pass@host:port`. Invalid entries (unsupported scheme or missing host) SHALL fail configuration with a clear error before any network request.

#### Scenario: Global proxy list parsed
- **WHEN** `CHECK_IN_PROXY_URLS` is `http://1.2.3.4:8080,http://5.6.7.8:3128`
- **THEN** configuration contains two proxy addresses and the site uses them in order

#### Scenario: Per-site proxy overrides global
- **WHEN** `CHECK_IN_PROXY_URLS` is set and `SITE_SIJISHE_PROXY_URLS` is also set
- **THEN** the sijishe site uses only the per-site list

#### Scenario: Invalid proxy URL fails startup
- **WHEN** `CHECK_IN_PROXY_URLS` contains `ftp://1.2.3.4:21`
- **THEN** startup fails with a configuration error before any network request

### Requirement: Proxy applied to site sessions
The runtime SHALL route every site HTTP session (login and sign-in requests) through one of the configured proxy addresses, rotating the choice across sessions in round-robin order, and SHALL NOT route notification channel requests through site proxies.

#### Scenario: Session carries proxy
- **WHEN** a site session is created with one configured proxy
- **THEN** the session routes both `http` and `https` requests through that proxy

#### Scenario: Proxy rotates per session
- **WHEN** three sessions are created with two configured proxies
- **THEN** sessions use proxies in round-robin order (A, B, A)

#### Scenario: Notifications bypass proxy
- **WHEN** a site proxy is configured and a notification is sent
- **THEN** the notification request does not use the site proxy

### Requirement: Proxy credential redaction
The runtime SHALL render proxy addresses containing credentials as `scheme://***@host:port` in logs, error messages, and notification content, never exposing the embedded username or password.

#### Scenario: Redacted in error message
- **WHEN** a connection error message contains `http://user:pass@1.2.3.4:8080`
- **THEN** the rendered message shows `http://***@1.2.3.4:8080` and no credential substring

#### Scenario: Redacted in debug log
- **WHEN** the runtime logs the proxy chosen for a session
- **THEN** the log line contains the masked proxy address and no credential substring
