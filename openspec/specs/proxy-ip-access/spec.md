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

### Requirement: Proxy failover on proxy failure
When a site request through the current proxy fails because the proxy itself is unreachable (a proxy connection error such as `requests.exceptions.ProxyError`, including connect timeouts to the proxy) or the site rejects the request with an HTTP status that marks the proxy as unusable (`403`, `429`, or any `5xx`), the runtime SHALL retry the same request through the next configured proxy, rotating until a request succeeds or every configured proxy has been attempted. Once a proxy succeeds, the session SHALL keep using it for subsequent requests. Other failures (site-level HTTP errors such as `401`/`404`, or non-proxy request errors) SHALL NOT trigger rotation. When every configured proxy fails, the runtime SHALL raise the last error or return the last rejected response, and the account SHALL fail as `site-unavailable`.

#### Scenario: Failover to the next proxy
- **WHEN** a request through proxy A raises a proxy connection error and proxy B is configured
- **THEN** the same request is retried through proxy B

#### Scenario: Failover on site rejection
- **WHEN** a request through proxy A is rejected with `403`, `429`, or a `5xx` status and proxy B is configured
- **THEN** the same request is retried through proxy B

#### Scenario: Working proxy is sticky
- **WHEN** a request succeeds through proxy B after proxy A failed
- **THEN** subsequent requests in that session use proxy B

#### Scenario: All proxies fail
- **WHEN** every configured proxy fails with a proxy connection error or a rejection status
- **THEN** the runtime raises the last error or returns the last rejected response and the account fails as `site-unavailable`

#### Scenario: No rotation on other site-level failure
- **WHEN** the site returns an HTTP error response such as `401` or `404` through the working proxy
- **THEN** the runtime does not rotate to another proxy

### Requirement: Site sessions ignore ambient environment proxies
The runtime SHALL disable environment proxy merging (`trust_env = False`) on site sessions, so ambient shell proxies such as `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` never hijack site traffic. Site requests SHALL use only the configured proxy list (`SITE_<NAME>_PROXY_URLS` / `CHECK_IN_PROXY_URLS`) and SHALL connect directly when no proxy is configured.

#### Scenario: Ambient proxy does not override configured proxy
- **WHEN** the shell environment has `HTTPS_PROXY` set and a site session is configured with a proxy list
- **THEN** site requests use only the configured proxy and are not routed through the ambient `HTTPS_PROXY`

#### Scenario: Direct connection when no proxy configured
- **WHEN** no site proxy is configured but the shell environment has `HTTP_PROXY` / `HTTPS_PROXY` set
- **THEN** site requests connect directly instead of using the ambient environment proxy
