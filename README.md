# Auto Check In

纯 HTTP 的多站点自动签到工具。每个站点由独立适配器实现登录与签到，环境数据完全隔离；多个站点在同一次运行中并行执行。

## 功能特性

- 多站点并行调度，站点间环境与失败完全隔离
- 代理池按需补给：直连优先（首个请求先直连，成功即用、0 池成本），直连失败才从多个 IP 池拉取一小批（并行粗探、凑满即停），批次耗尽再取下一批
- 代理失败轮换：请求因代理连接失败或被站点拒绝（403/429/5xx）时自动切换下一个代理
- 登录会话缓存：有效期内复用 cookie，失效自动重登
- 多通知渠道：SMTP / 钉钉 / 企业微信 / 飞书 / Server 酱 / Bark / Telegram / PushPlus / PushDeer / Webhook / ntfy / 控制台
- 全部凭据与敏感配置只走环境变量 / GitHub Secrets，禁止写入配置文件，日志全程脱敏

## 安装与本地运行

需要 Python 3.12。安装依赖后，为每个要运行的站点配置环境变量：

```bash
uv sync
export CHECK_IN_SITES='sijishe'
export SITE_SIJISHE_BASE_URL='https://xsijishe.net'
export SITE_SIJISHE_ACCOUNTS='账号1&密码1@账号2&密码2'
uv run auto-check-in --config config/check-in.toml
```

账号格式为 `账号&密码`，多个账号用换行或 `@` 分隔。站点地址和账号只从环境变量读取，禁止写入配置文件。

先验证配置而不访问站点（会输出每站已识别账号数与脱敏用户名，便于核对账号是否被识别）：

```bash
uv run auto-check-in --config config/check-in.toml --dry-run
```

> 提示：GitHub Actions 日志中 `account=***` 是 GitHub 对 Secret 的自动脱敏，**不代表账号未识别**。
> 应用会在启动时输出 `site=<站点> accounts=<数量> recognized` 作为识别信号；逐账号日志使用脱敏用户名
> （如 `account=1 username=sa***1`）。凭据经 Discuz 协议放在登录 POST 的请求体里，URL 上本就不出现
> `username/password`，因此错误日志里的 URL 看不到账号是正常的。

## 命令行参数

入口为 `uv run auto-check-in [参数]`，`--dry-run` / `--no-notify` / `--notify-only` 三者互斥：

| 参数 | 说明 | 缺省值 |
| --- | --- | --- |
| `--config PATH` | TOML 配置文件路径 | `AUTO_CHECK_IN_CONFIG` 环境变量；未设置则为 `config/check-in.toml` |
| `--dry-run` | 只校验配置与账号，不访问站点 | 关闭 |
| `--no-notify` | 本次运行不发送通知 | 关闭 |
| `--notify-only` | 只发送测试通知，不签到、不访问站点 | 关闭 |
| `--debug` | 开启 DEBUG 日志（等价于 `CHECK_IN_LOG_LEVEL=DEBUG`） | 关闭 |

## 运行流程

```
启动：加载配置（多站点环境隔离）
        │
        ▼
多站点并行调度（CHECK_IN_SITES，默认并行度 min(站点数, 4)）
        │
        ▼ 每个站点：独立环境变量 + 独立 HTTP 会话（批次按站点隔离）
直连优先：首个站点请求先直连（短超时预算，快失败）
   │ 成功（2xx/3xx）→ 粘住直连，不拉批（0 池成本）
   └ 失败（403/429/5xx/超时/拒连）→ 拉批：拉取多个池 → 解析/去重 → 并行粗探
     （connect 2s / total 4s，2xx/3xx 可用）凑满 5 个即停；批次耗尽 → 取下一批
     （最多 5 批）；池失败 → 直连兜底（warn）
        │
        ▼
加载会话缓存并验证登录态
   │ 有效               │ 无效
   ▼                   ▼
直接进入签到         登录弹框（解析 formhash/referer/loginhash）
   │                   │
   │                   ▼
   │            登录 POST（密码 MD5）
   │                   │
   │                   ▼
   │            确认登录态（auth cookie / 签到页结构）
   └───────┬───────────┘
           ▼
GET 签到页 → 解析 formhash → GET 签到接口
           ▼
响应判定：success / already-checked-in / login-failed / check-in-failed
   │ login-failed → 清 cookie → 重新登录一次 → 再签到
   ▼
保存会话缓存 → 汇总 → 通知 → 退出码（0/1/2）
```

