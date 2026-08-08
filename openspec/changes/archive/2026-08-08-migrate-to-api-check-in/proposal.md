## Why

签到流程可以完全用 HTTP 完成：登录与签到两个动作均可通过 `requests.Session` + lxml 复现，站点地址直接由用户配置。为简化运维并减少 GitHub Actions 的总运行时间，本变更实现纯 HTTP 登录+签到，并让多个站点在同一次运行中并行处理，环境数据完全隔离。

## What Changes

- **BREAKING** 适配器改为纯 HTTP 登录+签到：不采集签到统计，不做任何页面渲染依赖。
- **BREAKING** 站点地址必填，直接使用配置的 `base_url`。
- 多站点同进程并行：`CHECK_IN_SITES` 启用站点，每站独立环境变量（`SITE_<NAME>_BASE_URL`、`SITE_<NAME>_ACCOUNTS`）与独立 HTTP 会话；一站失败不影响其他站。
- 规范退出码：0 = 全部成功/已签到，1 = 存在失败，2 = 配置错误；凭据脱敏不进入结果、日志与通知。
- `CheckInAdapter` 协议与 `ADAPTERS` 注册表保留，未来站点沿用同一扩展点。

## Capabilities

### New Capabilities

- `api-only-check-in`: 纯 HTTP 的登录与签到流程。
- `adapter-extension`: 多站点并行编排、环境隔离、注册表与统一结果契约。

### Modified Capabilities

- 无（仓库尚无主规格，本变更以增量规格定义新行为）。

## Impact

- 重写 `auto_check_in/adapters/sijishe.py`；更新 `auto_check_in/config.py`、`auto_check_in/runner.py`（多站点并行）、依赖文件、README 和测试。
- 移除仅用于验证码 OCR 的依赖（当前登录表单无验证码；若未来站点需要，再按新需求引入）。
- GitHub Actions 单 job 内并行执行全部启用站点；每站凭据通过对应 Secret 注入。
