## Context

- `notify.py` 是根目录顶层模块，wheel 只打包 `auto_check_in`；安装后入口在非项目根目录运行时 `from notify import send` 可能失败。模块内含全局 `push_config`、`print` 猴子补丁、无超时的“一言”请求和线程发送。
- 工作流 `actions/cache/restore` 与 `actions/cache/save` 使用同一 key：第二次运行起 save 会因 key 已存在而失败，稳定 key 下缓存不会刷新。
- `--dry-run` 只解析账号，未校验 `ADAPTERS` 注册表。
- 无日志、汇总不区分站点、无运行计时、无请求间隔控制。
- 会话缓存（`.runtime/sessions`）与 `SITE_CONFIGS` 工作流已实现但未回填规划文档。

## Goals / Non-Goals

**Goals:**

- 通知模块打包进 wheel，发送异常不影响退出码，无外部一言依赖，每渠道请求有超时。
- 引入脱敏结构化日志与按站点分组汇总。
- GitHub Actions 会话缓存可恢复且每日刷新；手动触发可选站点。
- dry-run 与真实运行同一套校验；未知配置键告警、必填/类型错误汇总。
- 会话缓存可配置过期重登；记录各站点耗时。

**Non-Goals:**

- 不做“仅失败通知”——每天照常通知。
- 不做 VCR 录制回放 e2e fixture。
- 不改变登录、签到、多站点并行业务逻辑。

## Decisions

1. **通知重写（通道注册表）**：新建 `auto_check_in/notify.py`，`send(title, content)` 按环境变量启用渠道；每个渠道为独立函数并带 `timeout`；删除全局可变 `push_config`、`print` 猴子补丁与 `one()`/一言追加。CLI 用 `try/except` 包裹发送并告警，退出码仍由签到结果决定。
2. **传输层抽象**：`http.py` 提供 `SessionProvider`（随机 UA、默认超时、可注入 retry），适配器通过 provider 创建会话，不再各自 `import requests`。
3. **结构化日志**：stdlib `logging`，logger 名 `auto_check_in`；每站点/账号输出脱敏日志（站点、账号、状态、耗时）；级别由 `CHECK_IN_LOG_LEVEL` 或 `--debug` 控制。
4. **分组汇总**：`AccountResult` 增加 `site` 字段，`RunSummary.render()` 按站点分组输出 `【站点名】` 分块；通知正文与日志一致。
5. **工作流**：缓存 save 用唯一 key `sessions-<os>-<ref>-<run_id>`，restore 用 `restore-keys` 前缀；`workflow_dispatch.inputs.sites` 覆盖 `CHECK_IN_SITES`。
6. **请求间隔**：新增 `CHECK_IN_REQUEST_DELAY`（默认 3），站点内账号间等待该秒数并加 ±20% 随机抖动，设 0 关闭。
7. **配置校验**：未知键收集为警告；必填/类型错误跨站点汇总后一次性抛出 `ConfigError`；`validate_config` 由 runner 与 dry-run 共用。
8. **会话 TTL**：`save_cookies` 写入 `saved_at`；`CHECK_IN_SESSION_MAX_AGE`（默认 0=关闭）超过时限时忽略缓存直接重登。
9. **运行计时**：runner 用 `time.perf_counter` 记录每站点耗时并输出日志。
10. **文档回填**：README/openspec 上下文更新；`migrate-to-api-check-in` 的 design/specs 补会话缓存与 `SITE_CONFIGS` 章节。
11. **User-Agent 池**：`http.py` 内置常见桌面浏览器 UA 池，`SessionProvider` 与 `ua_headers` 每次请求随机取用；`notify` 复用同一池，不引入任何 UA 配置项；移除 `CHECK_IN_USER_AGENT` 与 `[network] user_agent`，避免用户手动维护 UA。

## Risks / Trade-offs

- [通知重写破坏现有渠道行为] → 保留渠道环境变量与 `send(title, content)` 接口；测试覆盖主要渠道选择逻辑。
- [分组汇总改变输出格式] → 属预期变更，同步更新测试与 README。
- [请求间隔拖慢多账号] → 默认 0 保持现状，仅按需开启。
- [会话 TTL 默认关闭] → 不改变现有行为；开启后减少无效缓存验证请求。
- [缓存唯一 key 增多条目] → 单条体积小，GitHub 按 7 天未使用淘汰，总量受 10GB 上限约束。
- [随机 UA 可能被站点风控] → 池内置常见浏览器版本并保持更新；如站点需要固定 UA，再以独立需求引入配置覆盖。

## Migration Plan

1. 重写并移动通知模块，更新 CLI 与文档。
2. 实现传输层、日志、分组汇总。
3. 更新工作流（缓存 key + 手动站点输入）。
4. 加请求间隔、配置校验、会话 TTL、计时。
5. 回填文档、补测试、全套验证后归档。

## Open Questions

- 无未决问题。
