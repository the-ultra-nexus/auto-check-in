## 1. 仓库内改动

- [x] 1.1 更新 `README.md` 中 `SITE_CONFIGS` 示例，从 `sijishe` 条目删除 `"adapter": "sijishe"` 字段
- [x] 1.2 在 `tests/test_common.py` 的 `test_site_configs_json` 中补充断言：`SITE_CONFIGS` 省略 `adapter` 的站点回退为站点同名适配器（`config.sites[0].adapter == "sijishe"`）

## 2. 自动化验证

- [x] 2.1 运行 `uv run pytest`，确认配置解析与现有测试全部通过

## 3. Secret 更新与集成验证

- [x] 3.1 用去掉 `"adapter": "sijishe"` 的新 JSON 运行 `uv run auto-check-in --dry-run`，确认站点解析为 `adapter=sijishe` 且无配置错误
- [x] 3.2 用 `gh secret set SITE_CONFIGS` 将新 JSON 覆写到仓库 Secret
- [x] 3.3 手动触发 GitHub Actions workflow（`workflow_dispatch`）验证签到与通知正常

## 4. 本地单独运行通知（--notify-only）

- [x] 4.1 在 `auto_check_in/cli.py` 的 `build_parser()` 新增 `--notify-only` 参数，并与 `--dry-run`、`--no-notify` 互斥
- [x] 4.2 在 `main()` 实现 `--notify-only`：仅读取通知相关配置（标题、开关），不要求站点凭据、不访问站点，向所有已启用渠道发送测试通知
- [x] 4.3 新增单元测试：`--notify-only` 不访问站点、发送测试通知、无渠道启用时提示并返回退出码 2
- [x] 4.4 更新 `README.md` 记录 `--notify-only` 用法
- [x] 4.5 运行 `uv run auto-check-in --notify-only`，本地验证各通知渠道送达
