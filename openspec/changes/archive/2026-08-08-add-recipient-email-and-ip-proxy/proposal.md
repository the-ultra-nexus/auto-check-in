## Why

- SMTP 通知目前只能把结果发给发件人自己（`message["To"] = SMTP_EMAIL`），无法指定独立收件人，需要增加一个可选收件人邮箱。
- 站点（xsijishe.net，Cloudflare 前置）可能封禁 GitHub Actions 出口 IP，导致登录被拦截（`login-blocked`）。需要先支持「配置代理 IP 访问站点」来验证是否 IP 问题，再决定后续代理池/隧道方案。

## What Changes

- SMTP 通道新增可选环境变量 `SMTP_TO`：单收件人，未设置时回退到 `SMTP_EMAIL`（向后兼容，现有配置无需修改）。
- 站点 HTTP 访问新增代理支持：通过环境变量配置一个或多个代理地址（`http://host:port` 或 `http://user:pass@host:port`），每次会话选择一个代理出口访问站点。
- 代理列表支持全局与站点级两层配置（沿用现有 `[network]` / `[sites.<name>.network]` + 环境变量覆盖模式）；代理凭据属于敏感信息，只从环境变量/GitHub Secret 读取，禁止写入 TOML。
- 日志与结果中的代理地址做凭据脱敏，避免 `user:pass@` 泄漏。
- 代理只作用于站点流量（登录+签到），通知渠道不走代理。
- 本次只支持「手动配置代理 IP 列表」用于验证；代理池 API 拉取、隧道代理接入不在本次范围（验证确认后再决策）。

## Capabilities

### New Capabilities
- `proxy-ip-access`: 站点 HTTP 访问可配置一个或多个代理 IP，按会话选择出口，且代理凭据在日志/结果中脱敏

### Modified Capabilities
- `smtp-channel-reliability`: SMTP 通道新增可选收件人配置（`SMTP_TO`，缺省为发件人自身）

## Impact

- `auto_check_in/notify.py`: `smtp()` 收件人取值（`SMTP_TO` 缺省回退 `SMTP_EMAIL`）
- `auto_check_in/config.py`: `NetworkConfig` 增加代理列表字段与解析/校验
- `auto_check_in/http.py`: `SessionProvider` 为会话应用代理
- `auto_check_in/security.py`: 增加代理地址凭据脱敏
- `config/check-in.toml`: 说明非敏感的代理配置键（敏感值走环境变量）
- `.github/workflows/check-in.yml`: 透传 `SMTP_TO` 与代理相关 Secrets
- `README.md`: 收件人配置与代理试用说明
- 测试: `tests/test_notify.py`（收件人）、`tests/test_common.py`（配置解析）、新增 HTTP 代理相关用例