## 代理池与失败轮换

代理只作用于站点登录/签到流量，通知渠道不受影响。代理一律来自 IP 池的按需分批补给，不再支持手写静态代理列表。

### 配置

```bash
# 逗号分隔多个 IP 池 URL，每个池返回代理列表（一行一个或逗号分隔）
export CHECK_IN_PROXY_POOL_URLS='xxxx'
```

- 只允许环境变量 / GitHub Secret 提供，写入配置文件会直接报错（与凭据同等对待）
- GitHub Actions 中放入同名 Secret 即可，工作流已内置 `env` 映射

### 池格式

每行（或逗号分隔条目）支持三种格式，混用亦可：


| 格式                         | 示例                            |
| -------------------------- | ----------------------------- |
| `host:port`                | `1.2.3.4:8080`                |
| `http(s)://host:port`      | `http://1.2.3.4:8080`         |
| 空白/制表符分隔表格（取前两列 ip 与 port） | `1.2.3.4 8080 HTTP(S) 国家 ...` |


拉取后按 `host:port` 去重并截断上限，非法行跳过并计数。

### 直连优先与拉批

**直连优先**（站点级 `direct_first`，默认开启，等价于把本机 IP 作为池的首位候选）：会话第一个请求（GET 签到页）先直连，短超时预算（复用粗探 connect 2s / total 4s）保证快失败。

- 直连返回 `2xx`/`3xx` → 直接返回并粘住直连，**不拉批（0 池成本）**
- 直连失败（`403`/`429`/`5xx`/超时/拒连/TLS）→ **才拉批**，用批内代理重试同一请求；直连粘住期间后续请求再失败 → 同样拉批重试
- 站点关闭 `direct_first`（该站实验后直连成功率持续为 0 时）→ 无条件先拉批再发请求；在 `SITE_CONFIGS` 每站点设 `"direct_first": false`，本地可用 `SITE_<NAME>_DIRECT_FIRST=false`（env 优先，禁止写入 TOML）

拉批本身：

- **批次按站点隔离**：每个站点的会话各自拉批、各自持有与轮换，站点间不共享批次
- 拉取多个池 → 解析/去重 → **并行粗探**（并发 10，连接 2s / 总 4s），只保留 `2xx`/`3xx`
- **凑满 5 个可用即停**（`BATCH_SIZE=5`，不全量探完）；批次耗尽 → 取下一批（每请求最多 `MAX_BATCHES=5` 批）
- 批次上限内仍失败 → 抛最后一个错误，该账号 `site-unavailable`；池拉取失败/取不到代理 → 直连兜底 + warn，不中断 run

### 触发边界


| 失败信号                                         | 含义              | 处理                            |
| -------------------------------------------- | --------------- | ----------------------------- |
| `403`/`429`/`5xx`/超时/拒连/TLS 失败               | 传输层：当前 IP/代理不可用 | 取下一批换 IP，重试同一请求               |
| 页面 `200` 但未登录/无 formhash/签到返回 `login-failed` | 会话层：cookie 失效   | **不拉池**，清 cookie 重新登录（复用当前批次） |


### 与失败轮换的分层

