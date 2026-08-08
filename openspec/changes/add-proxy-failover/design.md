## Context

当前 `SessionProvider._next_proxy()` 按会话 round-robin 选取一个代理（`auto_check_in/http.py`），会话绑定该代理后不再切换。适配器（如 `sijishe.py`）通过 `session.get/post(..., timeout=request_timeout_seconds)` 手动重试（`for _ in range(retries)` + `retry_delay_seconds`），但重试的是同一个代理。CI 日志显示代理连接失败时抛 `ProxyError('Unable to connect to proxy', ConnectTimeoutError(...))`，账号随后以 `site-unavailable` 失败。

约束：无 pytest/PyYAML 依赖（stdlib unittest）；代理凭据必须脱敏；不改动通知渠道行为（通知本就不走站点代理）。

## Goals / Non-Goals

**Goals:**
- 代理连接失败时自动轮换到下一个代理重试同一请求，提升"部分代理不可用"时的签到成功率。
- 会话粘性：同一会话尽量保持同一出口 IP，仅在当前代理确实连接失败时才切换。
- 仅代理连接类错误触发轮换；站点层失败不轮换。
- 全部代理失败时保持现有 `site-unavailable` 语义。

**Non-Goals:**
- 不新增环境变量/配置项（不扩大 env 清单与工作流映射面）。
- 不改跨会话 round-robin 分配、不改非代理错误的重试次数/延迟语义。
- 不做代理健康检查/主动探测（仅按需失败轮换）。
- 不改变通知渠道的请求路径。

## Decisions

1. **在 `http.py` 新增 `FailoverSession(requests.Session)`，覆写 `request()` 实现轮换**：捕获 `requests.exceptions.ProxyError` 时把 `self.proxies` 切到下一个代理并重试同一请求，成功后保持该代理。适配器调用点零改动，所有站点透明受益。备选方案：
   - 在适配器各调用点包一层轮换 helper → 改动面大（多处调用）、逻辑重复，弃用。
   - 在适配器重试循环里切代理 → 每适配器各写一份、与现有手动重试耦合，弃用。

2. **触发条件限定为 `requests.exceptions.ProxyError`**：urllib3/requests 在"连不上代理"（含代理连接超时）时抛 `ProxyError`，正是 CI 里观察到的异常类型。HTTP 状态码/站点层异常/其他网络错误不触发轮换，避免在站点本身出问题时无谓切换出口 IP。

3. **轮换顺序与粘性**：会话记录当前代理下标；请求失败时从当前下标向后遍历列表（每个代理每请求至多尝试一次）；成功即更新当前代理并停止；全部耗尽则抛出最后一个异常，由适配器现有重试与 `site-unavailable` 机制兜底。

4. **无新增环境变量**：复用 `proxy_urls` 列表；`.env.example`、工作流 `env`、env 一致性测试均无需改动，避免扩大本次变更的配置面。

5. **日志脱敏**：每次轮换输出 DEBUG 日志，代理地址经 `redact_text()` 脱敏，凭据永不进日志。

6. **站点会话禁用环境代理合并（`trust_env=False`）**：requests 默认 `trust_env=True` 会把 shell 的 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 合并进 session。实测本地设置了 `SITE_SIJISHE_PROXY_URLS=http://83.168.105.19:8005`（该代理不可达）时请求仍成功——实际走的是本地 Clash（`127.0.0.1:7897`），代理列表与失败轮换完全没被用到。关闭 `trust_env` 后站点流量只走运行时自己的代理列表，未配置则直连，与 CI 行为一致。备选方案：要求用户本地清空环境代理变量 → 治标不治本、容易漏，弃用。通知渠道不走站点会话，不受影响。

## Risks / Trade-offs

- [轮换使单请求最坏耗时变长] → 每个代理每请求至多尝试一次，全部失败后仍按现有重试与退出语义；最坏耗时 ≈ retries × 代理数 × 超时，先观察实际表现，后续可加轮换上限配置。
- [切换出口 IP 可能触发站点风控] → 粘性设计保证同一会话尽量同一代理，仅在代理连接失败（而非站点拒绝）时才切换。
- [ProxyError 判定过宽/过窄] → 触发条件限定为代理连接类错误，测试覆盖正反例；若后续出现其他代理故障形态（如代理返回 5xx），再扩展触发集合。
- [轮换日志泄露凭据] → 复用 `redact_text()` 脱敏，测试断言日志不含凭据子串。
- [本地 shell 环境代理（`HTTP_PROXY`/`HTTPS_PROXY`）劫持站点请求] → 站点会话 `trust_env=False`，代理只来自运行时配置；测试断言会话关闭环境代理合并。

## Migration Plan

1. `http.py` 新增 `FailoverSession`（禁用环境代理合并 `trust_env=False`），`SessionProvider.new_session()` 返回它（无代理时行为与普通 Session 一致）。
2. `tests/test_http.py` 增加用例（mock `requests.Session.request`）：失败轮换成功、全部失败抛错、粘性、非代理错误不轮换、无代理行为不变。
3. 本地验证：`uv run python -m unittest discover -s tests -v` 全量通过，`compileall` 通过。
4. 手动集成：`SITE_SIJISHE_PROXY_URLS` 配置“1 个坏代理 + 1 个好代理”，本地或 CI 试运行确认自动切换后签到成功；本地可在列表末尾加 `http://127.0.0.1:7897` 作为好代理验证自动切换；全部坏代理时确认 `site-unavailable`。
5. 回滚：仅涉及 `http.py` 与测试文件，直接 revert 即可，无数据/凭据迁移。

## Open Questions

- 是否需要"每请求最多尝试代理数"或"轮换总耗时上限"配置？当前先按"全部列表轮换一遍"，若实测超时过长再单独提案加配置项。
