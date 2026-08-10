"""Domain models shared by adapters and the runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .security import mask_username, redact_text


class CheckInStatus(StrEnum):
    SUCCESS = "success"
    ALREADY_CHECKED_IN = "already-checked-in"
    LOGIN_FAILED = "login-failed"
    LOGIN_BLOCKED = "login-blocked"
    SITE_UNAVAILABLE = "site-unavailable"
    CHECK_IN_FAILED = "check-in-failed"
    CONFIG_ERROR = "config-error"
    ERROR = "error"

    @property
    def successful(self) -> bool:
        return self in {self.SUCCESS, self.ALREADY_CHECKED_IN}

    @property
    def label(self) -> str:
        """Human-readable Chinese label for notifications."""
        return {
            CheckInStatus.SUCCESS: "签到成功",
            CheckInStatus.ALREADY_CHECKED_IN: "今日已签到",
            CheckInStatus.LOGIN_FAILED: "登录失败",
            CheckInStatus.LOGIN_BLOCKED: "登录被拦截",
            CheckInStatus.SITE_UNAVAILABLE: "站点不可用",
            CheckInStatus.CHECK_IN_FAILED: "签到失败",
            CheckInStatus.CONFIG_ERROR: "配置错误",
            CheckInStatus.ERROR: "运行错误",
        }[self]


@dataclass(frozen=True, slots=True)
class Account:
    """Credentials for one account. Never include this object in logs."""

    username: str
    password: str


@dataclass(frozen=True, slots=True)
class AccountResult:
    username: str
    status: CheckInStatus
    message: str = ""
    site: str = ""

    def summary_line(self) -> str:
        suffix = f"：{redact_text(self.message)}" if self.message else ""
        return f"账户[{mask_username(self.username)}] {self.status.label}{suffix}"


@dataclass(slots=True)
class RunSummary:
    results: list[AccountResult] = field(default_factory=list)
    sessions_restored: int = 0
    sessions_rejected: int = 0
    sessions_saved: int = 0

    @property
    def failed(self) -> list[AccountResult]:
        return [result for result in self.results if not result.status.successful]

    @property
    def successful(self) -> bool:
        return bool(self.results) and not self.failed

    @property
    def exit_code(self) -> int:
        return 0 if self.successful else 1

    def render(self) -> str:
        if not self.results:
            return "没有可处理的账号"
        groups: dict[str, list[AccountResult]] = {}
        for result in self.results:
            groups.setdefault(result.site or "未分组", []).append(result)
        lines: list[str] = []
        for site, items in groups.items():
            lines.append(f"【{site}】")
            lines.extend(item.summary_line() for item in items)
        if self.sessions_restored or self.sessions_rejected or self.sessions_saved:
            lines.append(
                f"会话缓存: 恢复 {self.sessions_restored}"
                f" / 被拒重登 {self.sessions_rejected}"
                f" / 新保存 {self.sessions_saved}"
            )
        return "\n".join(lines)

    def title_head(self) -> str:
        """Compact result summary for notification titles."""
        total = len(self.results)
        if not total:
            return "无账号"
        succeeded = total - len(self.failed)
        if self.successful:
            return f"{succeeded}/{total} 成功"
        return f"{len(self.failed)}/{total} 失败"
