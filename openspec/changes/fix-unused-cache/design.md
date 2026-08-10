## Context

`.github/workflows/check-in.yml` 的会话缓存机制本身工作正常：restore 按 `sessions-${{ runner.os }}-${{ github.ref }}-` 前缀命中最近一次运行（实测 run 31346920865 恢复了 31288082027 的缓存），save 每次用 `github.run_id` 生成唯一 key 无碰撞（现有 spec `runtime-reliability` 的 “Workflow session cache correctness” 已覆盖）。问题在内容与可验证性：

- 近 4 个缓存条目只有 599 / 600 / 705 / 722 B（约等于一个空目录或单条短 cookie），说明缓存没有可复用的会话载荷价值。
- 应用从不记录“恢复了几个账号的 cookie、保存了几个、是否被站点拒绝后重登”；工作流也从不校验缓存内容。README 虽写明“runner 出口 IP 可能变化导致 cookie 失效，此时会自动重新登录”，但没有任何遥测能区分“缓存未命中”“恢复但被站点拒绝”“恢复且复用成功”。

约束：无 pytest/PyYAML（stdlib unittest）；日志必须脱敏（`mask_username` / `redact_text`）；env 面变化必须同步 `.env.example` / workflow env / `tests/test_github_workflow.py`；不改登录/签到行为；站点为外部集成边界，恢复的 cookie 是否有效由站点决定，本 change 只负责“看得见”。

## Goals / Non-Goals

**Goals:**
- 让“缓存是否被使用”在每次运行的日志与通知里可见：按账号记录恢复命中/保存/被拒重登，汇总计数进入输出。
- CI 停止制造 ~700 B 的空缓存条目：会话文件不存在/无内容时跳过 save。
- CI 自动暴露“restore 命中但应用未复用/未保存”的场景（warning 起步），不再靠人工翻缓存列表。
- 用观测数据回答根因：恢复的会话是被站点拒绝（IP 绑定/会话失效）还是从未保存（登录被拦）。
- 本地与 CI 行为一致：遥测在应用内实现，不依赖解析第三方 action 输出。
- 文档同步：`README.md` 会话缓存章节与 `openspec/config.yaml` context 更新。

**Non-Goals:**
- 不改登录/签到行为、失败语义（`login-failed` / `login-blocked` / `site-unavailable` 归属不变）。
- 不新增 env / 不改 `.env.example` `@ci` 标记（工作流新增步骤不涉及 env 面）。
- 不改代理池策略与通知渠道。
- 不承诺“让缓存一定被复用”——站点侧是否接受 cookie 不可控，本 change 交付的是可观测性与空保存卫生，以及据此的决策路径。

## Decisions

1. **遥测放在应用内，计数随 `RunSummary` 输出**：
   - `session.py` 新增 `SessionCacheStats`（frozen dataclass：`restored` / `rejected` / `saved`，均默认 0）。
   - `SijisheAdapter` 持有每站点实例独立的 stats；`_restore_session` 命中即 `restored += 1`，`_persist_session` 实际写入成功即 `saved += 1`，`run()` 中“恢复过 cookie 但 `_sign_in` 返回 `login-failed` 触发清 cookie 重登”即 `rejected += 1`。
   - runner 从 adapter 取回 stats 聚合进 `RunSummary`（新增三字段），`render()` 末尾追加一行（如 `会话缓存: 恢复 1 / 被拒重登 1 / 新保存 1`）；通知随之携带。
   - 备选：在 `AccountResult` 上增加字段 → 冻结 dataclass 与大量测试断言改动面大，弃用。备选：从日志解析计数 → 脆弱、耦合日志格式，弃用。
