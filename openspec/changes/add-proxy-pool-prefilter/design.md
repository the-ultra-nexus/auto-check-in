## Context

当前站点代理来自静态列表（`CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS`，env-only）。`SessionProvider` 按会话 round-robin 选代理，`FailoverSession` 在代理连接失败或被站点拒绝（403/429/5xx）时轮换（已归档 `add-proxy-failover`）。免费代理池时效 1~10 分钟，静态 Secret 在定时任务运行时往往已全部失效；run 31257331306 实测前两个代理（403 / 连接失败）空转后才轮到可用代理。此前规划过“运行前全量预筛 + 按耗时排序”，但存在两个固有缺陷：慢（几百个代理逐个探活要几分钟）与不可靠（探活连通 ≠ 实际请求成功，站点 WAF 按请求行为判定，探活通过的代理登录时仍可能被拒）。本 change 改为**按需分批补给**：代理只在请求真正需要时小批量获取，失败再取下一批，成功即停。

约束：无 pytest/PyYAML 依赖（stdlib unittest）；代理凭据必须脱敏；env 面变化必须同步 `.env.example` / workflow env / `tests/test_github_workflow.py`（历史教训：CI 参数漏配）；不改通知渠道。

## Goals / Non-Goals

**Goals:**
- 按需分批：只有请求需要代理且当前批次耗尽时才拉池，成功即停（点到为止）。
- 有界：每批默认 5 个可用、每请求最多 5 批、粗探短超时（连接 2s / 总 4s），单请求耗时可控。
- 直连优先实验：首个站点请求**先直连**（等价于把本机 IP 作为池的首位候选），直连成功即返回（0 池成本）；失败才拉批重试。`direct_first` 为**站点级配置**（`SITE_CONFIGS` 每站点字段 / 本地 `SITE_<NAME>_DIRECT_FIRST` env，env 优先），实验期默认开启。
- 透明：补给逻辑在 `FailoverSession.request()` 内部，适配器零改动。
- 失败语义清晰：批次上限内全部失败 → 最后一个错误 → `site-unavailable`；池不可用/取不到代理 → 直连兜底 + warn。
- 本地与 CI 行为一致（应用内实现，不依赖 workflow 步骤）。
- `openspec/config.yaml` 与 `config/check-in.toml` 整理为与现状一致。

**Non-Goals:**
- 不做运行前全量预筛 / 按耗时排序。
- 不保证登录成功：`login-failed` / `login-blocked` 属站点层，不在本 change 范围。
- 不做跨天代理复用（免费代理 1~10 分钟失效，旧列表必死）。
- 不为补给/粗探参数（`BATCH_SIZE` / `MAX_BATCHES` / 粗探超时）新增 env：模块常量即可；`direct_first` 属站点行为开关，走站点级配置。
- 不改通知渠道请求路径；不引入付费代理。

## Decisions

1. **按需补给（`FailoverSession.request()` 内部）+ 直连优先实验**：
   - 站点级 `direct_first=True`（默认，实验期）：会话首个站点请求**先直连**（无代理，短超时预算，快失败），直连成功（2xx/3xx）→ 直接返回并粘住直连（0 池成本）；直连失败（403/429/5xx/超时/拒连/TLS）→ **才拉批**，用批内代理重试同一请求。直连粘住期间后续请求再失败 → 同一逻辑：拉批重试（“直连不行再重新拉批”）。
   - 站点级 `direct_first=False`：回到无条件先拉批（站点直连必死的兜底路径），保留为站点配置分支以便实验后切换。
   当前批次耗尽时取下一批（每请求最多 `MAX_BATCHES=5` 批）；任一请求成功即停止获取，会话粘住成功代理（现有粘性语义）。**批次按站点隔离**：每个站点的会话各自拉批、各自持有与轮换（`_proxy_urls` 为会话实例级），站点间不共享、不复用彼此批次；池 URL 全局一个 env，但批次是站点级的。备选方案：
   - 运行前全量预筛 + 排序（原方案）→ 慢（几分钟）且探活≠请求，弃用。
   - 适配器各调用点包一层取批逻辑 → 多处重复、与轮换耦合，弃用。
   - FailoverSession 只在“无代理”时取一批、不继续补给 → 一批全挂就失败，无法利用多池冗余，弃用。
   - “把本机 IP 字符串塞进代理列表、仍先拉批” → 直连成功与否无法省下拉批成本，且直连不是真代理，语义混乱，弃用；直连优先直接由“无代理=直连”表达。

2. **批次提供器 `auto_check_in/pool.py`**：并发拉取所有池 URL（每池字节上限 1MB、拉取超时 10s，失败跳过并 warn，地址经 `redact_text()` 脱敏）→ 多格式解析（`host:port` / `http(s)://host:port` / 空白或制表符分隔表格取前两列，非法行跳过并计数）→ 按 `host:port` 去重后截断上限 → **并行粗探**（`ThreadPoolExecutor` 并发 10，连接 2s / 总 4s，`2xx`/`3xx` 判可用，**凑满 `BATCH_SIZE=5` 个可用即提前终止**，不全量探完）→ 返回一批；不做全量排序（粘性由 FailoverSession 保证，无需按耗时排序）。

