"""Command-line entry point used by local runs and GitHub Actions."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .config import ConfigError, load_config, parse_accounts
from .log import setup_logging
from .runner import run
from .security import redact_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多站点自动签到")
    parser.add_argument("--config", help="TOML 配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只校验配置和账号，不访问站点")
    parser.add_argument("--no-notify", action="store_true", help="不发送通知")
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(debug=args.debug)
    try:
        config = load_config(args.config)
        if args.dry_run:
            for site in config.sites:
                accounts = parse_accounts(site.accounts)
                print(f"站点[{site.name}] 配置有效，已解析 {len(accounts)} 个账号")
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
