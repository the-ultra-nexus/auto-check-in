"""Command-line entry point used by local runs and GitHub Actions."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .config import ConfigError, load_config, load_notify_settings, parse_accounts
from .log import setup_logging
from .runner import run
from .security import mask_username, redact_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多站点自动签到")
    parser.add_argument("--config", help="TOML 配置文件路径")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只校验配置和账号，不访问站点")
    mode.add_argument("--no-notify", action="store_true", help="不发送通知")
    mode.add_argument("--notify-only", action="store_true", help="只发送测试通知，不签到、不访问站点")
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    return parser


def _notify_only(config_path: str | None) -> int:
    """Send a test notification through enabled channels without check-in or site access."""
    from .notify import active_channels, send

    title, enabled = load_notify_settings(config_path)
    if not enabled:
        print(
            "通知未启用（CHECK_IN_NOTIFY=false 或 [notification] enabled=false）",
            file=sys.stderr,
        )
        return 2
    channels = active_channels()
    if not channels:
        print(
            "未启用任何通知渠道：请先配置 BARK_PUSH / PUSH_KEY / TG_BOT_TOKEN+TG_USER_ID / SMTP_* 等环境变量",
            file=sys.stderr,
        )
        return 2
    content = f"通知测试 {date.today():%m-%d %H:%M}，已启用渠道: {', '.join(channels)}"
    send(f"{title} 通知测试", content)
    print(f"已发送测试通知，启用渠道: {', '.join(channels)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(debug=args.debug)
    try:
        if args.notify_only:
            return _notify_only(args.config)
        config = load_config(args.config)
        if args.dry_run:
            for site in config.sites:
                accounts = parse_accounts(site.accounts)
                masked = ", ".join(mask_username(account.username) for account in accounts)
                print(
                    f"站点[{site.name}] 配置有效，已解析 {len(accounts)} 个账号: {masked}"
                )
            return 0
        summary = run(config)
        output = redact_text(summary.render())
        print(output)
        if config.notify and not args.no_notify:
            try:
                from auto_check_in.notify import send

                title = (
                    f"{config.notification_title} {summary.title_head()} "
                    f"{date.today():%m-%d}"
                )
                send(title, output)
            except Exception as exc:
                print(f"通知发送失败: {exc}", file=sys.stderr)
        return summary.exit_code
    except ConfigError as exc:
        print(f"配置错误: {redact_text(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
