# Configuration Guidelines

> 配置系统的单一入口：`auto_check_in/config.py`。TOML 只放非敏感默认，凭据一律环境变量，
> 严格校验、未知键警告、错误聚合。改动配置前先读本文件与 `tests/test_common.py`。

## 配置来源与优先级

```
环境变量 > SITE_CONFIGS (JSON Secret) > TOML [sites.<name>] 节 > 代码默认值
```

- 通用变量前缀 `CHECK_IN_`（如 `CHECK_IN_SITES`、`CHECK_IN_SESSION_CACHE`、
  `CHECK_IN_MAX_WORKERS`）；站点级前缀 `SITE_<NAME>_`（站点名大写、`-`→`_`），
  如 `SITE_SIJISHE_BASE_URL`、`SITE_SIJISHE_ACCOUNTS`。
- 站点名正则 `^[A-Za-z0-9_]+$`（`_site_env_prefix`），非法名抛 `ConfigError`。
- 启用站点：`CHECK_IN_SITES`（逗号分隔）> `SITE_CONFIGS` 的键集合 > `[runtime] enabled_sites`；
  全部为空 → `ConfigError`。
- 账号格式 `账号&密码`，多个账号用 `@` 或换行分隔（`parse_accounts`）；密码内允许 `&`
  （用 `partition` 取第一个分隔符，见 `test_parse_accounts_supports_at_and_newline`）。

## 敏感信息铁律（config.py 强制拒绝，非忽略）

| 禁止项 | 检测点 | 行为 |
|--------|--------|------|
| `sites.<name>.accounts / password / passwd / secret / token / cookie(s)` | `_SENSITIVE_SITE_KEYS` | `ConfigError` + 指引 `SITE_<NAME>_ACCOUNTS` |
| `[network]` / `[sites.*.network]` 的 `proxy_urls` / `proxy_pool_urls` | 显式检查 | `ConfigError` + 指引 `CHECK_IN_PROXY_POOL_URLS` |
| `sites.<name>.direct_first` | 显式检查 | `ConfigError` + 指引 `SITE_<NAME>_DIRECT_FIRST` / SITE_CONFIGS |

凭据只允许经环境变量 / `SITE_CONFIGS` JSON Secret 提供；`SITE_CONFIGS` 必须合法 JSON 对象，
否则 `ConfigError`。

## 校验模式（config.py 内部助手）

- `_bool`：接受 `bool` 或 `1/true/yes/on`（含 `0/false/no/off`），否则 `ConfigError`。
- `_positive_int`：正整数校验，非法抛 `ConfigError`（消息中文）。
- 延迟/有效期类（`retry_delay_seconds`、`request_delay_seconds`、
  `session_max_age_seconds`）显式拒绝负数。
- `_warn_unknown(section, data, allowed)`：未知键记 `logger.warning`
  （`配置警告: <section> 中存在未知键 <key>`），不静默忽略、不致命。
- 键集合常量（`_TOP_LEVEL_KEYS` / `_RUNTIME_KEYS` / `_NOTIFICATION_KEYS` / `_SITE_KEYS` /
  `_NETWORK_KEYS`）是白名单的唯一事实来源；**新增配置键必须同步**对应集合 + `_warn_unknown`
  调用 + `.env.example` + CI 工作流。

## 错误聚合

`load_config` 逐站点收集错误到 `errors` 列表，最后一次性抛：
`ConfigError("配置错误：\n" + "\n".join(errors))` —— 一个站点配错不吞掉其他站点的报错，
CLI 打印全部后以退出码 2 结束（`cli.py`）。

## 加载入口

- `load_config(path=None, environ=None)`：`environ` 参数可注入（测试用，`test_common.py`
  大量用例）；默认读 `os.environ`；`path` 缺省取 `AUTO_CHECK_IN_CONFIG` env，
  再缺省 `config/check-in.toml`（`DEFAULT_CONFIG_PATH`）。
- 配置文件不存在时视为空 TOML（全走环境变量）；存在但读不了/解析失败 → `ConfigError`。
- `load_notify_settings()`：只读通知标题/开关，供 `--notify-only` 使用，
  不要求站点配置存在（通知测试不需要凭据）。

## 返回值契约

- 不可变数据类：`NetworkConfig` / `SiteConfig` / `CheckInConfig`
  （`@dataclass(frozen=True, slots=True)`，`config.py`）。
- `base_url` 统一 `rstrip("/")` 规范化；`sign_path` 默认 `/k_misign-sign.html`。
- 启动时对每个启用站点打印 `site=<name> accounts=<N> recognized`（INFO）作为账号识别信号
  （README 强调：CI 日志 `account=***` 是 GitHub 自动脱敏，不代表未识别）。

## 新增配置项检查清单

1. 定义默认值字段（数据类）+ 环境变量读取（`_env` + 覆盖优先级）。
2. 加入对应白名单集合（顶层/runtime/站点/网络），避免 `_warn_unknown` 误报。
3. 敏感项：在 `load_config` 加显式拒绝检查（参照代理池/direct_first 模式）。
4. `.env.example` 登记 + 需要时标 `@ci:secrets` / `@ci:vars` 并同步 CI 工作流
   （`tests/test_github_workflow.py` 双向校验）。
5. `tests/test_common.py` 补解析/覆盖/校验用例。

## 反模式

- CLI 或其他模块直接读 `os.environ` 绕过 `config.py`（配置事实来源唯一）。
- TOML 写凭据类键期望"运行时忽略"——会被 `ConfigError` 拒绝，且这是有意设计。
- 校验失败用 `assert` 或裸 `ValueError`（必须 `ConfigError`，带中文指引）。
- 新增键忘记加进白名单 → 用户每次运行收到未知键警告。
