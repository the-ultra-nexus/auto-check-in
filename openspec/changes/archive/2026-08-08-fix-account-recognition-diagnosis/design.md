## Context

`auto-check-in` 在 GitHub Actions 中通过 `SITE_CONFIGS`（JSON Secret）注入站点凭据。CI 日志里 `site=sijishe account=***` 的 `***` 是 GitHub Actions 对 Secret 的自动脱敏——用户名 `alice` 是 `SITE_CONFIGS` Secret 值（如 `alice&secret`）的子串，打印时被替换。应用自身从不输出 `***`（`runner.py`/`adapters/sijishe.py` 直接打印 `account.username`，无脱敏），也没有任何“账号已识别”的信号，用户无法区分“未识别”与“已识别但被脱敏”。

已用占位凭据本地复现验证：
- `SITE_CONFIGS` JSON 路径**正常工作**（`--dry-run` 解析出 1 个账号）；CI 中该账号真实参与了登录 POST（收到 403），说明识别本身没问题。
- 把 `accounts` 写进 `config/check-in.toml` 的 `[sites.sijishe]` 会被当作未知键静默忽略，随后报“缺少账号凭据”，是误导性脚坑。
- 登录 POST（`loginsubmit=yes`）返回 403 被 `except requests.RequestException` 统一归类为 `site-unavailable`（“站点不可用”），但站点实际可达（登录弹框 GET 与 formhash 解析均成功），文案误导。

约束：凭据只允许来自环境变量/Secret，禁止写入仓库；不绕过站点 WAF/防机器人；通知渠道异常不影响退出码；自动化测试不触网。

## Goals / Non-Goals

**Goals:**
- 让用户在 CI Secret 脱敏环境下也能确认：账号是否被识别、共识别几个、失败的是哪个账号。
- 日志与结果摘要不再打印完整用户名，改用可区分、不可还原的脱敏形式。
- 登录提交被站点拒绝（HTTP 4xx/403）时给出明确状态“登录被拦截”和可操作提示，不再误报“站点不可用”。
- 配置文件里出现敏感凭据键时给出确定性错误与正确指引。
- README 解释 `***` 含义与核对方法。

**Non-Goals:**
- 不绕过或对抗站点 WAF/防机器人（不做验证码识别、浏览器指纹、代理池）。
- 不修改 `SITE_CONFIGS` Secret 内容与账号凭据本身。
- 不改变“通知通道异常不影响退出码”语义；不改变多账号 `&`/`@` 分隔格式。
- 不修复 SMTP `Connection unexpectedly closed`（fix-send-err 已覆盖连接模式回退；剩余为环境/凭据问题，验证步骤提示核对）。

## Decisions

### 1. 识别信号用“数量”而非“用户名”，天然抗 Secret 脱敏
配置加载完成后逐站点输出 `site=<name> accounts=<N> recognized`（仅数量）。备选“启动时打印脱敏用户名列表”被否决：CI 观察显示 GitHub 会脱敏 Secret 的子串（完整用户名被替换为 `***`），含前缀的脱敏名仍可能被进一步掩盖；纯数量不会被命中。`--dry-run` 额外打印脱敏用户名列表用于本地核对。

### 2. `mask_username`：首尾保留 + 中间 `***`
`security.py` 新增 `mask_username(username)`：长度 ≤1 → `*`；≤4 → 首字符+`***`；否则 → 前 2 字符+`***`+末 1 字符（如 `alice` → `al***e`）。逐账号日志同时带序号（`account=1 username=sa***1`），即使脱敏名被 CI 进一步替换，序号仍可对应账号。会话缓存键仍用原始用户名（md5），内部不变。

### 3. 新增 `login-blocked` 状态与 `LoginBlockedError`
`models.py` 增加 `CheckInStatus.LOGIN_BLOCKED = "login-blocked"`（标签“登录被拦截”，计入失败、退出码仍为 1）。`errors.py` 新增 `LoginBlockedError(LoginError)`。`adapters/sijishe.py` 的 `_post_login` 对登录 POST 的 `requests.HTTPError`：状态为 4xx（典型 403）→ 抛 `LoginBlockedError("登录请求被站点拒绝（HTTP <status>）：站点可能启用了防机器人校验或封禁了当前出口 IP，请核对账号密码并在本地验证")`；`run()` 在 `LoginError` 之前捕获 `LoginBlockedError` → `LOGIN_BLOCKED`。非登录步骤（弹框 GET、签到接口）的 HTTP 错误保持 `site-unavailable` 归类不变。备选“复用 LOGIN_FAILED”被否决：凭据错误与站点拦截是不同根因，状态区分才能指导排障。

