## Why

上个需求 `add-recipient-email-and-ip-proxy` 引入了 `CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS` 环境变量，README 也写明“GitHub Actions 中把代理地址放入 Secret，并在工作流 `env` 中映射后再使用”，但 `.github/workflows/check-in.yml` 的 `env` 从未映射这两个变量：CI 里配置 `SITE_SIJISHE_PROXY_URLS` Secret 会被静默忽略，签到仍走 runner 出口 IP。这类“运行时支持的环境变量漏同步到 GitHub 工作流”的问题已第二次出现，需要补上映射，并用自动化检查杜绝再犯；同时本地仓库缺少一份权威的环境变量清单，环境变量分散在代码、README、工作流多处，正是遗漏的土壤。

## What Changes

- `.github/workflows/check-in.yml` 的 `env` 增加代理变量映射：`CHECK_IN_PROXY_URLS: ${{ secrets.CHECK_IN_PROXY_URLS }}` 与 `SITE_SIJISHE_PROXY_URLS: ${{ secrets.SITE_SIJISHE_PROXY_URLS }}`（站点级优先于全局）。
- 仓库根目录新增 `.env.example`：环境变量清单的单一事实来源，用 `# @ci:secrets` / `# @ci:vars` 标记声明“CI 必须透传”的变量；未标记变量仅本地使用、不要求进 CI。
- 新增自动化测试：从 `.env.example` 标记读取期望集合，解析工作流 `env` 做双向校验——标记变量必须已映射且来源正确；工作流引用的变量必须已在 `.env.example` 声明且标记一致。缺漏时测试失败并在 CI 中阻断，防止未来新增环境变量再次漏同步；该测试随 CI 每次运行执行。
- `README.md` 的 GitHub Actions Secrets 清单补充代理变量（`CHECK_IN_PROXY_URLS` / `SITE_SIJISHE_PROXY_URLS`），并补充 `.env.example` 指引，与工作流映射保持一致。
- 非目标：不改动代理解析、轮换或脱敏等运行时行为；不改动其他站点的工作流映射（当前仅启用了 sijishe）。

## Capabilities

### New Capabilities
- `github-actions-env`: GitHub Actions 工作流的 `env` 映射与 `.env.example` 声明的 CI 环境变量（`@ci:secrets` / `@ci:vars` 标记）保持一致，缺漏时由自动化测试在 CI 中阻断。

### Modified Capabilities
<!-- 无运行时需求变化 -->

## Impact

- `.github/workflows/check-in.yml`：`env` 增加两个 Secret 映射，行为影响仅限已配置代理 Secret 的仓库。
- `.env.example`（新增）：环境变量清单，纯声明、不含任何凭据。
- `tests/test_github_workflow.py`（新增）：纯本地解析与断言，不访问网络。
- `README.md`：GitHub Actions 配置章节更新。
- 依赖：无新增；凭据仍只经 GitHub Secret 注入，不进入仓库。
