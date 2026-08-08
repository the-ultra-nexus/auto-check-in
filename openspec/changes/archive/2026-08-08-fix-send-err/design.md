## Context

当前 SMTP 通道（`auto_check_in/notify.py`）只做一件事：

```python
client = smtplib.SMTP_SSL(server, timeout=TIMEOUT) if SMTP_SSL == "true" else smtplib.SMTP(server, timeout=TIMEOUT)
```

- `SMTP_SSL` 必须严格等于小写 `"true"` 才走隐式 SSL，否则明文 `SMTP()` 直连。
- `SMTP_SERVER` 按 README 是 `smtp.qq.com:465`，`smtplib` 在 `port=0` 时会从字符串解析端口，所以本机 `SMTP_SSL='true'` 能连上 465。
- 一旦 GitHub secret `SMTP_SSL` 不是严格 `"true"`（未设置、`True`、`1`、带空格等），代码走明文 `SMTP('smtp.qq.com:465')`；QQ 465 只接受隐式 TLS，服务器直接断开 → `SMTPServerDisconnected: Connection unexpectedly closed`（本机实测复现：明文连 qq 465 报完全相同的错误）。
- 通道没有 `SMTP_PORT` / `SMTP_STARTTLS` 支持，587 STARTTLS 类服务器无法配置。

签到适配器（`auto_check_in/adapters/sijishe.py`）的 `run()` 用 `except Exception` 兜底，把所有未预期异常折叠成固定文案 `运行过程中发生未预期错误`，真实原因（403、连接/SSL 错误等）既不进日志也不进通知。GitHub runner 出口 IP 与本地不同，站点 WAF/网络差异导致首次请求 1.22s 快速失败时完全无法远程定位——这正是“本地能跑、CI 失败”的观察窗口。

## Goals / Non-Goals

**Goals:**
- SMTP 发送不因 `SMTP_SSL` 拼写/缺失、服务器模式（465 SSL / 587 STARTTLS）不匹配而失败；`Connection unexpectedly closed` 这类连接层错误通过自动探测与回退自愈。
- 签到未预期异常以脱敏形式进入日志与结果/通知，远端运行可诊断；HTTP/网络类失败归类为明确的失败状态。
- 全部用标准库（`smtplib`、`ssl`），不引入新依赖；自动化测试不触网。

**Non-Goals:**
- 不改动站点凭据与 `SITE_CONFIGS` secret 内容（用户管理），只在验证步骤提示核对。
- 不改变“通知通道异常不影响退出码”的语义；不改变多通道并发发送模型。
- 不新增账号级重试策略（沿用现有 `network.retries` 语义）。

## Decisions

### 1. SMTP 连接模式：ssl / starttls / plain 三态 + 自动链
`_smtp_attempts(host, port, port_override, use_ssl, use_starttls)` 返回有序 `(mode, port)` 列表：
- `SMTP_SSL=true` → `[("ssl", 465 或指定端口)]`
- `SMTP_STARTTLS=true` → `[("starttls", 587 或指定端口)]`
- 两者都未设置（自动）：
  - 有显式端口：465 → `[ssl, starttls, plain]`；587 → `[starttls, plain, ssl]`；其它端口 → `[starttls, plain, ssl]`
  - 无端口 → `[starttls(587), ssl(465), plain(25)]`

理由：自动链按“最可能先试”，覆盖本次故障的所有疑点（SMTP_SSL 非严格 true + 服务器在 465；或 SMTP_SSL=true 但服务器只支持 587 STARTTLS）。替代方案“只按 SMTP_SSL 单模式连接”无法自愈，已被实测排除。

### 2. 端口解析优先级
`SMTP_PORT` > `SMTP_SERVER` 中的 `host:port` > 模式默认值（ssl=465 / starttls=587 / plain=25）。`_parse_smtp_server` 支持 `host`、`host:port`、`[ipv6]:port`；端口非法时报清晰错误（由 `_safe` 捕获打印，不影响退出码）。

### 3. `SMTP_SSL` 宽松真值判定
与 `CONSOLE` 一致：`{"1","true","yes","on"}`（大小写不敏感）视为真。直接针对最可能的根因（secret 不是严格小写 `"true"`）。`SMTP_STARTTLS` 同样宽松解析。

### 4. 回退只针对连接层错误
`SMTPAuthenticationError`、`SMTPRecipientsRefused`、`SMTPSenderRefused`、`SMTPDataError` 属于确定性失败，立即抛出不重试（避免掩盖“授权码错误”等真实问题，也避免对已拒绝的邮件反复重发）；`SMTPServerDisconnected`、`OSError`、`TimeoutError`、`ssl.SSLError` 等连接层错误记录后尝试下一种模式，最后抛最后一次错误。

### 5. 适配器错误可观测性
- `except Exception as exc`：`detail = redact_text(str(exc))[:200]`，`logger.warning(...)` 记录脱敏原因，`AccountResult.message` 追加脱敏原因。
- 单独捕获 `requests.RequestException`（含 `HTTPError`、连接/SSL/超时）：归类为 `CheckInStatus.SITE_UNAVAILABLE`，消息带脱敏原因（如 `HTTP 403`、连接失败摘要）。
- 理由：HTTP 403/5xx 与网络失败不是“未预期逻辑错误”，用 `site-unavailable` 表达更准确；仍保持失败（退出码 1），但可诊断。

### 6. 测试策略
- SMTP：在 `tests/test_notify.py` 用可脚本化的 `FakeSMTP` + `mock.patch("auto_check_in.notify.smtplib.SMTP/SMTP_SSL")` 验证模式选择、端口解析、STARTTLS、自动回退、宽松真值、认证错误不重试、非法端口报错。
- 适配器：`FakeSession` 抛出真实异常/HTTP 错误，断言结果状态与消息包含脱敏原因、日志被调用。
- 不触网；真实 SMTP/站点行为留给手动集成验证。

## Risks / Trade-offs

- [自动回退最多尝试 3 次连接，最坏多花 ~2×15s] → 通知线程与主流程隔离、并行发送，不阻塞退出码；按最可能模式排序，显式指定模式时不走自动链。
- [STARTTLS 默认校验证书（`ssl.create_default_context`），自签测试服务器会失败] → 标准安全默认，真实邮件服务商均有效；不做关闭校验的开关。
- [错误分类改变结果状态（error → site-unavailable）] → 退出码语义不变（仍失败）；消息保留原细节，测试覆盖新状态。
- [异常详情进通知可能含敏感文本] → `redact_text` 脱敏 cookie/hex token + 200 字符截断；日志与消息均走同一脱敏。

## Migration Plan

1. 实现 SMTP 通道 + 适配器错误处理 + 测试（本变更 tasks.md）。
2. 合入后本地验证：`uv run auto-check-in --notify-only`（真实 SMTP）应收到邮件；`uv run python -m unittest discover -s tests -v` 全绿。
3. 触发 GitHub Actions `workflow_dispatch` 观察：SMTP 应能发送；若签到仍失败，通知/日志会给出真实原因（如 403），据此核对 `SITE_CONFIGS` secret 与本地环境变量一致性。
4. 回滚：撤销合并提交即可，无数据/配置迁移。

## Open Questions

- GitHub `SMTP_SSL` secret 的真实值无法读取；本设计覆盖了“非严格 true”与“服务器模式不匹配”两种最可能场景，剩余差异（如 runner IP 被站点封禁）需靠新的可观测性定位。
- 若签到失败确为 runner IP 被封，可能需要站点侧处理或换出口，不在本变更范围内。
