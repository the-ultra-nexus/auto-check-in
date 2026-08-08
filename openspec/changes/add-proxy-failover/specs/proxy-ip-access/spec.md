## ADDED Requirements

### Requirement: Proxy failover on connection failure
When a site request through the current proxy fails because the proxy itself is unreachable (a proxy connection error such as `requests.exceptions.ProxyError`, including connect timeouts to the proxy), the runtime SHALL retry the same request through the next configured proxy, rotating until a request succeeds or every configured proxy has been attempted. Once a proxy succeeds, the session SHALL keep using it for subsequent requests. Non-proxy failures (site-level HTTP errors or other request errors) SHALL NOT trigger rotation. When every configured proxy fails, the runtime SHALL raise the last error and the account SHALL fail as `site-unavailable`.

#### Scenario: Failover to the next proxy
- **WHEN** a request through proxy A raises a proxy connection error and proxy B is configured
- **THEN** the same request is retried through proxy B

#### Scenario: Working proxy is sticky
- **WHEN** a request succeeds through proxy B after proxy A failed
- **THEN** subsequent requests in that session use proxy B

#### Scenario: All proxies fail
- **WHEN** every configured proxy raises a proxy connection error
- **THEN** the runtime raises the last error and the account fails as `site-unavailable`

#### Scenario: No rotation on site-level failure
- **WHEN** the site returns an HTTP error response through the working proxy
- **THEN** the runtime does not rotate to another proxy

### Requirement: Site sessions ignore ambient environment proxies
The runtime SHALL disable environment proxy merging (`trust_env = False`) on site sessions, so ambient shell proxies such as `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` never hijack site traffic. Site requests SHALL use only the configured proxy list (`SITE_<NAME>_PROXY_URLS` / `CHECK_IN_PROXY_URLS`) and SHALL connect directly when no proxy is configured.

#### Scenario: Ambient proxy does not override configured proxy
- **WHEN** the shell environment has `HTTPS_PROXY` set and a site session is configured with a proxy list
- **THEN** site requests use only the configured proxy and are not routed through the ambient `HTTPS_PROXY`

#### Scenario: Direct connection when no proxy configured
- **WHEN** no site proxy is configured but the shell environment has `HTTP_PROXY` / `HTTPS_PROXY` set
- **THEN** site requests connect directly instead of using the ambient environment proxy