3. **补给参数（模块常量）与 `direct_first` 站点级配置**：`BATCH_SIZE=5`、`MAX_BATCHES=5`、粗探 connect 2s / total 4s、粗探并发 10、拉池 1MB/10s、每池上限 200。`direct_first` 不在此列——它是站点行为开关：`SITE_CONFIGS` 每站点 JSON 字段（如 `"direct_first": false`）或本地 `SITE_<NAME>_DIRECT_FIRST` env（env 优先，与 `adapter`/`base_url` 同模式），默认 `true`，禁止写入 TOML。理由：补给/粗探参数与 `CHECK_IN_PROXY_POOL_URLS` 保持“一个 env 管一切”的配置面；`direct_first` 按站点实验（不同站点直连可达性不同），放站点配置才能按站开关。

4. **失败语义**：批次耗尽 → 取下一批；`MAX_BATCHES` 批全败 → 抛最后一个错误 → 账号 `site-unavailable`（现有语义不变）。池拉取失败或取不到任何代理 → 直连兜底 + warn（站点对出口 IP 的封禁可能间歇，直连偶尔能通），不中断 run；直连也失败则按现有 `RequestException` 处理。

5. **触发时机（直连优先，站点级）**：站点 `direct_first=True` 时，首个站点请求先直连（短超时预算，默认复用粗探 connect 2s / total 4s 保证快失败），直连成功即粘住直连；直连失败才拉批。站点 `direct_first=False` 时，无条件先拉批再发请求。**无需判断 cookies**。不做“跨天复用代理列表”的优化（免费池旧列表必死，等于没省）。
   - **拉批只由传输层失败触发**：403/429/5xx/超时/拒连/TLS 失败 → 当前 IP 或代理不可用 → 拉批换 IP 重试同一请求。
   - **会话层失败不触发拉批**：签到页 `200` 但未登录（无 formhash / 提示请先登录）或签到提交返回 `login-failed` → 代理是通的，是 cookie 过期 → 清 cookie 重新登录并复用当前批次。拉池解决不了 cookie 过期，避免白拉。
   - **实验观测**：日志记录直连成功/失败（含失败原因）与拉批次数；实验期（建议 ≥7 个有效日）若某站点直连成功率持续为 0，将该站点 `direct_first` 改为 `false`（保留无条件先拉批路径）。

6. **配置面最小化并移除静态代理列表**：仅保留 `CHECK_IN_PROXY_POOL_URLS`（逗号分隔多个池 URL，env-only，禁止写入 TOML）。同步移除 `CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS` 的解析与接线（config.py、`.env.example`、workflow env、相关测试），避免两套代理来源并存造成的语义混乱。

7. **config 文件重组**：
   - `openspec/config.yaml`：context 重写为当前现状——纯 HTTP 多站点自动签到（Python 3.12 + requests），去掉 Selenium/ddddocr/OpenCV/onnxruntime 等过期依赖描述；补充代理池按需补给（批次按站点隔离）、失败轮换、会话缓存、多通知渠道；rules 补充“代理池 URL 仅 env/Secret、日志脱敏、拉取与探活必须有超时上限”“流程边界：补给=运行时、轮换=兜底”。
   - `config/check-in.toml`：分区规范为 `[runtime] → [network] → [notification] → [sites.<name>]`；文件头明确“敏感信息与代理池 URL 禁止写入”；`[network]` 内注释列出补给/粗探模块常量当前值，不新增 TOML key。

8. **流程边界**（写入 design 与 config.yaml context）：

    | 边界 | 归属 |
    | --- | --- |
    | 探测执行 | 应用内 `pool.py` 批次粗探，各站点会话独立拉批（运行时按需） |
    | 判定口径 | 唯一口径：2xx/3xx 可用；403/429/5xx/超时/拒连/TLS 失败 |
    | 代理获取 | 请求需要且当前批次耗尽时按需取批；成功即停、粘性 |
    | 运行中失效 | `FailoverSession` 轮换（ProxyError / 403/429/5xx），批次耗尽取下一批 |
    | 配置来源 | 池 URL/凭据→env/Secret；非敏感（超时/重试/路径/启用列表）→TOML；补给/粗探参数→模块常量 |
    | 站点边界 | 外部站点不可控；`login-failed`/`login-blocked` 属站点层，由通知与日志暴露，不归代理层 |
    | CI 边界 | 应用内补给保证本地/CI 一致；env 一致性由 `test_github_workflow` 强制 |

9. **env 一致性同步**：`.env.example` 增加 `CHECK_IN_PROXY_POOL_URLS=  # @ci:secrets`；`check-in.yml` env 增加 `CHECK_IN_PROXY_POOL_URLS: ${{ secrets.CHECK_IN_PROXY_POOL_URLS }}`；`tests/test_github_workflow.py` 的双向校验自动覆盖，但必须同步上述两处否则 CI 测试红。

