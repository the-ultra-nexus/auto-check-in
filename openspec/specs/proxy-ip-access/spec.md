# proxy-ip-access Specification

## Purpose
Site HTTP access can be routed through proxies acquired on demand from configured proxy pools (`CHECK_IN_PROXY_POOL_URLS`) to work around blocked exit IPs; proxy credentials are redacted in all output.

## Requirements
### Requirement: Proxy pool on-demand replenishment
The runtime SHALL accept one or more proxy pool URLs from the `CHECK_IN_PROXY_POOL_URLS` environment variable (comma-separated) and SHALL reject attempts to configure pool URLs in the TOML config file. When a site request needs a proxy and the current batch of proxies is exhausted, the runtime SHALL acquire a fresh batch: fetch the configured pools, parse entries in supported formats (`host:port`, `http(s)://host:port`, or whitespace/tab-separated table rows taking the first two columns), deduplicate by host and port, and quickly probe candidates in parallel with a short timeout, keeping only proxies that return `2xx` or `3xx` and stopping as soon as the batch is full. The runtime SHALL retry the same request through each proxy in the batch, and when a batch is exhausted SHALL acquire the next batch, up to a bounded number of batches. As soon as a request succeeds, the runtime SHALL stop acquiring and keep the successful proxy for subsequent requests. When the batch limit is exhausted, the runtime SHALL raise the last error and the account SHALL fail as `site-unavailable`. When pools cannot be fetched or no proxy can be acquired, the runtime SHALL fall back to a direct connection, log a warning, and SHALL NOT abort the run.

