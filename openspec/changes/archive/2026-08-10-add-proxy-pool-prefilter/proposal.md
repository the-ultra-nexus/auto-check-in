## Why

免费代理池时效极短（1~10 分钟轮换），静态代理列表在定时任务运行时往往已全部失效；run 31257331306 实测前两个代理（403 / 连接失败）空转后才轮到可用代理。且“运行前全量预筛”有两个固有缺陷：慢（几百个代理逐个探活要几分钟）与不可靠（探活连通 ≠ 实际请求成功，站点 WAF 按请求行为判定）。方案改为**按需分批补给**：站点请求真正需要代理时才拉取一小批（短超时粗探），批次在请求层失败时再取下一批，成功即停（点到为止），尽量少花时间。

## What Changes

- 新增 `CHECK_IN_PROXY_POOL_URLS`（逗号分隔多个 IP 池 URL），**仅允许 env/Secret 提供，禁止写入 TOML**；移除 `CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS` 静态代理列表（代码、`.env.example`、workflow env 一并移除）。
- **直连优先实验**（站点级 `direct_first`，默认开启）：首个站点请求**先直连**（短超时预算、快失败），成功即返回并粘住直连（0 池成本，等价于把本机 IP 作为池的首位候选）；失败（403/429/5xx/超时/拒连/TLS）**才拉批**，用批内代理重试同一请求。`direct_first` 在 `SITE_CONFIGS` 每站点配置（本地 `SITE_<NAME>_DIRECT_FIRST` env 优先，禁止 TOML），实验期日志统计直连成功/失败，某站点成功率持续为 0 时改该站点为 `false`（无条件先拉批路径保留）。
- **按需分批补给**：拉批后站点请求需要代理且当前批次耗尽时，会话从池取下一批（默认每批 5 个可用、每请求最多 5 批）继续重试同一请求；任一请求成功即停，会话粘住成功代理；批次上限内仍失败 → 现有 `site-unavailable` 语义。**批次按站点隔离**：每个站点的会话各自拉批、各自持有与轮换，站点间不共享批次。
- **批次粗探**：拉池后以短超时（连接 2s / 总 4s）粗筛，只保留 2xx/3xx 的代理；探活通过≠请求成功，由“取下一批”兜底，不再假装预筛是保证。
- 池拉取失败或取不到任何代理 → 直连兜底 + warn（站点对出口 IP 的封禁可能是间歇的，直连偶尔能通），不中断 run。
- 移除“运行前全量预筛 + 按耗时排序”设计；`runner` 不再有预筛阶段。
- 重新整理 `openspec/config.yaml`（过期的 Selenium/OCR 上下文重写为纯 HTTP 多站点现状）与 `config/check-in.toml`（分区规范化），并明确流程边界。
- 删除 `scripts/test_proxy_connectivity.sh`（全量探活脚本废弃，不再交付独立 CLI）。
- env 一致性同步：`.env.example`、`check-in.yml` env、`tests/test_github_workflow.py` 全量更新，避免“CI 漏参数”重演。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `proxy-ip-access`: 新增“代理池按需补给”需求（替换原“代理池预筛”需求）：直连优先（首请求先直连、失败才拉批，`DIRECT_FIRST` 开关）、批次按站点隔离、批次耗尽取下一批、成功即停粘性、上限内失败 → `site-unavailable`、池不可用直连兜底；拉批仅由传输层失败（403/429/5xx/超时/拒连）触发，会话层失败（页面 200 但 `login-failed`）不拉批而是清 cookie 重登；移除“静态代理列表配置”需求；会话代理来源改为按需获取结果。
- `github-actions-env`: 更新“代理 Secret 映射”场景，从 `CHECK_IN_PROXY_URLS` / `SITE_SIJISHE_PROXY_URLS` 改为 `CHECK_IN_PROXY_POOL_URLS`。

## Impact

- `auto_check_in/config.py`：移除静态代理列表解析与 env 接线；新增 `proxy_pool_urls` 解析与校验（env-only，禁止 TOML）；`SiteConfig` 新增 `direct_first`（`SITE_<NAME>_DIRECT_FIRST` env > `SITE_CONFIGS` 每站点字段 > 默认 true）。
- 新模块 `auto_check_in/pool.py`：批次提供器（拉取、多格式解析、去重、短超时粗探、返回一批）。
- `auto_check_in/http.py`：`FailoverSession` 增加按需补给能力（`DIRECT_FIRST` 直连优先：首请求先直连、失败才拉批；当前列表耗尽时取下一批重试同一请求、成功粘性、批次上限、批次按站点隔离、日志脱敏、直连成功/失败计数）。
- `auto_check_in/runner.py`：无运行前预筛阶段。
- `scripts/test_proxy_connectivity.sh`：删除（探活脚本废弃）。
- `tests/`：静态代理用例改为池解析/粗探/补给用例（直连优先：直连成功不拉批 / 直连失败才拉批、批次耗尽取下一批、成功粘性、上限全败 → `site-unavailable`、兜底直连、批次站点隔离、`direct_first` 站点级解析（env > SITE_CONFIGS > 默认）、env 一致性）。
- `.github/workflows/check-in.yml` + `.env.example` + `config/check-in.toml`：代理 env 面同步为仅 `CHECK_IN_PROXY_POOL_URLS`。
- 新增 `SITE_CONFIGS.example.json`：`SITE_CONFIGS` JSON Secret 的完整示例（`base_url`/`accounts`/`sign_path`/`direct_first`），README 与 `.env.example` 引用。
- `openspec/config.yaml`：上下文与规则更新为当前纯 HTTP 架构与流程边界。