- **直连优先 + 按需补给**：直连能通则 0 池成本；直连失败才拉批，批次耗尽再取下一批
- **失败轮换**（`FailoverSession`）是兜底：批内代理仍可能失效，请求因代理连接失败或被站点拒绝（403/429/5xx）时自动按序切换下一个代理，成功后保持（粘性）
- 免费代理池时效短（1~10 分钟轮换）、多为数据中心 IP，实际可用率可能很低；多配几个池提高冗余，必要时考虑付费/自建稳定代理

## 环境变量

完整清单见仓库根目录 [.env.example](.env.example)（单一事实来源）。带 `# @ci:secrets` / `# @ci:vars` 标记的变量为工作流已透传项；未标记变量仅本地使用。工作流 `env` 映射由 `tests/test_github_workflow.py` 双向校验——新增环境变量漏配或工作流引用未声明变量都会在 CI 中直接失败。


| 分类  | 变量                         | 说明                                                                            |
| --- | -------------------------- | ----------------------------------------------------------------------------- |
| 通用  | `CHECK_IN_SITES`           | 逗号分隔本次运行的站点，优先于配置文件 `enabled_sites`                                           |
| 通用  | `SITE_CONFIGS`             | JSON Secret，包含全部站点的地址与账号（CI 用）                                                |
| 通用  | `CHECK_IN_MAX_WORKERS`     | 站点并行度，默认 `min(站点数, 4)`                                                        |
| 通用  | `AUTO_CHECK_IN_CONFIG`     | 配置文件路径，默认 `config/check-in.toml`                                              |
| 代理  | `CHECK_IN_PROXY_POOL_URLS` | 逗号分隔多个 IP 池 URL，按需分批补给（直连优先、失败才拉批、批次按站点隔离）                                    |
| 网络  | `CHECK_IN_REQUEST_TIMEOUT` | 单请求超时秒，默认 15                                                                  |
| 网络  | `CHECK_IN_RETRIES`         | 业务重试次数，默认 3                                                                   |
| 网络  | `CHECK_IN_RETRY_DELAY`     | 登录重试间隔秒，默认 3.0（设 0 关闭）                                                         |
| 网络  | `CHECK_IN_REQUEST_DELAY`   | 站点内账号间隔秒，默认 3.0（设 0 关闭）                                                       |
| 会话  | `CHECK_IN_SESSION_CACHE`   | 是否缓存登录会话，默认 true                                                              |
| 会话  | `CHECK_IN_SESSION_DIR`     | 会话缓存目录，默认 `.runtime/sessions`                                                 |
| 会话  | `CHECK_IN_SESSION_MAX_AGE` | 会话最大有效期秒，0 关闭                                                                 |
| 日志  | `CHECK_IN_LOG_LEVEL`       | 日志级别（如 `DEBUG`），等价于 CLI `--debug`                                             |
| 通知  | 见下方“通知方式”表                 | 各渠道凭据均为 Secret 透传                                                             |
| 站点级 | `SITE_<NAME>_BASE_URL`     | 站点地址                                                                          |
| 站点级 | `SITE_<NAME>_ACCOUNTS`     | 该站点账号，`账号&密码`，多个用换行/`@` 分隔                                                    |
| 站点级 | `SITE_<NAME>_DIRECT_FIRST` | 该站直连优先开关，`true`/`false`（默认 `true`），env 优先于 `SITE_CONFIGS` 的 `direct_first` 字段 |
| 站点级 | `SITE_<NAME>_SIGN_PATH`    | 签到页路径（默认 `/k_misign-sign.html`），env 优先于 `SITE_CONFIGS` 的 `sign_path` 字段       |


站点级变量 `SITE_<NAME>_*` 在本地或自建 workflow 中使用，优先于 `SITE_CONFIGS` 中同名站点；CI 推荐统一维护 `SITE_CONFIGS` 一个 Secret。

## 多站点并行

