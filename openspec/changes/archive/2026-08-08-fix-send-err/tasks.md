## 1. SMTP 通道加固

- [x] 1.1 在 `auto_check_in/notify.py` 新增 `_parse_smtp_server`：解析 `SMTP_SERVER` 的 `host` / `host:port` / `[ipv6]:port`，端口非法时报清晰错误
- [x] 1.2 新增 `_smtp_attempts`：按 `SMTP_SSL` / `SMTP_STARTTLS` / 自动模式生成有序 `(mode, port)` 连接尝试列表，端口优先级 `SMTP_PORT` > `SMTP_SERVER` 内嵌端口 > 模式默认（ssl=465 / starttls=587 / plain=25）
- [x] 1.3 新增 `_smtp_send`：按模式连接（`SMTP_SSL` 隐式 TLS，或 `SMTP` + `ehlo` + `starttls(context=ssl.create_default_context())`），`login` + `sendmail`，退出时 `quit`/`close` 兜底
- [x] 1.4 重写 `smtp()`：宽松真值解析 `SMTP_SSL` / `SMTP_STARTTLS`（`1/true/yes/on`，大小写不敏感）；连接层错误（`SMTPServerDisconnected`/`OSError`/`TimeoutError`/`ssl.SSLError`）回退下一种模式，认证/收件人拒绝等确定性错误（`SMTPAuthenticationError`/`SMTPRecipientsRefused`/`SMTPSenderRefused`/`SMTPDataError`）立即抛出不重试；全部失败时抛出最后一次错误
- [x] 1.5 `.github/workflows/check-in.yml` 的 `env` 增加 `SMTP_STARTTLS`、`SMTP_PORT` secrets 透传
- [x] 1.6 README 更新 SMTP 配置：`SMTP_SERVER` 支持 `host:port`、`SMTP_PORT`、`SMTP_STARTTLS`、三种连接方式与自动回退说明

## 2. 签到错误可观测性

- [x] 2.1 `auto_check_in/adapters/sijishe.py` 的 `run()` 兜底改为：捕获 `requests.RequestException` 归类为 `CheckInStatus.SITE_UNAVAILABLE`（消息带脱敏原因，如 `HTTP 403`）；其余未预期异常归类为 `CheckInStatus.ERROR` 且消息追加 `redact_text(str(exc))[:200]`
- [x] 2.2 两处兜底均用 `logger.warning` 记录脱敏原因（`site=... account=...`）

## 3. 自动化测试

- [x] 3.1 `tests/test_notify.py` 新增 SMTP 测试（脚本化 `FakeSMTP` + mock `smtplib.SMTP`/`SMTP_SSL`）：隐式 SSL 用 465、STARTTLS 用 587、`SMTP_PORT` 覆盖、`host:port` 解析、自动回退（首个模式 `SMTPServerDisconnected` 后切下一模式成功）、宽松真值、认证错误不重试、非法端口报错
- [x] 3.2 `tests/test_sijishe.py` 新增：未预期异常被 `logger.warning` 记录且结果消息含脱敏原因；HTTP 错误归类为 `site-unavailable` 且消息含状态
- [x] 3.3 运行 `uv run python -m unittest discover -s tests -v` 全部通过，且 `uv run python -m compileall auto_check_in tests` 无错误

## 4. 手动集成验证

- [x] 4.1 本地以真实 SMTP 环境变量运行 `uv run auto-check-in --notify-only`，确认各渠道（含 SMTP）发送成功
- [x] 4.2 本地以 `SITE_SIJISHE_BASE_URL` / `SITE_SIJISHE_ACCOUNTS` 运行完整签到，确认签到成功且通知正常
- [ ] 4.3 触发 GitHub Actions 手动运行，确认 SMTP 通知成功；若签到仍失败，根据新的日志/通知原因核对 `SITE_CONFIGS` secret 与本地环境变量一致性
