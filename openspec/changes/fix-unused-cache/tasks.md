## 1. 会话缓存遥测（应用侧）

- [x] 1.1 `auto_check_in/session.py`：新增 `SessionCacheStats`（frozen dataclass，`restored` / `rejected` / `saved` 默认 0），不改变 cookie JSON 结构与 `load_cookies` / `save_cookies` 签名
- [x] 1.2 `auto_check_in/adapters/sijishe.py`：`SijisheAdapter` 持有每站点独立 stats 实例；`_restore_session` 命中即 `restored += 1` 并记录脱敏日志（`site` / `mask_username` / cookie 数量），未命中记录 miss
- [x] 1.3 `sijishe.py` `run()`：恢复过 cookie 但 `_sign_in` 返回 `login-failed` 触发清 cookie 重登时 `rejected += 1` 并记录脱敏日志（不输出 cookie 值）
- [x] 1.4 `sijishe.py` `_persist_session`：实际写入成功即 `saved += 1` 并记录脱敏日志；跳过（无 `*_auth` cookie / `session_cache` 关闭）记录原因且计数不变
- [x] 1.5 `auto_check_in/models.py`：`RunSummary` 新增 `sessions_restored` / `sessions_rejected` / `sessions_saved` 字段（默认 0）；`render()` 末尾输出固定格式行 `会话缓存: 恢复 N / 被拒重登 N / 新保存 N`（仅在任一计数 >0 时输出，保持既有输出兼容）
- [x] 1.6 `auto_check_in/runner.py`：`_run_site` 从 adapter 取回 stats，`run()` 聚合进 `RunSummary`（站点并行下每站点实例独立，无共享）

## 2. 应用侧测试（stdlib unittest，不访问网络）

- [x] 2.1 单测：restore 命中/未命中 → 计数正确且日志含脱敏账号与 cookie 数量（沿用 `tests/helpers.py` FakeSession 模式）
- [x] 2.2 单测：restored 会话存在但签到返回 `login-failed` → `rejected += 1`、清 cookie 并重新登录
- [x] 2.3 单测：`_persist_session` 保存成功 `saved += 1`；无 `*_auth` cookie 时跳过且计数不变
- [x] 2.4 单测：`RunSummary.render()` 输出固定格式缓存计数行；全量 `uv run python -m unittest discover -s tests -v` 与 `compileall` 通过

## 3. CI 工作流改造（`.github/workflows/check-in.yml`）

- [x] 3.1 Restore 后新增 `Inspect session cache` 步骤：输出 `.runtime/sessions` 文件数与总大小（`find | wc -l` + `du -sh`）
- [x] 3.2 Save 前新增 `Prepare cache save` 步骤：无会话文件时输出 `skip=true`；`Save session cache` 改为 `if: always() && steps.prepare.outputs.skip != 'true'`，不再创建空缓存条目
- [x] 3.3 新增 `Verify cache reuse` 步骤：`steps.restore.outputs.cache-hit == 'true'` 且 summary 计数行 restored=0 或 saved=0 时输出 `::warning`（含 cache key 与计数），不改变 job 退出码
- [x] 3.4 确认 `tests/test_github_workflow.py` env 双向校验仍通过（本 change env 面零变化，工作流 `env` 不动）

## 4. 文档同步

- [x] 4.1 `README.md` 会话缓存章节：补充遥测行格式、CI 的 Inspect / Prepare / Verify 步骤与“空目录跳过保存”“未使用缓存告警”说明
- [x] 4.2 `openspec/config.yaml` context：补充会话缓存可观测性与 CI 校验边界，并记录 `SessionCacheStats` 单实例单线程约束
- [x] 4.3 新增文件确认 git 跟踪：`git status` 显示 A/M（本 change 无新源文件时仅确认改动文件被跟踪；`.runtime/` 保持 gitignore，会话文件不入库）

## 5. 验证与决策

- [x] 5.1 本地：`uv run auto-check-in --config config/check-in.toml --debug`（或 FakeSession 驱动的测试路径）确认日志出现 session-cache restore/save 事件与 summary 计数行
- [x] 5.2 CI：`workflow_dispatch` 手动触发一次，确认 Inspect / Prepare / Verify 步骤输出符合 spec（命中缓存但零复用时出现 warning）
- [x] 5.3 观测窗口：连续 ≥3 次定时运行，记录每次 `restored` / `rejected` / `saved` 计数（已记录 1 个有效点：run 1 `restored=1 / rejected=0 / saved=1`，会话复用成功、无重新登录；经用户确认提前关闭观测窗口，直接走分支 B）
- [ ] 5.4 决策分支 A（`saved=0` 或 `rejected == restored`，站点会话不跨运行）：移除 restore/save 与 Verify 步骤，同步 README / spec / `openspec/config.yaml`，收尾 `runtime-reliability` 相关需求（未采用：观测显示会话可复用）
- [x] 5.5 决策分支 B（出现复用成功）：`Verify cache reuse` 从 warning 升级为 fail（`cache-hit` 但零复用即失败），README 记录观测结论
- [x] 5.6 回滚：revert 即可，无数据迁移；旧会话文件格式兼容（本 change 不改 cookie JSON 结构）