The runtime SHALL prefer a direct connection for the first site request (equivalent to treating the machine's own IP as the first candidate in the pool): with the site's `direct_first` enabled (default `true`), the first request SHALL be attempted directly with a short timeout budget; if it returns `2xx`/`3xx` the runtime SHALL return it and keep the direct connection sticky, without acquiring a batch; only when the direct attempt fails with a transport-level error (`403`/`429`/`5xx`/timeout/connection or TLS failure) SHALL the runtime acquire a batch and retry the same request through it. While the direct connection is sticky, any later transport-level failure SHALL trigger the same acquire-and-retry. With `direct_first` disabled, the runtime SHALL acquire a batch before sending the first request. The `direct_first` flag SHALL be configured per site through the `SITE_CONFIGS` JSON field (e.g. `"direct_first": false`) or the local `SITE_<NAME>_DIRECT_FIRST` environment variable (env takes precedence, matching the `adapter`/`base_url` pattern), and SHALL NOT be accepted from the TOML config file. A batch SHALL be triggered only by transport-level failures; session-level failures (page loads with HTTP `200` but the session is not logged in, or the sign-in submission reports `login-failed`) SHALL NOT trigger pool acquisition and SHALL be handled by clearing stale cookies and re-logging in, reusing the current batch when one is already held. Batches SHALL be isolated per site: each site's session acquires and holds its own batch, rotates within it, and never shares or reuses another site's batch.

#### Scenario: First request tries direct first
- **WHEN** a site request is made and no batch is available, with the site's `direct_first` enabled
- **THEN** the runtime sends the request directly with a short timeout, and acquires a batch only if the direct attempt fails

#### Scenario: Direct success returns without a batch
- **WHEN** the direct first request returns `2xx`/`3xx`
- **THEN** the runtime returns the response and keeps the direct connection for subsequent requests, with no batch acquired

#### Scenario: Direct failure acquires a batch
- **WHEN** the direct first request fails with `403`/`429`/`5xx`/timeout/connection/TLS error
- **THEN** the runtime acquires a batch and retries the same request through it

#### Scenario: Direct-first disabled acquires a batch upfront
- **WHEN** the site's `direct_first` is disabled and no batch is available
- **THEN** the runtime acquires a batch before sending the first request

#### Scenario: Direct-first configured per site
- **WHEN** `SITE_CONFIGS` sets `"direct_first": false` for one site and the local `SITE_<NAME>_DIRECT_FIRST=true` env is set for the same site
- **THEN** the env value wins (`true`) and the site attempts direct first; another site without the flag keeps the default `true`

#### Scenario: Direct-first rejected in TOML
- **WHEN** `direct_first` is written to the TOML config file for a site
- **THEN** configuration fails with a clear error before any network request

#### Scenario: Sticky direct later fails and re-acquires
- **WHEN** a direct connection has been sticky and a later request fails with a transport-level error
- **THEN** the runtime acquires a batch and retries that request through it

#### Scenario: Batches isolated per site
- **WHEN** two site sessions each need a proxy
- **THEN** each session acquires and holds its own independent batch, and neither session reuses the other's proxies

#### Scenario: Login failure does not trigger pool acquisition
- **WHEN** a site request loads successfully (HTTP `200`) but the page shows the session is not logged in (missing formhash / "please log in"), or the sign-in submission reports `login-failed`
- **THEN** the runtime does not acquire a new batch, clears the stale cookies, and re-logins, reusing the current batch when one is already held

#### Scenario: Batch exhausted acquires the next batch
- **WHEN** every proxy in the current batch fails
- **THEN** the runtime fetches the next batch and retries the same request, up to the batch limit

#### Scenario: Success stops and sticks
- **WHEN** a request succeeds through a proxy in a batch
- **THEN** the runtime stops acquiring and keeps that proxy for subsequent requests

#### Scenario: Batch limit exhausted
- **WHEN** all batches fail within the batch limit
- **THEN** the runtime raises the last error and the account fails as `site-unavailable`

#### Scenario: Pool failure falls back to direct
- **WHEN** the pools cannot be fetched or no proxy can be acquired
- **THEN** the runtime connects directly, logs a warning, and continues without aborting the run

#### Scenario: Pool format variants parsed
- **WHEN** a pool line is `1.2.3.4:8080`, `http://1.2.3.4:8080`, or `1.2.3.4 8080 ...` (space or tab separated)
- **THEN** the entry is parsed as the proxy address `http://1.2.3.4:8080`

#### Scenario: Pool URLs rejected in TOML
- **WHEN** proxy pool URLs are written to the TOML config file
- **THEN** configuration fails with a clear error before any network request

### Requirement: Proxy applied to site sessions
The runtime SHALL route every site HTTP session (login and sign-in requests) through proxies acquired on demand from the pool, rotating through the current batch in failover order, and SHALL NOT route notification channel requests through site proxies. When no proxy can be acquired, the runtime SHALL connect directly.

#### Scenario: Session carries proxy
- **WHEN** a site session is created and a batch has been acquired
- **THEN** the session routes both `http` and `https` requests through the acquired proxies

#### Scenario: Proxy rotates on failure
- **WHEN** a request through the current proxy fails
- **THEN** the request is retried through the next proxy in the batch, or the next batch when the current one is exhausted

#### Scenario: Notifications bypass proxy
- **WHEN** a site proxy is configured and a notification is sent
- **THEN** the notification request does not use the site proxy

#### Scenario: Direct connection when no proxy available
- **WHEN** the pool yields no usable proxy for the site
- **THEN** site requests connect directly

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
The runtime SHALL disable environment proxy merging (`trust_env = False`) on site sessions, so ambient shell proxies such as `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` never hijack site traffic. Site requests SHALL use only the proxies acquired from the pool (`CHECK_IN_PROXY_POOL_URLS`) and SHALL connect directly when no proxy is acquired.

#### Scenario: Ambient proxy does not override configured proxy
- **WHEN** the shell environment has `HTTPS_PROXY` set and a site session has acquired proxies
- **THEN** site requests use only the acquired proxies and are not routed through the ambient `HTTPS_PROXY`

#### Scenario: Direct connection when no proxy configured
- **WHEN** no site proxy is acquired but the shell environment has `HTTP_PROXY` / `HTTPS_PROXY` set
- **THEN** site requests connect directly instead of using the ambient environment proxy
