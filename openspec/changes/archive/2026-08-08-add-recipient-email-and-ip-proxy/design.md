## Context

- 通知走 `auto_check_in/notify.py`，SMTP 通道目前 `From`/`To` 都是 `SMTP_EMAIL`（发给自己）。
- 站点访问全部经 `auto_check_in/http.py` 的 `SessionProvider.new_session()` 创建裸 `requests.Session()`，无代理支持；站点为 Discuz（xsijishe.net），Cloudflare 前置，登录提交被拦时进入 `login-blocked`（现有错误信息已提示「封禁了当前出口 IP」）。
- 配置采用「TOML 非敏感值 + 环境变量敏感值」隔离模式；网络参数已有「全局 `[network]` + 站点级 `[sites.<name>.network]` + 环境变量覆盖」三层结构。

## Goals / Non-Goals

**Goals:**
- SMTP 通知支持可选单收件人 `SMTP_TO`，缺省回退 `SMTP_EMAIL`，现有配置零改动。
- 站点会话支持一个或多个代理地址（环境变量配置），每会话轮换出口，用于验证「是否 IP 问题」。
- 代理凭据在日志、错误、通知中脱敏。
- 代理仅作用于站点流量（登录+签到），通知渠道不受影响。
- 失败可观测：代理连接失败时按现有 `SITE_UNAVAILABLE` 状态上报，便于定位坏代理。

**Non-Goals:**
- 不做代理池 API 拉取（阿布云/快代理/蘑菇代理等）与隧道代理接入——验证确认是 IP 问题后再立项。
- 不做代理健康检查/自动 failover（试用期由结果观测代替）。
- 不支持 SOCKS5（需要额外依赖），仅 HTTP/HTTPS 代理。
- 通知渠道不代理。

## Decisions

### D1: `SMTP_TO` 单收件人、可选、缺省回退
- 环境变量 `SMTP_TO` 未设置时 `recipient = SMTP_EMAIL`，`From` 始终为 `SMTP_EMAIL`。
- `message["To"]` 沿用现有 `formataddr((Header(SMTP_NAME), recipient))` 风格，仅替换地址。
- `CHANNEL_REQUIREMENTS["smtp"]` 不强制 `SMTP_TO`，避免破坏现有配置。
- 备选（多收件人逗号分隔）被排除：用户已明确单收件人，多收件人可在需要时再加。

### D2: 代理地址只走环境变量
- 全局 `CHECK_IN_PROXY_URLS`、站点级 `SITE_<NAME>_PROXY_URLS`（逗号分隔，站点级优先），TOML 不接受代理 URL。
- 理由：代理 URL 可能内嵌 `user:pass@`，属于凭据；与「敏感值只从环境变量读」的既有安全模型一致，也避免 TOML 误写凭据。
- 每个条目格式 `http://host:port` 或 `http://user:pass@host:port`；解析时校验 scheme（http/https）与 host 非空，非法条目抛 `ConfigError`。
- 若 TOML 的 `[network]` / `[sites.<name>.network]` 出现 `proxy_urls`，直接抛 `ConfigError` 并指引改用环境变量（避免凭据误入仓库）。

### D3: 按会话轮换（round-robin）
- 每次 `new_session()` 按顺序取下一个代理，同时设置 `session.proxies = {"http": proxy, "https": proxy}`。
- 一个站点内一个账号一个会话 → 每个账号换一个出口 IP，试用期可把「哪个代理」与账号结果对应起来。
- DEBUG 日志输出脱敏后的代理地址（`http://***@host:port`），便于对照。
- 备选（随机选取）被排除：round-robin 可复现、易对照；随机留到池子方案再做。

### D4: 试用期不做自动 failover
- 代理连接失败时适配器现有 `except requests.RequestException → SITE_UNAVAILABLE` 已能上报，试用期靠结果观测识别坏代理。
- 备选（失败换下一个代理重试）会侵入适配器逻辑且掩盖坏代理，试用期不做。

### D5: 代理凭据脱敏
- `security.redact_text` 增加正则，把 `scheme://user:pass@` 掩成 `scheme://***@`，与现有 cookie/token 脱敏并列。
- 所有日志与结果字符串都经 `redact_text`/脱敏用户名渲染，代理地址同样覆盖。

### D6: 会话缓存与代理的交互沿用现有兜底
- 换出口 IP 可能导致站点侧会话失效 → 现有「缓存失效 → 自动重登」逻辑已覆盖，无需新机制。

## Risks / Trade-offs

- [站点在 Cloudflare 后，数据中心代理 IP 可能触发人机校验而非绕过封禁] → 试用阶段用少量代理小规模验证；`login-blocked` 结果会在通知中体现，据此判断方案是否成立
- [代理本身不可用/慢，拉低整体成功率] → 轮换 + 每账号独立结果可定位坏代理；坏代理只影响对应账号
- [免费/低质代理 IP 携带有害流量，可能被站点拉黑] → 试用期数据驱动决策，不自动长期使用
- [换 IP 使缓存 cookie 失效，触发重复登录] → 已有自动重登兜底；频率可接受（每天一次）
- [SMTP 收件人配错导致通知丢失] → `--notify-only` 测试通知可先行验证；SMTP 发送失败会打印渠道错误

## Open Questions

- 试用代理列表由用户提供后填入 Secrets；是否需要把「哪个代理可用」自动汇总进通知正文（先不做，观察日志即可）
- 若确认是 IP 问题，代理池方案（隧道 vs API 池）留待下个变更决策
