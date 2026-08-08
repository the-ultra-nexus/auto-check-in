## 1. 工作流补映射

- [x] 1.1 `.github/workflows/check-in.yml` 的 `env` 增加 `CHECK_IN_PROXY_URLS: ${{ secrets.CHECK_IN_PROXY_URLS }}`（全局代理列表）
- [x] 1.2 `.github/workflows/check-in.yml` 的 `env` 增加 `SITE_SIJISHE_PROXY_URLS: ${{ secrets.SITE_SIJISHE_PROXY_URLS }}`（sijishe 站点级，优先于全局）
- [x] 1.3 `check-in.yml` 在 “Install dependencies” 之后新增 “Verify env coverage” step，运行 `uv run python -m unittest tests.test_github_workflow -v`，失败即终止 run

## 2. 防遗漏自动化检查

- [x] 2.1 新增仓库根目录 `.env.example`（环境变量清单的单一事实来源）：收录 `config.py` / `notify.py` 读取的全部环境变量与 `SITE_<NAME>_*` 动态前缀说明；CI 必透传的加 `# @ci:secrets` / `# @ci:vars` 标记（`SITE_CONFIGS`、`CHECK_IN_SITES`、通知渠道 Secrets、代理变量），未标记变量不要求进 CI
- [x] 2.2 新增 `tests/test_github_workflow.py`（stdlib unittest）：解析 `.env.example` 标记作为期望集合，正则解析工作流 `env`（兼容 `inputs.x || vars.Y`），双向断言——标记变量必须已映射且来源正确；工作流引用的变量必须已在 `.env.example` 声明且标记一致
- [x] 2.3 正向反例测试：`.env.example` 标记了但工作流未映射 → 测试失败并列出变量名
- [x] 2.4 反向反例测试：工作流引用了 `.env.example` 未声明的变量 → 测试失败并列出变量名

## 3. 文档同步

- [x] 3.1 `README.md` 补充 `.env.example` 指引（单一事实来源、`@ci:secrets` / `@ci:vars` 标记含义）
- [x] 3.2 `README.md` 的 GitHub Actions Secrets 清单补充可选：`CHECK_IN_PROXY_URLS`、`SITE_SIJISHE_PROXY_URLS`（与工作流映射一致）

## 4. 验证

- [x] 4.1 本地运行 `uv run python -m unittest tests.test_github_workflow -v` 通过
- [x] 4.2 本地运行全量 `uv run python -m unittest discover -s tests -v` 无回归
- [ ] 4.3 手动触发 `workflow_dispatch` 验证工作流绿色；未配置代理 Secret 时签到与通知行为不回归

## 5. 教训固化

- [x] 5.1 `.gitignore` 的 `.env.*` 之后增加 `!.env.example` 例外（真实的本地 `.env` 仍被忽略），修复 `.env.example` 被 git 静默忽略、CI checkout 缺文件的问题
- [x] 5.2 教训：新增文件必须确认被 git 跟踪——`git status` 应显示 `A`/`M` 而非被忽略；“本地存在”不等于“已提交”，本地测试无法发现提交遗漏，CI 检查会在 checkout 后兜底
