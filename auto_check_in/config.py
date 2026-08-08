"""Validated configuration and credential parsing for multi-site runs."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .log import logger
from .models import Account

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "check-in.toml"
_SITE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_NETWORK_KEYS = {"request_timeout_seconds", "retries", "retry_delay_seconds", "request_delay_seconds"}
_TOP_LEVEL_KEYS = {"runtime", "notification", "sites", "network", "enabled_sites", "max_workers", "session_cache", "session_dir", "session_max_age_seconds", "notification_title", "notify"}
_RUNTIME_KEYS = {"enabled_sites", "max_workers", "session_cache", "session_dir", "session_max_age_seconds"}
_NOTIFICATION_KEYS = {"title", "enabled"}
_SITE_KEYS = {"adapter", "base_url", "sign_path", "network"}


class ConfigError(ValueError):
    """Raised when configuration or credentials cannot be used safely."""


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    request_timeout_seconds: int = 15
    retries: int = 3
    retry_delay_seconds: float = 3.0
    request_delay_seconds: float = 3.0


@dataclass(frozen=True, slots=True)
class SiteConfig:
    name: str
    adapter: str
    base_url: str
    accounts: str
    sign_path: str = "/k_misign-sign.html"
    network: NetworkConfig = NetworkConfig()
    session_cache: bool = True
    session_dir: Path = Path(".runtime/sessions")
    session_max_age_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class CheckInConfig:
    sites: tuple[SiteConfig, ...]
    max_workers: int = 4
    notification_title: str = "签到"
    notify: bool = True


def _env(environ: Mapping[str, str], name: str, default: str = "") -> str:
    value = environ.get(name)
    return value if value is not None and value != "" else default


def _bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} 必须是 true 或 false")


def _positive_int(value: object, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} 必须是正整数") from exc
    if result <= 0:
        raise ConfigError(f"{name} 必须是正整数")
    return result


def _warn_unknown(section: str, data: Mapping[str, object], allowed: set[str]) -> None:
    for key in data:
        if key not in allowed:
            logger.warning("配置警告: %s 中存在未知键 %s", section, key)


def _site_env_prefix(name: str) -> str:
    if not _SITE_NAME_RE.fullmatch(name):
        raise ConfigError(f"站点名只能包含字母、数字和下划线: {name}")
    return f"SITE_{name.upper().replace('-', '_')}_"


def parse_accounts(payload: str | None) -> tuple[Account, ...]:
    """Parse ``username&password`` entries without logging the payload."""
    if not payload or not payload.strip():
        raise ConfigError("未设置账号凭据，请配置 SITE_<NAME>_ACCOUNTS")
    accounts: list[Account] = []
    for index, raw in enumerate(re.split(r"[@\r\n]+", payload)):
        value = raw.strip()
        if not value:
            continue
        username, separator, password = value.partition("&")
        if not separator or not username.strip() or not password:
            raise ConfigError(f"第 {index + 1} 个账号格式错误，应为 账号&密码")
        accounts.append(Account(username.strip(), password))
    if not accounts:
        raise ConfigError("没有可处理的账号")
    return tuple(accounts)


def _network_from(raw: Mapping[str, object], env: Mapping[str, str]) -> NetworkConfig:
    network = NetworkConfig(
        request_timeout_seconds=_positive_int(
            _env(env, "CHECK_IN_REQUEST_TIMEOUT", str(raw.get("request_timeout_seconds", 15))),
            "CHECK_IN_REQUEST_TIMEOUT",
        ),
        retries=_positive_int(
            _env(env, "CHECK_IN_RETRIES", str(raw.get("retries", 3))),
            "CHECK_IN_RETRIES",
        ),
        retry_delay_seconds=float(
            _env(env, "CHECK_IN_RETRY_DELAY", str(raw.get("retry_delay_seconds", 3.0)))
        ),
        request_delay_seconds=float(
            _env(env, "CHECK_IN_REQUEST_DELAY", str(raw.get("request_delay_seconds", 3.0)))
        ),
    )
    if network.request_delay_seconds < 0:
        raise ConfigError("CHECK_IN_REQUEST_DELAY 不能为负数")
    return network


def load_config(
    path: str | Path | None = None, environ: Mapping[str, str] | None = None
) -> CheckInConfig:
    """Load multi-site configuration from TOML defaults plus environment isolation."""
    env = os.environ if environ is None else environ
    config_path = Path(path or env.get("AUTO_CHECK_IN_CONFIG", str(DEFAULT_CONFIG_PATH)))
    raw: dict = {}
    if config_path.exists():
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"配置文件无法读取: {config_path}") from exc

    _warn_unknown("顶层", raw, _TOP_LEVEL_KEYS)

    runtime_raw = raw.get("runtime", {}) if isinstance(raw.get("runtime"), dict) else {}
    _warn_unknown("runtime", runtime_raw, _RUNTIME_KEYS)
    notification_raw = raw.get("notification", {}) if isinstance(raw.get("notification"), dict) else {}
    _warn_unknown("notification", notification_raw, _NOTIFICATION_KEYS)
    global_network_raw = raw.get("network", {}) if isinstance(raw.get("network"), dict) else {}
    _warn_unknown("network", global_network_raw, _NETWORK_KEYS)
    site_configs: dict[str, dict] = {}
    site_configs_raw = _env(env, "SITE_CONFIGS", "")
    if site_configs_raw:
        try:
            parsed = json.loads(site_configs_raw)
        except json.JSONDecodeError as exc:
            raise ConfigError("SITE_CONFIGS 必须是合法 JSON 对象") from exc
        if not isinstance(parsed, dict):
            raise ConfigError("SITE_CONFIGS 必须是 JSON 对象")
        site_configs = {str(name): value for name, value in parsed.items() if isinstance(value, dict)}
    enabled = _env(env, "CHECK_IN_SITES", "")
    if not enabled and site_configs:
        enabled = ",".join(site_configs)
    if not enabled:
        configured = runtime_raw.get("enabled_sites", raw.get("enabled_sites"))
        enabled = ",".join(str(item) for item in configured) if configured else ""
    site_names = [name.strip() for name in enabled.split(",") if name.strip()]
    if not site_names:
        raise ConfigError("未启用任何站点，请配置 CHECK_IN_SITES、[runtime] enabled_sites 或 SITE_CONFIGS")

    sites_raw = raw.get("sites", {})
    session_cache = _bool(
        _env(
            env,
            "CHECK_IN_SESSION_CACHE",
            str(runtime_raw.get("session_cache", raw.get("session_cache", True))),
        ),
        "CHECK_IN_SESSION_CACHE",
    )
    session_dir = Path(
        _env(
            env,
            "CHECK_IN_SESSION_DIR",
            str(runtime_raw.get("session_dir", raw.get("session_dir", ".runtime/sessions"))),
        )
    )
    session_max_age_seconds = float(
        _env(
            env,
            "CHECK_IN_SESSION_MAX_AGE",
            str(runtime_raw.get("session_max_age_seconds", raw.get("session_max_age_seconds", 0.0))),
        )
    )
    if session_max_age_seconds < 0:
        raise ConfigError("CHECK_IN_SESSION_MAX_AGE 不能为负数")
    sites: list[SiteConfig] = []
    errors: list[str] = []
    for name in site_names:
        try:
            prefix = _site_env_prefix(name)
            section = sites_raw.get(name, {}) if isinstance(sites_raw, dict) else {}
            _warn_unknown(f"sites.{name}", section, _SITE_KEYS)
            json_cfg = site_configs.get(name, {})
            adapter = _env(
                env,
                f"{prefix}ADAPTER",
                str(json_cfg.get("adapter") or section.get("adapter", name)),
            )
            base_url = _env(
                env,
                f"{prefix}BASE_URL",
                str(json_cfg.get("base_url") or section.get("base_url", "")),
            ).rstrip("/")
            accounts = _env(env, f"{prefix}ACCOUNTS", str(json_cfg.get("accounts") or ""))
            if not base_url:
                raise ConfigError(f"站点 {name} 缺少 base_url，请配置 {prefix}BASE_URL")
            if not accounts:
                raise ConfigError(f"站点 {name} 缺少账号凭据，请配置 {prefix}ACCOUNTS")
            sign_path = str(json_cfg.get("sign_path") or section.get("sign_path", "/k_misign-sign.html"))
            site_network_raw = section.get("network", {}) if isinstance(section.get("network"), dict) else {}
            _warn_unknown(f"sites.{name}.network", site_network_raw, _NETWORK_KEYS)
            merged_network = {**global_network_raw, **site_network_raw}
            sites.append(
                SiteConfig(
                    name=name,
                    adapter=adapter,
                    base_url=base_url,
                    accounts=accounts,
                    sign_path=sign_path,
                    network=_network_from(merged_network, env),
                    session_cache=session_cache,
                    session_dir=session_dir,
                    session_max_age_seconds=session_max_age_seconds,
                )
            )
        except ConfigError as exc:
            errors.append(str(exc))
    if errors:
        raise ConfigError("配置错误：\n" + "\n".join(errors))

    max_workers = _positive_int(
        _env(
            env,
            "CHECK_IN_MAX_WORKERS",
            str(runtime_raw.get("max_workers", raw.get("max_workers", 4))),
        ),
        "CHECK_IN_MAX_WORKERS",
    )
    return CheckInConfig(
        sites=tuple(sites),
        max_workers=max_workers,
        notification_title=str(
            notification_raw.get("title", raw.get("notification_title", "签到"))
        ),
        notify=_bool(
            _env(
                env,
                "CHECK_IN_NOTIFY",
                str(notification_raw.get("enabled", raw.get("notify", True))),
            ),
            "CHECK_IN_NOTIFY",
        ),
    )
