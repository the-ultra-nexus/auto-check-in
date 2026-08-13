# Notification Channels

> 通知通道注册表：按环境变量启用、纯函数无全局可变状态、每渠道独立超时、并发发送互不影响。
> 唯一实现：`auto_check_in/notify.py`（测试 `tests/test_notify.py`，全库最大测试文件）。

## 架构模式

- 每个通道是一个**纯函数** `def <name>(title: str, content: str) -> None`，
  读取自身环境变量，**缺配置直接 `return`**（不抛错、不启用）。
- `CHANNELS` 元组登记所有通道；`CHANNEL_REQUIREMENTS` 声明每个通道的必需环境变量；
  `active_channels()` 依此计算启用列表。
- 模块**无全局可变状态**：不缓存请求、不记录已发送、不持有连接。
- 新增通道 = 纯函数 + 注册进 `CHANNELS` + 补 `CHANNEL_REQUIREMENTS` + 测试。

## 通用约定

| 约定 | 值/说明 | 参考 |
|------|--------|------|
| 请求超时 | `TIMEOUT = 15` 秒，每渠道独立 | `notify.py` |
| User-Agent | `_headers()` → `random_user_agent()`（http.py 共享） | `notify.py` |
| 布尔解析 | `_truthy()`：`1/true/yes/on`（忽略大小写），用于 `SMTP_SSL` 等标志 | `notify.py` |
| 环境变量读取 | `_env(name)` 空值归一为 `""`，与 `config.py::_env` 同风格 | `notify.py` |

## 发送隔离（send）

- `send(title, content)` 对每个通道起一个 **daemon 线程**并发发送并 `join`；
  单通道异常由 `_safe` 捕获打印（`通知渠道 <name> 发送失败: ...`），**不影响其他渠道，
  不向调用方抛错**（`cli.py` 对 `send` 仍包 try/except 兜底）。
- `SKIP_PUSH_TITLE`：按行匹配标题命中即跳过（如定时任务内重复通知去重）。
- `console` 通道特殊：`CONSOLE` 环境变量必须显式为真值才启用
  （`active_channels` 单独判断，其他通道看必需变量是否非空）。

## SMTP 通道细节（最复杂通道）

- 配置：`SMTP_SERVER`（`host` 或 `host:port`，IPv6 用 `[addr]` 写法）、`SMTP_PORT`（覆盖）、
  `SMTP_SSL` / `SMTP_STARTTLS`、`SMTP_EMAIL`、`SMTP_PASSWORD`、`SMTP_NAME`、
  `SMTP_TO`（缺省 = `SMTP_EMAIL`）。
- **模式探测**（`_smtp_attempts`）：未显式指定 SSL/STARTTLS 时按
  `starttls(587) → ssl(465) → plain(25)` 顺序尝试，连接层失败换下一种；
  `SMTP_PORT` 指定 465/587 时优先对应模式组合。
- **不重试的确定性错误**：`SMTPAuthenticationError` / `SMTPRecipientsRefused` /
  `SMTPSenderRefused` / `SMTPDataError` 直接上抛（`_SMTP_DEFINITIVE_ERRORS`），
  避免对凭据/地址错误做无意义重试。
- STARTTLS 前检查 `has_extn("starttls")`，缺失抛 `SMTPServerDisconnected`。
- 中文标题用 `email.header.Header(title, "utf-8")` + `formataddr`，正文 `MIMEText(content, "plain", "utf-8")`。

## 新增通知渠道流程

1. `notify.py` 加纯函数通道（`_env` 判空 → 直接 return；`requests.post` + `TIMEOUT` + `_headers()`）。
2. 加入 `CHANNELS` 元组与 `CHANNEL_REQUIREMENTS`（必需 env 键）。
3. `.env.example` 登记新变量；若需 CI 透传加 `@ci:secrets` / `@ci:vars` 标记，
   并同步 `.github/workflows/check-in.yml`（`tests/test_github_workflow.py` 会双向校验）。
4. `tests/test_notify.py` 补用例（mock `requests`，验证缺配置不发送 / 载荷正确 / 异常隔离）。

## 反模式

- 通道函数里写全局状态（如模块级 `_sent` 集合）——本库约定纯函数。
- 缺少必需 env 时抛异常代替静默跳过（会污染 `send` 的并发语义）。
- 单通道异常上抛到 `send` 调用方（必须由 `_safe` 隔离）。
- 新增 env 变量不同步 `.env.example` / CI 工作流（CI 校验会失败）。
- 在通道内复用 `FailoverSession` 或代理逻辑——通知流量**不受代理池影响**（README 明确）。
