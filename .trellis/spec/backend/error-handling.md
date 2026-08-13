# Error Handling

> 分层错误模型：异常只在适配器内部出现，跨层边界一律转成 `AccountResult` + `CheckInStatus`。

## 异常层次（`auto_check_in/errors.py`）

```text
Exception
├── ConfigError(ValueError)          # config.py：配置/凭据不可用时提前抛出
├── LoginError                       # 适配器：登录无法完成
│   └── LoginBlockedError(LoginError) # 站点拒绝登录提交本身（HTTP 4xx，防机器人/封 IP）
├── CheckInError                     # 适配器：签到无法完成
└── SiteUnavailableError             # 适配器：无可用的站点端点
```

- `ConfigError` 由 `config.py` / `runner.run()` 抛出，CLI 捕获后打印 `配置错误: ...` 到
  stderr 并以退出码 **2** 结束（`cli.py`）。
- `LoginBlockedError` 用于区分「凭据/站点状态问题」（可重登）与「站点主动拦截」
  （防机器人校验、封禁出口 IP），见 `sijishe.py::_post_login` 对 `400 <= code < 500` 的处理。

## 核心原则：适配器 `run()` 永不向调用方抛业务异常

`SijisheAdapter.run` 把一切异常转换为 `AccountResult(status=CheckInStatus.*)`：

| 捕获的异常 | 映射状态 | 参考位置 |
|-----------|---------|---------|
| `LoginBlockedError` | `LOGIN_BLOCKED` | `adapters/sijishe.py::run` |
| `LoginError` | `LOGIN_FAILED` | 同上 |
| `CheckInError` | `CHECK_IN_FAILED` | 同上 |
| `requests.RequestException` | `SITE_UNAVAILABLE`（消息脱敏截断 200 字符） | 同上 |
| 其他 `Exception` | `ERROR`（消息脱敏截断 200 字符） | 同上 |

消息中的异常文本必须经 `redact_text(...)` 后使用（可能含 URL/凭据片段）。

## 状态枚举（`auto_check_in/models.py`）

`CheckInStatus(StrEnum)` 是唯一跨层状态语言，成员：

`SUCCESS` / `ALREADY_CHECKED_IN` / `LOGIN_FAILED` / `LOGIN_BLOCKED` /
`SITE_UNAVAILABLE` / `CHECK_IN_FAILED` / `CONFIG_ERROR` / `ERROR`

- `successful` 属性：`SUCCESS` 与 `ALREADY_CHECKED_IN` 视为成功（幂等语义）。
- `label` 属性：面向用户的中文标签（通知用）。
- 新增状态必须同时更新 `successful` 与 `label`，否则通知/退出码会失真。

## 编排层隔离（`runner.py`）

- `run()` 先**全量校验**（站点非空、适配器已注册、账号可解析），失败立即抛
  `ConfigError` —— 不启动任何站点请求。
- 每个站点在独立 `ThreadPoolExecutor` 任务里执行（`_run_site`）；单账号处理抛异常
  → 记为该账号 `ERROR`；整个站点任务抛异常 → 记为 `<site>` 的 `ERROR`。
  一个站点的失败不影响其他站点。

## 退出码约定（CLI）

| 码 | 含义 | 位置 |
|----|------|------|
| 0 | 全部成功（`RunSummary.successful`） | `RunSummary.exit_code` |
| 1 | 存在失败结果 | 同上 |
| 2 | 配置错误 / 通知测试不可用 | `cli.py::main` |

## Discuz 响应分类

`discuz.py::classify_discuz_response` 把签到接口返回文本归类为
`SUCCESS` / `ALREADY_CHECKED_IN` / `LOGIN_FAILED` / `CHECK_IN_FAILED`；
已签判定优先用 `DISCUZ_ALREADY_MARKERS`（"今日已签" 等中文标记）。
解析失败的兜底是 `CHECK_IN_FAILED`，不要往上层抛原始 HTML。

## 反模式

- 适配器直接向 runner 抛原始 `requests` 异常或任意 `Exception` —— 必须转成
  `AccountResult`（runner 会兜底转 `ERROR`，但消息会丢失具体状态语义）。
- 在 `config.py` 用裸 `assert` 或 `raise ValueError` —— 必须用 `ConfigError`（带中文指引）。
- 把 URL/响应文本原样写进结果消息 —— 先 `redact_text` 再截断。