`CHECK_IN_SITES` 用逗号列出本次运行的站点；各站点环境完全隔离，在同一进程内并行执行（默认并行度 `min(站点数, 4)`，可用 `CHECK_IN_MAX_WORKERS` 调整），站点内账号串行，账号间默认等待 3 秒（`CHECK_IN_REQUEST_DELAY`，设 0 关闭）。一站失败不影响其他站，全部结束后任一失败则退出码为 1。通知与 HTTP 请求从同一个内置 UA 池随机取用 User-Agent，无需配置。

例如同时运行司机社和一个未来注册的 `site2`：

```bash
export CHECK_IN_SITES='sijishe,site2'
export SITE_SIJISHE_BASE_URL='https://xsijishe.net'
export SITE_SIJISHE_ACCOUNTS='账号1&密码1@账号2&密码2'
export SITE_SITE2_BASE_URL='https://site2.example'
export SITE_SITE2_ACCOUNTS='账号A&密码A'
uv run auto-check-in --config config/check-in.toml
```

规则：

- 站点名只能包含字母、数字和下划线；环境变量按 `SITE_<NAME>_*` 命名，`NAME` 为大写站点名
- 每站必填 `SITE_<NAME>_BASE_URL` 与 `SITE_<NAME>_ACCOUNTS`；可选 `SITE_<NAME>_ADAPTER`，未设置时使用与站点同名的适配器
- `config/check-in.toml` 的 `[runtime] enabled_sites` 是默认列表，`CHECK_IN_SITES` 优先；新增站点前先把适配器注册到 `ADAPTERS`
- 先做 dry-run 可逐个站点校验配置与账号：

```bash
export CHECK_IN_SITES='sijishe,site2'
export SITE_SIJISHE_BASE_URL='https://xsijishe.net'
export SITE_SIJISHE_ACCOUNTS='账号1&密码1'
export SITE_SITE2_BASE_URL='https://site2.example'
export SITE_SITE2_ACCOUNTS='账号A&密码A'
uv run auto-check-in --config config/check-in.toml --dry-run
```

## 退出码

- `0`：全部账号成功或已签到
- `1`：存在失败账号
- `2`：配置或凭据错误（启动前失败）

## 会话缓存

默认把登录 cookie 保存在 `.runtime/sessions/`（已 gitignore，文件权限 0600）：下次运行先加载并验证登录态，有效则直接签到，只有签到返回 `login-failed`（会话失效）时才重新登录并写回缓存。

- 关闭：`CHECK_IN_SESSION_CACHE=false`
- 修改目录：`CHECK_IN_SESSION_DIR=/path/to/dir`
- 超期重登：`CHECK_IN_SESSION_MAX_AGE`（秒，默认 0 关闭）

GitHub Actions 通过 `actions/cache` 在两次运行间恢复/保存 `.runtime/sessions`（工作流已内置）。注意 runner 出口 IP 可能变化导致 cookie 失效，此时会自动重新登录，功能不受影响。

## GitHub Actions

工作流位于 [.github/workflows/check-in.yml](.github/workflows/check-in.yml)，每天 08:00（Asia/Shanghai）运行，亦可在 Actions 页面手动触发。请在仓库 Settings → Secrets and variables → Actions 中设置：

- 必需：`SITE_CONFIGS`（JSON Secret，包含全部站点的地址与账号）
- 可选：仓库变量 `CHECK_IN_SITES`（逗号分隔，只运行部分站点；留空则运行 `SITE_CONFIGS` 里全部站点）
- 可选：`CHECK_IN_PROXY_POOL_URLS`（逗号分隔多个 IP 池 URL，直连失败后按需分批补给）
- 按通知渠道选填：`BARK_PUSH`、`PUSH_KEY`、`FSKEY`、`TG_BOT_TOKEN`、`TG_USER_ID`、`DD_BOT_TOKEN`/`DD_BOT_SECRET`、`QYWX_KEY`、`SMTP_SERVER`/`SMTP_SSL`/`SMTP_EMAIL`/`SMTP_PASSWORD`/`SMTP_NAME`（可选 `SMTP_STARTTLS`/`SMTP_PORT`/`SMTP_TO`）