2. **每站点实例独立 stats，无跨线程共享**：runner 站点并行（`ThreadPoolExecutor`）时每站点一个 adapter 实例，stats 不跨实例共享，天然线程安全；若未来单实例多线程需加锁，记录为显式约束。
3. **日志事件与计数分离**：事件级日志沿用现有 `logger.info/debug`（脱敏：`site=... account=al*** session-cache restored=2`），不输出 cookie 值；计数只进 summary。理由：日志用于排障，summary 用于 CI 校验与通知。
4. **CI 三步改造**（均不涉及 env 面）：
   - Restore 后新增 `Inspect session cache`：输出 `.runtime/sessions` 文件数与总大小（`find | wc -l` + `du -sh`），让“恢复了什么”直接进日志。
   - Save 前新增 `Prepare cache save`：统计会话文件数，输出 `skip=true/false`；`Save session cache` 步骤改为 `if: always() && steps.prepare.outputs.skip != 'true'`，杜绝空条目。
   - 新增 `Verify cache reuse`：应用把计数渲染进 stdout 固定行（`会话缓存: ...`），该步骤 grep `steps.restore.outputs.cache-hit` 与计数——`cache-hit=true` 且 `restored=0` 或 `saved=0` 时输出 `::warning`（不 fail，先告警后决策）。
   - 备选：解析 actions/cache 的 tar 输出大小判断 → 依赖 action 内部实现，弃用。
5. **根因决策路径（观测驱动）**：遥测上线后连续 ≥3 次定时运行：
   - 若 `saved=0` → 登录在 CI 被拦/未产生 `*_auth` cookie（与代理/IP 有关），缓存无物可存 → 移除 restore/save 步骤并同步 README/spec。
   - 若 `restored>0` 且 `rejected == restored` → 站点会话不跨运行（IP 绑定或服务端失效）→ 移除 restore/save 步骤（保留遥测计数，日志/通知仍显示每次重登），README 明确“CI 缓存已移除”的结论与依据。
   - 若 `rejected < restored` 或出现复用成功 → 保留缓存，`Verify cache reuse` 从 warning 升级为 fail（任何 `cache-hit` 但零复用即失败）。
   - 决策不写死在代码里：判定标准落在 tasks 的验证清单，由实施者在观测窗口结束后选择保留/移除分支。
6. **不新增 env 与配置项**：遥测默认开启，日志级别沿用现有 `CHECK_IN_LOG_LEVEL` / `--debug`；工作流新步骤为 CI 专属脚本，无配置面。`.env.example` 与 `tests/test_github_workflow.py` 无需改动（env 面零变化）。
7. **文档同步**：`README.md` 会话缓存章节补充遥测行格式与 CI 校验/跳过空保存说明；`openspec/config.yaml` context 补充“会话缓存可观测性与 CI 校验”边界（本 change 触及全局运行时行为，按规则同步）。

## Risks / Trade-offs

- [站点会话被 IP 绑定，缓存永远无法复用] → 遥测先行；若观测证实，按决策 5 移除 restore/save，避免继续制造死缓存与噪音。
- [`Verify cache reuse` 在 IP 绑定场景必然告警] → 设计为 `::warning` 而非 fail；移除分支落地后告警自然消失，不会造成 CI 常红。
- [grep 解析 summary 行脆弱] → 计数行格式固定（`会话缓存: ...`）且由 `render()` 单点输出，工作流只做前缀匹配；单测覆盖该行格式。
- [空保存守卫误跳过有效保存] → 跳过条件仅为“无会话文件”，有文件即保存；key 含 `run_id` 无同 key 碰撞，不丢数据。
- [并行站点未来共享 stats 的线程安全] → 当前每站点独立实例；在 `SessionCacheStats` 文档注释与 config.yaml context 中记录“单实例单线程”约束。

## Migration Plan

- 纯增量：先合入遥测 + 工作流校验（warning 模式），连续观测 ≥3 个运行日；再按决策 5 的观测结果合入“保留（升级 fail）”或“移除 restore/save”的收尾改动。
- 回滚：revert 即可，无数据迁移；旧会话文件与现有 `load_cookies`/`save_cookies` 格式完全兼容（本 change 不改 cookie JSON 结构）。

## Open Questions

- 站点（sijishe）是否绑定出口 IP 使 cookie 跨运行必然失效——由观测任务回答，不阻塞本 change 交付。
- 观测窗口结束后 `Verify cache reuse` 是否升级为 fail——由决策 5 的标准确定。
