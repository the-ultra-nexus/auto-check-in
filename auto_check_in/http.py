"""Shared HTTP client helpers (user-agent pool and headers)."""

from __future__ import annotations

import random
from typing import Any

import requests

from .config import NetworkConfig
from .log import logger
from .security import redact_text

USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
)


def random_user_agent() -> str:
    """Pick a random user agent from the shared pool."""
    return random.choice(USER_AGENTS)


def ua_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Request headers with a freshly randomized user agent."""
    headers = {"User-Agent": random_user_agent()}
    if extra:
        headers.update(extra)
    return headers


# 命中这些 HTTP 状态码即视为当前代理不可用并轮换：
# 403 站点/WAF 拒绝出口 IP，429 限流，5xx 多为代理上游或目标故障。
ROTATE_STATUS_CODES = frozenset({403, 429, *range(500, 600)})


class FailoverSession(requests.Session):
    """A requests.Session that retries through the next proxy on proxy failure.

    Once a proxy works it is kept for subsequent requests (sticky); rotation
    happens when the current proxy raises a proxy connection error
    (``requests.exceptions.ProxyError``) or the site rejects the request with an
    HTTP status in ``ROTATE_STATUS_CODES`` (``403`` / ``429`` / ``5xx``). When
    every proxy fails, the last error is raised or the last rejected response is
    returned, and the caller's existing failure handling (``site-unavailable``)
    applies. Ambient environment proxies (``HTTP_PROXY`` / ``HTTPS_PROXY`` /
    ``ALL_PROXY``) are ignored so site traffic only ever uses the configured
    proxy list.
    """

    def __init__(
        self,
        proxy_urls: tuple[str, ...] = (),
        initial_proxy: str | None = None,
    ) -> None:
        super().__init__()
        self.trust_env = False
        self._proxy_urls = proxy_urls
        self._proxy_index = proxy_urls.index(initial_proxy) if initial_proxy in proxy_urls else 0
        if initial_proxy:
            self.proxies = {"http": initial_proxy, "https": initial_proxy}

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        if not self._proxy_urls:
            return super().request(method, url, *args, **kwargs)
        last_error: requests.exceptions.ProxyError | None = None
        last_response: Any = None
        for _ in range(len(self._proxy_urls)):
            proxy = self._proxy_urls[self._proxy_index % len(self._proxy_urls)]
            self.proxies = {"http": proxy, "https": proxy}
            try:
                response = super().request(method, url, *args, **kwargs)
            except requests.exceptions.ProxyError as exc:
                last_error = exc
                logger.debug("proxy %s 连接失败，轮换到下一个代理", redact_text(proxy))
                self._proxy_index += 1
                continue
            if response.status_code in ROTATE_STATUS_CODES:
                last_response = response
                logger.debug(
                    "proxy %s 被站点拒绝 (HTTP %s)，轮换到下一个代理",
                    redact_text(proxy),
                    response.status_code,
                )
                self._proxy_index += 1
                continue
            return response
        if last_error is not None:
            raise last_error
        assert last_response is not None
        return last_response


class SessionProvider:
    """Creates HTTP sessions with shared UA/timeout defaults."""

    def __init__(self, network: NetworkConfig):
        self.network = network
        self._proxy_index = 0

    def _next_proxy(self) -> str | None:
        """Pick the next proxy URL in round-robin order, or ``None`` when unset."""
        proxies = self.network.proxy_urls
        if not proxies:
            return None
        proxy = proxies[self._proxy_index % len(proxies)]
        self._proxy_index += 1
        return proxy

    def new_session(self) -> Any:
        proxy = self._next_proxy()
        session = FailoverSession(self.network.proxy_urls, initial_proxy=proxy)
        session.headers.update({"User-Agent": random_user_agent()})
        if proxy:
            logger.debug("session proxy=%s", redact_text(proxy))
        return session