`SITE_CONFIGS` 完整示例见仓库根目录 [SITE_CONFIGS.example.json](SITE_CONFIGS.example.json)，要点如下：

```json
{
  "sijishe": {
    "base_url": "https://xsijishe.net",
    "accounts": "账号1&密码1@账号2&密码2",
    "direct_first": true
  },
  "site2": {
    "base_url": "https://site2.example",
    "accounts": "账号A&密码A",
    "direct_first": false
  }
}
```

`direct_first` 为可选字段（默认 `true`）：`false` 表示该站点不尝试直连、无条件先拉批再发请求。

新增站点只需更新这一个 Secret，无需改动工作流。Secrets 只作为环境变量传递，不会被打印。手动触发工作流时可在 “sites” 输入框临时指定站点（逗号分隔），留空则按仓库变量或全部站点运行。

### 登录被拦截（`login-blocked`）

当登录提交（`member.php?action=login&loginsubmit=yes`）返回 HTTP 4xx（典型 403）时，结果状态为
“登录被拦截”。站点实际可达（登录弹框、formhash 均正常），只是登录提交被站点端拒绝，常见原因与排查：

1. **站点 WAF / 防机器人**：对自动化登录做了风控。稍后重试、或换时段再跑一次看是否恢复。
2. **出口 IP 被封**：GitHub runner 出口 IP 被站点封禁。可配置 `CHECK_IN_PROXY_POOL_URLS` 换代理出口重试，
 或先在本机（住宅 IP）用相同凭据跑一次确认 `uv run auto-check-in --config config/check-in.toml --dry-run`
 识别正常、实际运行能登录。
3. **凭据问题**：核对 `SITE_CONFIGS` Secret 与本地 `SITE_SIJISHE_ACCOUNTS` 是否一致、账号密码是否有效。

排查时结合 `--debug` 日志：会记录失败步骤（`dialog-fetch` / `login-submit` / `sign-in`）与登录表单
字段填充状态（仅字段名，不含任何值）。

> 注意：补给粗探只保证“连通”，不保证“登录成功”。代理可用但登录仍失败（`login-failed` / `login-blocked`）
> 是站点层问题，需要按上面方向排查。

## 通知方式

通知由 `auto_check_in/notify.py` 统一发送，支持多个渠道同时启用；所有值都通过环境变量或 GitHub Secrets 注入，禁止写入配置文件。文档、示例与规划文档中的账号一律使用占位符（如 `alice&secret`），禁止出现真实用户名/密码；真实凭据只存在于本机环境变量或 GitHub Secret 中。标题为短格式结果摘要，如 `签到 3/3 成功 08-08` 或 `签到 1/3 失败 08-08`，正文为按站点分组的每账号汇总。

运行日志使用标准 `logging`：`CHECK_IN_LOG_LEVEL`（如 `DEBUG`）或 CLI 的 `--debug` 可打开调试日志，日志内容已脱敏。


| 渠道          | 需要设置的环境变量                                                                                                                                            |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 邮箱 SMTP     | `SMTP_SERVER`（如 `smtp.qq.com` 或 `smtp.qq.com:465`）、`SMTP_SSL`、`SMTP_EMAIL`、`SMTP_PASSWORD`（授权码）、`SMTP_NAME`；可选 `SMTP_STARTTLS`、`SMTP_PORT`、`SMTP_TO` |
| 钉钉机器人       | `DD_BOT_TOKEN`、`DD_BOT_SECRET`                                                                                                                       |
| 企业微信机器人     | `QYWX_KEY`                                                                                                                                           |
| 飞书机器人       | `FSKEY`                                                                                                                                              |
| Server 酱    | `PUSH_KEY`                                                                                                                                           |
| Bark        | `BARK_PUSH`（可选 `BARK_GROUP`、`BARK_SOUND`、`BARK_ICON`、`BARK_LEVEL`、`BARK_URL`）                                                                        |
| Telegram    | `TG_BOT_TOKEN`、`TG_USER_ID`（可选 `TG_API_HOST`）                                                                                                        |
| PushPlus    | `PUSH_PLUS_TOKEN`                                                                                                                                    |
| PushDeer    | `DEER_KEY`（可选 `DEER_URL`）                                                                                                                            |
| 自定义 Webhook | `WEBHOOK_URL`、`WEBHOOK_METHOD`                                                                                                                       |
| ntfy        | `NTFY_TOPIC`（可选 `NTFY_URL`）                                                                                                                          |
| 控制台输出       | `CONSOLE=true`                                                                                                                                       |


