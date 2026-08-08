"""On-demand proxy batch provider.

Fetches proxy lists from the configured pools, parses entries in the supported
formats, deduplicates by host:port, and quickly probes candidates in parallel
until a small batch is ready (or the candidates are exhausted). The caller
(FailoverSession) acquires a new batch only when the current one is exhausted.
"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Iterable
from urllib.parse import urlsplit

import requests

from .log import logger
from .security import redact_text

BATCH_SIZE = 5
MAX_BATCHES = 5
PROBE_CONNECT_TIMEOUT = 2.0
PROBE_TOTAL_TIMEOUT = 4.0
PROBE_CONCURRENCY = 10
POOL_FETCH_TIMEOUT = 10.0
POOL_MAX_BYTES = 1_048_576
POOL_MAX_ENTRIES = 200

_PROBE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_FIELD_SPLIT_RE = re.compile(r"\s+")


def parse_pool_entry(line: str) -> str | None:
    """Parse one proxy entry into ``http://host:port`` or return ``None``.

    Supports ``host:port``, ``http(s)://host:port``, and whitespace/tab-
    separated table rows whose first two columns are ip and port.
    """
    text = line.strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return text
    fields = _FIELD_SPLIT_RE.split(text)
    if len(fields) >= 2:
        host, port = fields[0], fields[1]
    else:
        host, separator, port = text.partition(":")
        if not separator:
            return None
    if not host or not port.isdigit():
        return None
    return f"http://{host}:{port}"


def _entry_key(entry: str) -> str:
    parsed = urlsplit(entry)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{host}:{port}"


def _fetch_pool(url: str) -> str:
    response = requests.get(url, timeout=POOL_FETCH_TIMEOUT)
    response.raise_for_status()
    data = response.content
    if len(data) > POOL_MAX_BYTES:
        raise ValueError("代理池内容超过 1MB 上限")
    return data.decode("utf-8", errors="replace")


def _parse_pool_text(text: str) -> Iterable[str]:
    for line in text.splitlines():
        for part in line.split(","):
            entry = parse_pool_entry(part)
            if entry is not None:
                yield entry


def _probe_one(proxy_url: str, probe_url: str) -> bool:
    try:
        response = requests.get(
            probe_url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=(PROBE_CONNECT_TIMEOUT, PROBE_TOTAL_TIMEOUT),
            headers={"User-Agent": _PROBE_UA},
            allow_redirects=True,
        )
    except requests.RequestException:
        return False
    return 200 <= response.status_code < 400


def fetch_pool_batch(pool_urls: Iterable[str], probe_url: str) -> tuple[str, ...]:
    """Fetch all pools, parse/dedupe candidates, and probe until a batch is full.

    Returns an empty tuple when no pool yields usable proxies.
    """
    urls = tuple(pool_urls)
    if not urls:
        return ()
    candidates: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as executor:
        futures = {executor.submit(_fetch_pool, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                text = future.result()
            except Exception as exc:
                logger.warning("代理池拉取失败: %s（%s）", redact_text(url), exc)
                continue
            count = 0
            for entry in _parse_pool_text(text):
                key = _entry_key(entry)
                if key in candidates:
                    continue
                candidates[key] = entry
                count += 1
                if count >= POOL_MAX_ENTRIES:
                    break
    if not candidates:
        return ()
    usable: list[str] = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_CONCURRENCY)
    futures = {
        executor.submit(_probe_one, entry, probe_url): entry for entry in candidates.values()
    }
    try:
        for future in concurrent.futures.as_completed(futures):
            entry = futures[future]
            try:
                ok = future.result()
            except Exception:
                ok = False
            if ok:
                usable.append(entry)
                if len(usable) >= BATCH_SIZE:
                    break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if usable:
        logger.info(
            "代理批次获取成功 usable=%d probed=%d",
            len(usable),
            len(futures),
        )
    return tuple(usable)
