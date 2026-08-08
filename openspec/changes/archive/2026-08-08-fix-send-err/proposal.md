## Why

GitHub Actions 定时运行 `uv run auto-check-in --config config/check-in.toml` 失败：签到账户报 `运行过程中发生未预期错误`（真实异常被兜底逻辑吞掉，无法远程诊断），通知渠道 SMTP 报 `Connection unexpectedly closed`，最终退出码 1。同一套站点凭据在本机用 `SITE_SIJISHE_BASE_URL` / `SITE_SIJISHE_ACCOUNTS` 可以直接跑通（签到成功、邮件正常），说明问题出在 GitHub Actions 环境差异与运行时对失败的处理上，而不是站点凭据本身。

根因分析（详见 design.md）：

- **SMTP**：`notify.smtp` 只在 `SMTP_SSL == "true"` 时用隐式 SSL（`SMTP_SSL(server)`），否则用明文 `SMTP(server)` 直连。`SMTP_SERVER='smtp.qq.com:465'` 时若 secret 不是严格小写 `"true"`（未设置、`True`、`1`、带空格等），就走明文连 465；QQ 465 只接受隐式 TLS，服务器直接断开连接，报 `Connection unexpectedly closed`（本机已验证明文连 qq 465 产生完全相同的错误）。通道也不支持端口解析、`SMTP_PORT` 或 `SMTP_STARTTLS`，无法配置 587 STARTTLS 类服务器。
- **签到错误被掩盖**：`SijisheAdapter.run` 的兜底 `except Exception` 把一切未预期异常（HTTP 403、连接/SSL 错误等）折叠成固定文案，真实原因既不进日志也不进通知。GitHub runner 出口 IP 与本地不同，站点 WAF/网络差异导致首个请求 1.22s 内快速失败时完全无法远程定位（本地正常而 CI 失败正是这个差异的体现）。

## What Changes

- 重写 `auto_check_in/notify.py` 的 SMTP 通道：支持 `SMTP_STARTTLS`、`SMTP_PORT`，`SMTP_SERVER` 解析 `host:port`；`SMTP_SSL` 采用宽松真值判定；未显式指定模式时自动探测（587 STARTTLS → 465 隐式 SSL → 25 明文），连接层失败自动切换，认证/收件人等确定性错误不触发回退。修复 `Connection unexpectedly closed` 这类因模式与服务器不匹配导致的发送失败。
- 增强签到适配器错误可观测性：未预期异常记录脱敏日志，并在结果/通知消息中带上脱敏、截断的真实原因；HTTP/网络类错误归类为更明确的失败状态（站点不可用）而不是笼统的 error，让远端运行可诊断。
- 工作流透传 `SMTP_STARTTLS` / `SMTP_PORT` secrets；README 补充 SMTP 连接方式与排障说明。
- 新增自动化测试（SMTP 模式选择/端口解析/回退、适配器异常可观测性），并加入手动集成验证步骤（本地 `--notify-only` + 核验 `SITE_CONFIGS` 与本地环境变量一致）。

**Non-Goals**：不改动站点凭据与 `SITE_CONFIGS` secret 内容（由用户管理，仅在验证步骤中提示核对）；不改变“通知通道异常不影响退出码”的既有语义；不新增重试策略；不改变多通道并发发送模型。

## Capabilities

### New Capabilities

- `smtp-channel-reliability`: SMTP 通知通道的连接模式（隐式 SSL / STARTTLS / 明文）、端口与 `host:port` 配置、自动探测与连接层回退、宽松 `SMTP_SSL` 判定，避免错误模式导致发送失败。

### Modified Capabilities

- `operations-and-observability`: 新增“未预期异常必须脱敏记录并出现在结果/通知中，便于远程诊断”的 requirement 场景（原规格只有结构化日志，未覆盖适配器异常的具体可观测性）。

## Impact

- `auto_check_in/notify.py`：SMTP 通道重写（新增 `_parse_smtp_server` / `_smtp_attempts` / `_smtp_send` 等辅助函数，标准库 `smtplib`/`ssl`，无新依赖）。
- `auto_check_in/adapters/sijishe.py`：`run()` 兜底异常处理与错误分类；复用 `logger` 与 `redact_text`。
- `.github/workflows/check-in.yml`：`env` 增加 `SMTP_STARTTLS`、`SMTP_PORT`。
- `README.md`：SMTP 配置说明、`--notify-only` 验证与排障段落。
- `tests/test_notify.py`、`tests/test_sijishe.py`：新增单元测试。
- `openspec/specs/operations-and-observability/spec.md`：后续归档时合并 delta。
