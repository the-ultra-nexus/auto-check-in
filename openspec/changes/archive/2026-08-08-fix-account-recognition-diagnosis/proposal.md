## Why

GitHub Actions 定时运行 `uv run auto-check-in --config config/check-in.toml` 时日志显示 `site=sijishe account=***`，用户据此以为 `SITE_CONFIGS` 里的账号没被识别。实际上账号**已被识别**（运行解析出 1 个账号并真实发起了登录 POST，只是被站点以 403 拒绝）——`***` 是 GitHub Actions 对 Secret 的自动脱敏（用户名是 `SITE_CONFIGS` 这个 Secret 值的子串，CI 日志里被替换成了 `***`）。应用本身从不打印 `***`，也没有任何日志能证明“账号已识别”，导致用户无法区分“未识别”和“已识别但被脱敏”。同时登录 POST 的 403 被笼统归类为 `站点不可用`，但站点实际可达（登录弹框 GET 与 formhash 解析都成功），只有登录提交被 WAF/防机器人拦截，现有文案既不准确也无法指导排障。

## What Changes

- 新增**账号识别可观测性**：配置加载后按站点输出已识别账号数量（如 `site=sijishe accounts=1 recognized`，只含数量、不含任何凭据，CI 脱敏无法掩盖）；所有逐账号日志与结果摘要改用脱敏用户名（如 `sak***1`）而非原始用户名，既证明识别成功，也避免用户名泄露或整段被 Secret 脱敏。
- 新增**登录被拦截**状态：登录提交（`loginsubmit=yes` POST）返回 HTTP 4xx（典型 403）时归类为新的 `login-blocked`（标签“登录被拦截”）并给出可操作提示（站点防机器人/WAF、出口 IP 被封、账号密码需核对），不再误报为“站点不可用”。
- 新增**登录提交可观测**：凭据经 Discuz 协议放在 POST body（URL 上本就不出现 `username`/`password`，`requests` 异常也只打印 URL，容易被误判为“没带参数”）；登录失败或 `--debug` 时日志标明失败步骤（获取弹框 → 提交登录 → 签到）并确认登录表单字段已填充（仅字段名，不含任何值）。
- 配置文件凭据脚坑改为明确报错：`[sites.*]` 中出现 `accounts` 键时直接抛出配置错误并指向 `SITE_<NAME>_ACCOUNTS` / `SITE_CONFIGS` 环境变量，而不是静默忽略后报“缺少账号凭据”（当前行为已验证：TOML 中写 `accounts` 会被当作未知键忽略）。
- README 补充 CI 日志 `***` 含义说明：它是 GitHub Secret 自动脱敏，不代表未识别；如何用 `--dry-run` 与 `accounts=N recognized` 日志核对账号是否被识别；以及 `登录被拦截` 的排障路径。
- 新增**全项目数据脱敏/凭据卫生**：清除规划文档与示例中来自用户 `SITE_CONFIGS` 报告的真实用户名/凭据，统一改用占位符（如 `alice&secret`）；核查全部跟踪文件与 git 历史不含真实凭据；README 明确示例与规划文档禁用真实标识符。
- 新增/更新自动化测试：脱敏用户名助手、识别数量日志、`login-blocked` 分类、TOML `accounts` 报错；不触网。

**Non-Goals**：不绕过站点 WAF/防机器人（不做验证码、浏览器指纹、代理池等对抗手段）；不修改 `SITE_CONFIGS` Secret 内容与账号凭据；不改变通知通道异常不影响退出码的既有语义；SMTP 的 `Connection unexpectedly closed` 属于环境/凭据问题（fix-send-err 已覆盖连接模式回退），仅在验证步骤提示核对，不在本变更修复。

## Capabilities

### New Capabilities
- `account-recognition-observability`: 账号识别结果的可观测性——按站点输出已识别账号数量，并以脱敏用户名（而非原始用户名或裸 `***`）出现在日志与结果摘要中，使 CI Secret 脱敏环境下仍能确认账号是否被识别、哪个账号失败。

### Modified Capabilities
- `operations-and-observability`: 逐账号日志行与失败状态语义更新——账号标识改为脱敏用户名；登录提交被站点拒绝（HTTP 4xx/403）映射为明确的 `login-blocked` 状态并携带可操作提示，不再笼统归为 `site-unavailable`。
- `runtime-reliability`: 配置校验完整性——`[sites.*]` 中出现敏感凭据键 `accounts` 时作为确定性配置错误报出并给出正确配置指引，取代“未知键警告 + 缺凭据”的误导性行为。

## Impact

- `auto_check_in/config.py`：加载后输出识别数量日志；TOML `accounts` 键确定性报错。
- `auto_check_in/security.py`：新增 `mask_username` 脱敏用户名助手（保留首尾字符便于区分，不包含完整凭据子串）。
- `auto_check_in/models.py`：新增 `CheckInStatus.LOGIN_BLOCKED`（标签“登录被拦截”）。
- `auto_check_in/runner.py`、`auto_check_in/adapters/sijishe.py`：逐账号日志与结果使用脱敏用户名；登录提交 HTTP 4xx 归类为 `login-blocked`。
- `auto_check_in/cli.py`：摘要输出使用脱敏用户名。
- `README.md`：`***` 含义与账号识别核对、`登录被拦截` 排障说明。
- 测试：`tests/test_common.py`、`tests/test_sijishe.py` 新增用例；无新依赖；不触网。
