## Context

`load_config()` 在解析每个站点时按以下优先级取 `adapter`：`SITE_<NAME>_ADAPTER` 环境变量 → `SITE_CONFIGS` JSON 中的 `adapter` → TOML `[sites.<name>] adapter` → 站点名。也就是说站点未配置 `adapter` 时已默认使用与站点同名的适配器。因此 GitHub `SITE_CONFIGS` Secret 中 `sijishe` 条目的 `"adapter": "sijishe"` 是冗余的；README 的示例同样写入了该字段。当前 `tests/test_common.py::test_site_configs_json` 中 `sijishe` 条目已省略 `adapter`，但未对回退结果做断言。

CLI 目前只有 `--dry-run`（校验配置与账号后直接退出、不发通知）与 `--no-notify`（运行但跳过通知）；通知只在真实签到完成后发送，本地无法在不访问站点的情况下验证通知渠道。

约束：Secret 内容无法从仓库读取或校验，更新 Secret 是仓库外的管理动作；本变更涉及通知发送逻辑（`--notify-only`），但不涉及 Selenium、OCR、站点网络与调度。

## Goals / Non-Goals

**Goals:**

- 从 `SITE_CONFIGS` Secret 与 README 示例中移除冗余的 `"adapter": "sijishe"`，使配置更精简、示例与真实 Secret 一致。
- 用规格与回归测试锁定「省略 `adapter` 时回退到站点同名适配器」的行为，避免未来改动破坏该默认值。
- 新增 `--notify-only`：本地无需站点凭据即可向所有已启用渠道发送测试通知，验证通知链路。
- 保持删除 `adapter` 前后解析出的 `SiteConfig.adapter` 均为 `"sijishe"`，行为完全不变。

**Non-Goals:**

- 不改变 `adapter` 的解析优先级、TOML 默认配置或显式指定 `adapter` 的能力。
- 不新增或修改通知渠道实现，不改变正常签到运行的通知行为。
- 不将 `--notify-only` 接入 GitHub Actions 定时流程（仅本地/手动使用）。
- 不迁移其他站点、不修改凭据格式，不重构 `load_config()`。

## Decisions

1. **代码零改动，只加固测试**：默认回退逻辑已存在（`section.get("adapter", name)`），本次只需在 `test_site_configs_json` 中补充断言 `config.sites[0].adapter == "sijishe"`，或新增一个明确的用例。理由：避免为了删除一个冗余字段而改动已稳定的解析逻辑。
2. **用 ADDED 规格而非 MODIFIED**：在 `adapter-extension` 的 delta spec 中新增 `Default adapter fallback` 要求，而不是改写现有 `Generic multi-site workflow configuration` 条目，减少归档时丢失既有细节的风险。
3. **Secret 通过 `gh` CLI 手工更新**：`gh secret set SITE_CONFIGS` 写入去掉 `adapter` 字段的新 JSON；变更前用本地 `--dry-run` 验证解析结果不变。理由：Secret 无法读回，只能整体覆写，先本地验证再更新最安全。
4. **README 示例同步删除字段**：示例即 Secret 的文档契约，删除后不再误导新站点配置者重复填写站点名。
5. **`--notify-only` 参数**：`build_parser()` 新增 `--notify-only`，并与 `--dry-run`、`--no-notify` 放入互斥组（`argparse` 报错拒绝自相矛盾的组合）。命名理由：语义直白「只跑通知」；备选 `--send-notify`、`--notify-test` 被否决（易与「发送签到结果」混淆）。
6. **不要求站点凭据**：`--notify-only` 只读取 `[notification]` 的标题与开关（TOML 默认 + 环境变量），不加载/校验 `SITE_CONFIGS` 与 `SITE_*_ACCOUNTS`，不初始化适配器或网络会话。理由：通知测试不应依赖签到配置；普通 `load_config()` 在缺站点凭据时会报错，需走轻量配置路径。
7. **测试通知内容**：发送固定标题（如 `Auto Check In 通知测试`）与包含当前时间、已启用渠道列表的正文；复用 `send()` 的并发发送与渠道异常隔离。无任何渠道启用时在控制台明确提示。
8. **退出码**：`--notify-only` 至少一个渠道启用且发送无致命错误时返回 0；无渠道启用或通知配置错误时返回 2（复用配置错误码），便于脚本/CI 判断。

## Risks / Trade-offs

- [站点名与适配器名不一致的站点依赖显式 `adapter`] → 本次只删除 `sijishe`（名称一致）的冗余字段，默认回退逻辑保留，显式 `adapter` 仍优先。
- [手工更新 Secret 时误删 `base_url`/`accounts`] → 先在本地以新 JSON 运行 `uv run auto-check-in --dry-run` 验证，再 `gh secret set`，最后手动触发一次 workflow 确认。
- [本地无任何通知渠道环境变量] → `--notify-only` 提示未启用渠道并以退出码 2 结束，明确告知而非静默成功。
- [测试通知误发到生产渠道] → 标题与正文明确标注「测试」，仅由用户本地手动触发，不进入 workflow。

## Migration Plan

1. 提交本变更（README、delta specs、回归测试、`--notify-only` 实现）。
2. 本地用去掉 `adapter` 的新 JSON 跑 `uv run auto-check-in --dry-run`，确认解析为 `adapter=sijishe`。
3. 本地运行 `uv run auto-check-in --notify-only` 验证各通知渠道送达。
4. 用 `gh secret set SITE_CONFIGS` 覆写 Secret，手动触发 workflow 验证签到与通知正常。
5. 回滚：代码侧撤销 `--notify-only` 及其测试即可；Secret 恢复原 JSON。

## Open Questions

- `--notify-only` 的具体参数名以本设计为准（`--notify-only`）；如需别名可在实现时补充。
