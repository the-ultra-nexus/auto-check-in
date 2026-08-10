## Why

CI 每次定时运行都会恢复会话缓存（日志：`Cache restored from key: sessions-Linux-refs/heads/main-31288082027`），但实测近 4 个运行产生的缓存条目始终只有 599 / 600 / 705 / 722 B——缓存里没有任何可复用的会话载荷，且应用与工作流都没有“会话是否被恢复、是否被站点接受、是否触发重新登录”的日志或校验。“缓存看起来未使用”只能靠人工翻 GitHub 缓存列表的字节数才能发现，属于静默失效。

## What Changes

- **应用侧会话缓存可观测性**（`session.py` / `adapters/sijishe.py` / `runner.py` / `models.py`）：
  - `_restore_session` 按账号记录命中/未命中与恢复的 cookie 数量（用户名脱敏）。
  - `_persist_session` 按账号记录保存成功/跳过及原因（无 `*_auth` cookie、`session_cache` 关闭）。
  - 新增“恢复后会话被站点拒绝 → 清 cookie 重新登录”的判定与日志（`session-rejected`）。
  - `RunSummary` 增加会话缓存计数（`restored` / `rejected` / `saved`），渲染进输出与通知，让缓存是否真正被复用直接在日志与通知里可见。
- **CI 工作流缓存卫生**（`check-in.yml`）：
  - Restore 后列出 `.runtime/sessions` 的文件数与大小，运行日志可见恢复了什么。
  - Save 前校验：不存在会话文件或文件未变化时跳过保存，不再创建 ~700 B 的空缓存条目。
  - 校验步骤：`cache-hit=true` 但应用报告 `restored=0` 或 `saved=0` 时输出告警（可选失败），自动暴露“未使用缓存”而不是静默通过。
- **根因验证与决策任务**：遥测上线后连续观测定时运行；若恢复的会话每次都被站点拒绝（`rejected == restored`，站点 IP 绑定或会话失效），则按决策移除 CI 的 restore/save 步骤并同步文档与 spec；否则保留缓存并凭日志证明复用。
- **非目标**：不改登录/签到行为与失败语义；不新增 env（env 面零变化，无需动 `.env.example` 的 `@ci` 标记）；不改代理池策略；不动通知渠道。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `runtime-reliability`: 扩展现有 “Workflow session cache correctness” 需求——会话缓存的恢复/保存必须可观测、可验证（应用侧 restore/persist 日志与汇总计数；CI 跳过空保存；`cache-hit` 但未复用未保存时告警），空缓存条目不再静默产生。
- `operations-and-observability`: 新增会话缓存计数需求——运行汇总输出与日志 SHALL 包含按账号的会话恢复/保存事件与汇总计数（脱敏），使“缓存是否被使用”可审计。

## Impact

- `auto_check_in/session.py`：恢复/保存事件日志与计数入口（无 cookie 结构变化，兼容既有会话文件）。
- `auto_check_in/adapters/sijishe.py`：`_restore_session` / `_persist_session` 记录命中/保存/跳过，`run()` 记录 restored→rejected→relogin 链路。
- `auto_check_in/models.py` + `runner.py`：`RunSummary` 新增会话缓存计数并渲染进 `render()` 输出。
- `.github/workflows/check-in.yml`：restore 后内容清单、save 前置校验、复用校验告警步骤。
- `tests/`：会话缓存计数/日志单测（stdlib unittest，不访问网络）与工作流校验逻辑测试。
- 文档同步：`README.md` 会话缓存章节补充遥测与 CI 校验说明；`openspec/config.yaml` context 补充会话缓存可观测性边界（本 change 触及全局运行时行为，按规则同步两处）。
- 依赖：无新增；无数据迁移；env 面不变。
