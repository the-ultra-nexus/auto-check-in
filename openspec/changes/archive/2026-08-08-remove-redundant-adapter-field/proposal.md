## Why

`SITE_CONFIGS` Secret 中 `sijishe` 站点配置的 `"adapter": "sijishe"` 是多余的：配置加载器在站点未指定 `adapter` 时已默认使用站点同名适配器。删掉该字段可以避免每个站点都要重复写一遍站点名，降低 Secret 维护成本，也让 README 示例与实际 Secret 保持一致。

另外，本地缺少单独测试通知渠道的手段：`--dry-run` 在发送通知前就退出，普通运行会真实访问站点，无法在不碰站点的情况下验证通知是否送达。新增 `--notify-only` 参数，让本地可以单独跑一次通知测试。

## What Changes

- 从 GitHub 仓库 Secret `SITE_CONFIGS` 的 `sijishe` 配置中删除 `"adapter": "sijishe"`（手工用 `gh secret set SITE_CONFIGS` 更新，不入库）。
- 更新 `README.md` 中 `SITE_CONFIGS` 示例，去掉冗余的 `"adapter": "sijishe"` 字段。
- 为 `SITE_CONFIGS` 省略 `adapter` 时回退到站点同名适配器的行为补充规格描述与自动化测试，防止未来改动破坏该默认值。
- **新增** CLI 参数 `--notify-only`：本地单独发送测试通知，不解析站点凭据、不访问站点、不执行签到；与 `--dry-run`、`--no-notify` 互斥。
- 不改动 `config/check-in.toml` 的本地默认适配器行为，不改变任何凭据/通知渠道配置。

## Capabilities

### New Capabilities

- `notify-standalone`: 通过 `--notify-only` 在本地单独发送测试通知、验证各通知渠道，不依赖站点凭据、不访问站点。

### Modified Capabilities

- `adapter-extension`: 明确 `SITE_CONFIGS` 中站点可省略 `adapter`，缺省时回退到与站点同名的适配器；补充相应场景。

## Impact

- `README.md`：`SITE_CONFIGS` 示例移除 `"adapter"` 字段；补充 `--notify-only` 用法。
- `openspec/specs/adapter-extension/spec.md`：新增/明确默认适配器回退的要求场景（通过 delta spec 记录）。
- `auto_check_in/cli.py`：`build_parser()` 新增 `--notify-only` 参数；`main()` 新增对应分支（只发通知，不执行签到）。
- `tests/`：为 `SITE_CONFIGS` 省略 `adapter` 的站点补充断言；为 `--notify-only` 新增测试（不访问站点、发送测试通知、退出码）。
- GitHub Actions 仓库设置：手工更新 `SITE_CONFIGS` Secret（唯一外部动作，删除后行为不变，风险低）。
