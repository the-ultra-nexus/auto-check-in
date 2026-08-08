## Context

上个需求 `add-recipient-email-and-ip-proxy` 实现了 `CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS` 的解析、轮换与脱敏，README 也写明“GitHub Actions 中把代理地址放入 Secret（如 `SITE_SIJISHE_PROXY_URLS`），并在工作流 `env` 中映射后再使用”，但 `.github/workflows/check-in.yml` 的 `env` 从未映射这两个变量。当前工作流 `env` 只覆盖 `SITE_CONFIGS`、`CHECK_IN_SITES`（仓库变量）与通知渠道 Secrets，代理 Secret 配了也不生效，签到仍走 runner 出口 IP。

约束：凭据与令牌只能经环境变量/GitHub Secret 注入；仓库测试用 stdlib `unittest`（README：`uv run python -m unittest discover -s tests -v`），当前无 pytest/PyYAML 依赖，不宜新增。

## Goals / Non-Goals

**Goals:**
- 工作流 `env` 补齐 `CHECK_IN_PROXY_URLS` 与 `SITE_SIJISHE_PROXY_URLS` 的 Secret 映射，使代理配置在 CI 中真正生效。
- 新增自动化检查：工作流 `env` 必须覆盖文档化的全部 CI 环境变量，缺漏时在 CI 中失败（fail-loud），杜绝“运行时支持但工作流漏映射”再犯。
- 仓库根目录新增 `.env.example`，作为环境变量清单的单一事实来源；README 与工作流都是派生/校验对象，不再各自维护一份清单。

**Non-Goals:**
- 不改动代理解析、轮换、脱敏、会话缓存等运行时行为。
- 不新增/调整未启用的通知渠道映射（`PUSH_PLUS_TOKEN`、`DEER_KEY`、`WEBHOOK_URL`、`NTFY_TOPIC` 等）。
- 不改动工作流触发方式（保持 schedule + workflow_dispatch），不新增 PR 专用 CI 工作流。

## Decisions

1. **工作流映射两个代理变量**：`CHECK_IN_PROXY_URLS: ${{ secrets.CHECK_IN_PROXY_URLS }}` 与 `SITE_SIJISHE_PROXY_URLS: ${{ secrets.SITE_SIJISHE_PROXY_URLS }}`。理由：README 同时文档化了全局与站点级两种方式，站点级优先；两个都映射才能保证任一配置方式在 CI 生效。未配置 Secret 时表达式求值为空字符串，运行时按未设置处理，不影响不使用代理的仓库。

2. **防遗漏机制 = `.env.example` 标记 + stdlib unittest 双向校验**：`.env.example` 是环境变量清单的单一事实来源，`# @ci:secrets` / `# @ci:vars` 标记声明“CI 必须透传”的变量（标记 ≠ 必须配置 Secret，只要求“配置了就透传”）。`tests/test_github_workflow.py` 从 `.env.example` 标记读取期望集合，正则解析工作流 `env` 块，做双向断言：标记变量必须已映射且来源正确；工作流引用的 `secrets.X` / `vars.X` 必须已在 `.env.example` 声明且标记一致。备选方案：
   - 代码内硬编码 `EXPECTED_WORKFLOW_ENV` 白名单 → 与 `.env.example` 形成两份清单，正是本次 bug 的根因（多处各存一份、无人校验一致），弃用。
   - 动态扫描 README 提取变量 → 不可靠，README 含大量非 CI 变量（`CONSOLE`、`CHECK_IN_SESSION_*` 等），会误报。
   - PyYAML 解析工作流 → 需要新增测试依赖，与仓库“零测试依赖、stdlib unittest”的现状冲突。
   - 选择针对本工作流固定缩进格式的正则解析（`KEY: ${{ secrets.KEY }}` / `vars.KEY`，兼容 `inputs.x || vars.Y`），零依赖、可读。

3. **检查随 CI 每次运行执行**：在 check-in.yml 的 “Install dependencies” 之后新增 “Verify env coverage” step，运行 `uv run python -m unittest tests.test_github_workflow -v`；失败即终止 run。备选方案：新建 push 触发的 `ci.yml` 在 PR 阶段反馈更快，但超出最小改动且本仓库目前仅一个工作流，留作后续演进。

4. **`.env.example` 是单一事实来源**：新增/修改环境变量时先改 `.env.example` 与标记，再同步工作流 `env` 映射；README 为派生文档。测试双向校验保证任意一侧漏改都会红。

## Risks / Trade-offs

- [正则解析对工作流格式敏感] → env 块格式变化时测试失败并指明期望格式，属预期信号，更新测试即可。
- [覆盖率检查失败会阻断定时签到] → 正是 fail-loud 设计：补上映射后重跑即恢复，避免静默失效。
- [`.env.example` 标记本身可能漏列未来新变量] → 由 README 同步、`--check-sources` 类源码扫描（后续可选）与代码评审约束；测试只保证已标记变量不漏映射。
- [未标记变量实际被工作流引用] → 反向校验会报“工作流引用了 `.env.example` 未声明的变量”，强制补声明。
- [新增文件被 `.gitignore` 静默忽略] → 新文件必须确认被 git 跟踪（`git status` 显示 `A`/`M`）；本次 `.env.example` 即被 `.env.*` 规则吞掉，由 CI 的 env 一致性检查在 checkout 后拦截，修复为增加 `!.env.example` 例外。
- [代理 Secret 配置错误/失效] → 沿用现有 `site-unavailable` 状态与通知机制暴露，本变更不改变该行为。

## Migration Plan

1. 修改 `.github/workflows/check-in.yml`：`env` 增加两个代理变量映射，新增 “Verify env coverage” step。
2. 新增 `.env.example`：收录 `config.py` / `notify.py` 读取的全部环境变量与 `SITE_<NAME>_*` 动态前缀说明，CI 必透传的加 `# @ci:secrets` / `# @ci:vars` 标记；同时 `.gitignore` 增加 `!.env.example` 例外，确保文件能被提交。
3. 新增 `tests/test_github_workflow.py`（stdlib unittest，双向校验 + 正反例）。
4. 更新 `README.md`：补充 `.env.example` 指引与代理 Secrets 清单。
5. 本地验证：`uv run python -m unittest tests.test_github_workflow -v`，再跑全量 `uv run python -m unittest discover -s tests -v`。
6. 手动触发 `workflow_dispatch` 确认工作流绿色；仓库 Settings 无需改动（代理 Secret 按需配置）。
7. 回滚：仅涉及工作流、`.env.example`、`.gitignore`、测试与 README，直接 revert 即可，无数据/凭据迁移。

## Open Questions

- 是否顺带映射未启用的通知渠道（`PUSH_PLUS`、PushDeer、Webhook、ntfy）？当前不在启用范围，建议留作独立需求。
- 是否引入 pre-commit 钩子，把全量测试与 env 一致性检查从“推送后 CI”提前到“提交前本地”？本次遗漏证明本地测试拦不住 git 静默忽略，钩子可作为后续增强。
