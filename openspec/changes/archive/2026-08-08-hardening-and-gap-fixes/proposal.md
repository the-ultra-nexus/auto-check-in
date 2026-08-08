## Why

从头审计发现：通知模块 `notify.py` 不在安装包内且是带全局状态/无超时的遗留单文件；没有任何日志；汇总不区分站点；GitHub Actions 会话缓存同 key 恢复/保存会失败；`--dry-run` 不校验适配器注册；传输层、配置校验、会话缓存生命周期和运行观测都存在可加固空间。

## What Changes

- **BREAKING** 以小型通道注册表重写通知模块并移入包内：移除全局 `push_config`、`print` 猴子补丁与一言逻辑，保留 `send(title, content)` 接口与现有渠道环境变量，每渠道独立超时；CLI 发送异常隔离，不影响退出码。
- 新增 stdlib 结构化日志：每站点/每账号一行（脱敏），级别可用 `CHECK_IN_LOG_LEVEL` 或 `--debug` 控制。
- 汇总按站点分组输出（`【站点名】` 分块），通知正文与日志一致。
- 工作流：会话缓存唯一 key + `restore-keys` 回退；`workflow_dispatch` 增加站点输入覆盖 `CHECK_IN_SITES`。
- 新增可选请求间隔 `CHECK_IN_REQUEST_DELAY`（默认 0，含账号间抖动）。
- 传输层抽象：`SessionProvider`（UA 池、超时、重试）下沉到 `http.py`，适配器统一获取会话。
- User-Agent 池：`notify` 与 HTTP 会话从同一个内置 UA 池随机取用，无需配置；移除 `CHECK_IN_USER_AGENT` / `[network] user_agent` 配置项与通知模块硬编码 UA。
- 配置校验强化：未知键告警；必填/类型错误跨站点汇总后一次性报出。
- 会话缓存写入时间戳，支持 `CHECK_IN_SESSION_MAX_AGE` 过期直接重登（默认关闭）。
- 运行计时：记录并输出每个站点耗时。
- 文档回填：README 与 OpenSpec 上下文更新；`migrate-to-api-check-in` 的规格/设计补上会话缓存与通用多站点工作流。

**Non-Goals**：保持每天通知（不做“仅失败通知”）；不做 VCR 录制回放类 e2e fixture。

## Capabilities

### New Capabilities

- `runtime-reliability`: 通知重写、传输层抽象、dry-run 校验、工作流缓存正确性、配置校验与会话缓存生命周期。
- `operations-and-observability`: 结构化日志、按站点分组汇总、手动站点选择、请求间隔与运行计时。

### Modified Capabilities

- 无（仓库尚无主规格，本变更以增量规格定义新行为）。

## Impact

- 重写并移动 `notify.py`；更新 `cli.py`、`http.py`、`runner.py`、`models.py`、`session.py`、`config.py`、`sijishe.py`。
- 更新 `.github/workflows/check-in.yml`（缓存 key、workflow_dispatch 输入）。
- 补充测试并回填规划文档。