### 4. TOML 敏感凭据键：从“未知键警告”改为确定性报错
`load_config` 检测 `sites.<name>` 节含 `accounts`（以及未来可能的密码类键）时，直接抛 `ConfigError("站点 <name> 的账号凭据不允许写入配置文件（检测到 sites.<name>.accounts），请使用 SITE_<NAME>_ACCOUNTS 或 SITE_CONFIGS 环境变量/Secret 提供")`。备选“允许 TOML 写凭据”被否决：配置文件随仓库提交，违背项目安全约束（config.yaml context 与 README 均要求凭据只走环境变量）。

### 5. 脱敏用户名的落点
逐账号日志（`runner.py`、`sijishe.py` 的 warning/info）与结果摘要（`models.py` `summary_line`、`cli.py`）统一改用 `mask_username`；`--dry-run` 输出追加脱敏用户名列表。通知内容随之脱敏。

### 6. 测试策略（不触网）
- `mask_username`：长度边界、不含完整用户名、空输入。
- 识别日志：`assertLogs` 断言 `load_config` 输出 `accounts=N recognized`。
- TOML `accounts`：断言抛 `ConfigError` 且消息含正确指引。
- 适配器：`FakeSession` 对登录 POST 抛 HTTPError(403) → 结果状态 `login-blocked`、消息含提示；对签到接口抛 HTTPError(503) → 仍为 `site-unavailable`。
- 摘要/日志：断言输出含脱敏用户名、不含完整用户名。

### 7. 登录提交过程可观测（只记字段名，不记值）
`_post_login` 提交前以 DEBUG 级记录登录表单字段是否填充（如 `login form: formhash=yes username=yes password=md5=yes`，不含值）；登录被拒时该步已由 `LoginBlockedError` 消息与步骤名覆盖。理由：用户看到错误 URL 上没有 `user/password` 就误以为没传——实际凭据在 POST body，`requests` 的 `HTTPError` 只打印 URL。备选“把凭据拼进 URL”被否决（泄露风险且不符合 Discuz 协议，服务器本就不接受 query 传参）。

### 8. 文档与规划文档凭据卫生
所有文档、示例与 OpenSpec 规划文档一律使用占位账号（如 `alice&secret`），禁止出现真实用户名/密码。理由：本变更的 design.md 曾因引用用户报告中的真实用户名而把真实标识符写进仓库（对应密码从未出现，已核实 git 历史）；规划文档同样会入库，需与代码同标准。核查手段：`git grep` 跟踪文件 + `git log -p` 历史扫描；`.gitignore` 已覆盖 `.runtime/`、`.env*`、`config/*.secret.toml`、验证码截图。

## Risks / Trade-offs

- [脱敏名含 2 字符前缀，仍可能被 CI Secret 脱敏命中] → 概率低（GitHub 对 <4 字符子串不脱敏）；逐账号日志带序号、加载日志带数量，双重兜底。
- [新增 `login-blocked` 状态改变 403 的既有归类] → 两种状态都失败、退出码不变；消息更准确，测试覆盖新旧两类 HTTP 错误的映射。
- [TOML `accounts` 从“警告+缺凭据”改为硬错误] → 对错误配置的用户是行为变化，但错误消息直接给出正确配置方式，属预期修复；对正确使用环境变量的用户无影响。
- [识别日志在加载期解析账号（多一次解析开销）] → `parse_accounts` 为纯字符串解析，开销可忽略；顺带让 `--dry-run` 之外的启动路径也提前校验格式。

## Migration Plan

1. 实现 `mask_username`、`LOGIN_BLOCKED`、`LoginBlockedError`、TOML 凭据键报错、适配器/runner/cli/models 脱敏与分类、README 说明（见 tasks.md）。
2. 本地验证：`uv run python -m unittest discover -s tests -v` 全绿；`SITE_CONFIGS='{...占位...}' uv run auto-check-in --config config/check-in.toml --dry-run` 输出 `accounts=1 recognized` 与脱敏用户名；有真实凭据时本地跑一次确认 `login-blocked` 或成功路径。
3. CI 验证：`workflow_dispatch` 触发，日志应含 `accounts=1 recognized` 与 `account=1 username=sa***1`；若站点仍 403，结果应为“登录被拦截”并带排障提示。
4. 回滚：撤销合并提交即可；无数据/配置迁移，`SITE_CONFIGS` Secret 无需改动。

## Open Questions

- 站点 403 的确切成因（WAF challenge / 出口 IP 封禁 / 凭据触发风控）无法远程判定；新状态与提示覆盖所有可能，最终需用户在本机（住宅 IP）核对账号密码与站点可访问性。
- 若 SMTP 在 CI 持续 `Connection unexpectedly closed`，需用户核对 `SMTP_SERVER`/`SMTP_SSL`/`SMTP_STARTTLS`/`SMTP_PASSWORD` Secret 与本地可用配置是否一致；不在本变更处理。
