"""Multi-site parallel orchestration."""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from .adapters import ADAPTERS
from .config import CheckInConfig, ConfigError, SiteConfig, parse_accounts
from .log import logger
from .models import AccountResult, CheckInStatus, RunSummary


def _run_site(
    site: SiteConfig,
    adapter_types: dict[str, type],
) -> list[AccountResult]:
    adapter = adapter_types[site.adapter](site)
    results: list[AccountResult] = []
    delay = site.network.request_delay_seconds
    site_started = time.perf_counter()
    for index, account in enumerate(parse_accounts(site.accounts)):
        if index > 0 and delay > 0:
            jitter = delay * random.uniform(-0.2, 0.2)
            time.sleep(max(0.0, delay + jitter))
        try:
            started = time.perf_counter()
            result = adapter.run(account)
            elapsed = time.perf_counter() - started
            results.append(replace(result, site=site.name))
            logger.info(
                "site=%s account=%s status=%s duration=%.2fs",
                site.name,
                account.username,
                result.status.value,
                elapsed,
            )
        except Exception:
            results.append(
                AccountResult(
                    account.username,
                    CheckInStatus.ERROR,
                    "账号处理失败",
                    site=site.name,
                )
            )
    logger.info(
        "site=%s finished accounts=%d duration=%.2fs",
        site.name,
        len(results),
        time.perf_counter() - site_started,
    )
    return results


def run(
    config: CheckInConfig,
    adapter_types: dict[str, type] | None = None,
) -> RunSummary:
    """Validate every site first, then process sites concurrently."""
    registry = ADAPTERS if adapter_types is None else adapter_types
    if not config.sites:
        raise ConfigError("没有启用的站点")
    for site in config.sites:
        if site.adapter not in registry:
            raise ConfigError(
                f"不支持的签到适配器: {site.adapter}（站点 {site.name}）"
            )
        parse_accounts(site.accounts)

    results: list[AccountResult] = []
    workers = min(config.max_workers, len(config.sites))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_site, site, registry): site for site in config.sites
        }
        for future in as_completed(futures):
            site = futures[future]
            try:
                results.extend(future.result())
            except Exception:
                results.append(
                    AccountResult(
                        f"<{site.name}>",
                        CheckInStatus.ERROR,
                        "站点运行异常",
                        site=site.name,
                    )
                )
    return RunSummary(results)