本地开启邮箱提醒示例（QQ 邮箱隐式 SSL，465 端口）：

```bash
export SMTP_SERVER='smtp.qq.com:465'
export SMTP_SSL='true'
export SMTP_EMAIL='you@qq.com'
export SMTP_PASSWORD='你的授权码'
export SMTP_NAME='Auto Check In'
# 可选：单独指定收件人邮箱，未设置时通知发给 SMTP_EMAIL 本身
export SMTP_TO='receiver@example.com'
```

SMTP 渠道支持三种连接方式：

- `SMTP_SSL=true`（也接受 `1` / `yes` / `on`，大小写不敏感）：隐式 SSL/TLS，默认端口 465；
- `SMTP_STARTTLS=true`：先明文连接再升级 STARTTLS，默认端口 587；
- 两者都未设置：自动探测，先尝试 587 STARTTLS，再尝试 465 隐式 SSL，最后 25 明文；连接层失败会自动切换，避免 `Connection unexpectedly closed` 这类因 SSL 模式与服务器不匹配导致的发送失败。认证失败等确定性错误不会重复尝试。

`SMTP_SERVER` 可写成 `主机` 或 `主机:端口`，也可用 `SMTP_PORT` 单独指定端口；`SMTP_EMAIL` 的邮箱地址即发件人。可选 `SMTP_TO` 单独指定单收件人，未设置时通知发送给发件人自身。

本地单独测试通知（不签到、不访问站点，也无需站点凭据）：

```bash
uv run auto-check-in --notify-only
```

会向所有已启用渠道发送一条测试通知并在控制台列出启用渠道；无任何渠道启用或通知被关闭（`CHECK_IN_NOTIFY=false`）时返回退出码 2。`--notify-only` 与 `--dry-run`、`--no-notify` 互斥。

GitHub Actions 使用时，把对应值配置为仓库 Secret，并在工作流 `env` 中映射（工作流已内置邮箱、钉钉、飞书、Server 酱、Telegram、企业微信机器人和 Bark 的映射）。如需跳过某个标题的推送可设置 `SKIP_PUSH_TITLE`。

## 扩展其他站点

新增站点时实现 `CheckInAdapter` 协议（`run(account) -> AccountResult`），在 `auto_check_in/adapters/__init__.py` 的 `ADAPTERS` 注册，配置 `[runtime] enabled_sites` 与 `SITE_<NAME>_*` 环境变量即可。运行器、结果模型、通知和 CLI 无需修改；测试可复用 `tests/helpers.py` 的 fixture（FakeSession、HTML/XML 样例等），并参考 `tests/test_sijishe.py` 为每个站点建立 `tests/test_<站点>.py`。

可复用的共用模块：Discuz 系站点的弹框解析、formhash 提取和响应分类在 `auto_check_in/discuz.py`；随机 UA 池在 `auto_check_in/http.py`；错误类型在 `auto_check_in/errors.py`；会话缓存与脱敏分别在 `auto_check_in/session.py`、`auto_check_in/security.py`。

## 验证

```bash
uv run python -m unittest discover -s tests -v
uv run python -m compileall auto_check_in tests
```