## Flows

### 场景 A：首次运行（无会话，需登录）

直连优先（`DIRECT_FIRST=True`）：先直连，失败才拉批，再走登录。

```text
直连 GET 签到页（短超时预算，快失败）
    │
    ├── 成功（2xx/3xx）──► 登录 → 存 cookie → 签到（0 池成本）
    │
    └── 失败（403/429/5xx/超时/拒连）
              │
              ▼
         拉批：并行粗探（并发 10，connect 2s / total 4s），凑满 5 个可用即停
              │
              ▼
         GET 签到页（走代理）→ 登录 → 存 cookie → 签到
```

### 场景 B：会话失效（有本地 cookies 但已过期）

同样直连优先：先直连，失败才拉批；`login-failed` 不拉池。

```text
直连 GET 签到页（短超时预算，快失败）
    │
    ├── 成功（2xx/3xx）──► 签到 → 完成（0 池成本）
    │
    └── 失败（403/429/5xx/超时/拒连）
              │
              ▼
         拉批：并行粗探（并发 10，connect 2s / total 4s），凑满 5 个可用即停
              │
              ▼
         GET 签到页（走代理）
              │
              ├── 200 且已登录 ──────► 签到 → 完成
              │
              └── login-failed（页面 200 但 cookie 失效，会话层）
                        │
                        ▼
                  清除 cookie → 重新登录（复用当前批次，不拉新批）→ 签到

注：直连失败后，后续站点请求（登录、签到页 GET、签到接口）均走批次代理；拉批只由“传输层失败”（403/429/5xx/超时/拒连）触发；`login-failed` 是会话层失败，代理是通的，不拉池。
```

## Risks / Trade-offs

- [请求路径内补给使首个请求变慢（最多 5 批 × 5 代理尝试）] → 批次上限 + 短超时粗探（总 4s）+ 粗探并发 10；批次获取与失败日志聚合，避免刷屏。
- [粗探误杀慢代理（2s/4s 太短）] → 超时是可调模块常量；实测后按命中率调整。
- [免费池命中率低导致补给频繁] → `BATCH_SIZE` / `MAX_BATCHES` 可调；多池冗余。
- [探活通过但请求仍失败] → 由“取下一批”兜底，不再假装预筛是保证。
- [池源故障/取不到代理] → 直连兜底 + warn；直连也失败则保持现有 `site-unavailable` 语义。
- [直连必死环境下每天白付一次直连失败] → 直连失败多为快失败（拒连/403 毫秒级），且受短超时预算限制；站点级 `direct_first` 可关（`false` 回到无条件先拉批）。
- [env 漏配（历史教训）] → tasks 清单显式包含 `.env.example` / workflow / 一致性测试三处同步。

## Migration Plan

1. `config.py`：移除静态代理列表解析与 env 接线（`CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS`）；新增 `CHECK_IN_PROXY_POOL_URLS` 解析与校验（禁止 TOML），`NetworkConfig` 增加 `proxy_pool_urls` 字段；`SiteConfig` 增加 `direct_first`（`SITE_<NAME>_DIRECT_FIRST` env 优先 > `SITE_CONFIGS` 每站点 `direct_first` > 默认 true，禁止 TOML）。
2. `pool.py`：批次提供器——并发拉池、多格式解析、去重、短超时粗探、返回一批；日志脱敏；各站点会话独立调用、批次互不共享。
3. `http.py`：`FailoverSession` 增加按需补给（站点级 `direct_first`：首请求先直连、失败才拉批；当前批次耗尽取下一批、成功粘性、批次上限、日志聚合；直连成功/失败计数）。
4. `runner.py`：删除运行前预筛逻辑。
5. `openspec/config.yaml`：context/rules 更新；`config/check-in.toml`：分区规范化。
6. `scripts/test_proxy_connectivity.sh`：删除（全量探活脚本废弃，不再交付独立 CLI）；README 同步移除脚本章节。
7. `SITE_CONFIGS.example.json`：新增 JSON Secret 示例文件，README 与 `.env.example` 引用；确认 git 跟踪（A/M）。
8. 测试：池解析/粗探判定/补给逻辑（mock）/兜底/环境一致性/批次站点隔离/`direct_first` 站点级解析/全量 unittest + compileall。
9. 验证：本地配置 `CHECK_IN_PROXY_POOL_URLS` 跑 `--debug` 看直连优先日志（直连成功/失败 → 拉批）与各站点独立补给日志；CI 设置 Secret 后 `workflow_dispatch` 复测；实验期统计直连成功率。
10. 回滚：仅新增模块与 env 与文档，revert 即可，无数据/凭据迁移。

## Open Questions

- 粗探超时（connect 2s / total 4s）是否需要配置化？`BATCH_SIZE=5` / `MAX_BATCHES=5` 已定，粗探超时仍为模块常量，实测后按命中率与耗时决定。
- 直连优先实验：`direct_first` 默认 true 的实验期多长？直连预算（connect 2s / total 4s）是否够用？某站点直连成功率持续为 0 时是否改为 `false`？
