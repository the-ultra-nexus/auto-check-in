"""Shared HTTP client helpers (user-agent pool and headers)."""

from __future__ import annotations

import random
from typing import Any, Callable

import requests

from .config import NetworkConfig
from .log import logger
from .pool import MAX_BATCHES, fetch_pool_batch
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
    """A requests.Session with direct-first probing and on-demand proxy batches.

    With ``direct_first`` (default) the first request is attempted directly; on
    success it is returned and the direct connection stays sticky. On a
    transport-level failure (``403``/``429``/``5xx``/timeout/connection/TLS) the
    session acquires a proxy batch from the pool and retries the same request.
    Once a batch is held, rotation happens on proxy connection errors or
    ``ROTATE_STATUS_CODES``; when the batch is exhausted the next batch is
    acquired, up to ``MAX_BATCHES``. The first working proxy is kept (sticky).
    Ambient environment proxies are ignored so site traffic only ever uses the
    direct connection or acquired batch proxies.
    """

    def __init__(
        self,
        proxy_urls: tuple[str, ...] = (),
        initial_proxy: str | None = None,
        direct_first: bool = True,
        pool_fetcher: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__()
        self.trust_env = False
        self._direct_first = direct_first
        self._pool_fetcher = pool_fetcher
        self._batch_count = 0
        self._proxy_urls = proxy_urls
        self._proxy_index = proxy_urls.index(initial_proxy) if initial_proxy in proxy_urls else 0
        if initial_proxy:
            self.proxies = {"http": initial_proxy, "https": initial_proxy}

    def _acquire_batch(self) -> bool:
        """Fetch the next batch of proxies; returns False when unavailable."""
        if self._pool_fetcher is None or self._batch_count >= MAX_BATCHES:
            return False
        self._batch_count += 1
        batch = self._pool_fetcher()
        if not batch:
            logger.warning("代理池未返回可用代理（第 %d 次尝试）", self._batch_count)
            return False
        self._proxy_urls = tuple(batch)
        self._proxy_index = 0
        logger.info("代理批次获取成功 proxies=%d", len(batch))
        return True

    def _direct_request(self, method: str, url: str, args: tuple, kwargs: dict) -> Any:
        """Attempt the request directly; returns (response, failed_reason)."""
        try:
            response = super().request(method, url, *args, **kwargs)
        except requests.RequestException as exc:
            return None, exc
        if response.status_code in ROTATE_STATUS_CODES:
            return response, response.status_code
        return response, None

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        if not self._proxy_urls:
            if self._direct_first:
                response, reason = self._direct_request(method, url, args, kwargs)
                if reason is None:
                    logger.debug("direct-first 成功，粘住直连")
                    return response
                logger.debug(
                    "direct-first 失败（%s），拉取代理批次重试",
                    getattr(reason, "__class__", reason).__name__ if isinstance(reason, Exception) else reason,
                )
                if not self._acquire_batch():
                    logger.warning("代理池不可用，回退直连")
                    if response is not None:
                        return response
                    raise reason  # type: ignore[misc]
            elif not self._acquire_batch():
                logger.warning("代理池不可用，直连兜底")
                return super().request(method, url, *args, **kwargs)

        last_error: requests.RequestException | None = None
        last_response: Any = None
        while self._proxy_urls:
            proxy = self._proxy_urls[self._proxy_index % len(self._proxy_urls)]
            self.proxies = {"http": proxy, "https": proxy}
            try:
                response = super().request(method, url, *args, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                logger.debug(
                    "proxy %s 请求失败（%s），轮换到下一个代理",
                    redact_text(proxy),
                    exc.__class__.__name__,
                )
                self._proxy_index += 1
            else:
                if response.status_code in ROTATE_STATUS_CODES:
                    last_response = response
                    logger.debug(
                        "proxy %s 被站点拒绝 (HTTP %s)，轮换到下一个代理",
                        redact_text(proxy),
                        response.status_code,
                    )
                    self._proxy_index += 1
                else:
                    return response
            if self._proxy_index % len(self._proxy_urls) == 0:
                if not self._acquire_batch():
                    break
        if last_error is not None:
            raise last_error
        if last_response is not None:
            return last_response
        return super().request(method, url, *args, **kwargs)


class SessionProvider:
    """Creates HTTP sessions with direct-first probing and pool-based batches."""

    def __init__(
        self,
        network: NetworkConfig,
        direct_first: bool = True,
        probe_url: str | None = None,
    ):
        self.network = network
        self.direct_first = direct_first
        self.probe_url = probe_url
        self._pool_fetcher: Callable[[], tuple[str, ...]] | None = None
        if network.proxy_pool_urls and probe_url:
            pool_urls = network.proxy_pool_urls
            self._pool_fetcher = lambda: fetch_pool_batch(pool_urls, probe_url)  # type: ignore[arg-type]

    def new_session(self) -> Any:
        session = FailoverSession(
            proxy_urls=(),
            direct_first=self.direct_first,
            pool_fetcher=self._pool_fetcher,
        )
        session.headers.update({"User-Agent": random_user_agent()})
        return session
