## Why

CI 运行 31254588184 显示：配置了多个代理时，会话只尝试当前 round-robin 选中的 1 个代理；该代理连接失败（`ProxyError` 连接超时）后不会切换到列表中的下一个，账号直接以 `site-unavailable` 失败退出。多代理的初衷是"一个挂了还有下一个"，当前实现只有"跨会话轮换"，缺少"失败轮换"。

## What Changes

- `auto_check_in/http.py` 的会话增加代理失败轮换：请求因当前代理连接失败（`requests.exceptions.ProxyError`，含代理连接超时）时，自动改用列表中的下一个代理重试同一请求，直到成功或全部代理耗尽。
- 会话粘性：某个代理成功后，该会话后续请求继续使用该代理（保持登录/签到出口 IP 一致）；后续该代理再失败仍会继续轮换。
- 非代理类失败（站点 HTTP 状态、站点层错误等）不触发轮换，保持现有行为。
- 全部代理都失败时抛出最后一个错误，账号按现有机制以 `site-unavailable` 体现。
- 无新增环境变量或配置项：复用现有 `SITE_<NAME>_PROXY_URLS` / `CHECK_IN_PROXY_URLS` 列表，`.env.example` 与工作流 `env` 无需改动。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `proxy-ip-access`: 新增"代理连接失败时轮换到下一个代理重试"的需求（失败轮换 + 会话粘性 + 仅代理类错误触发）。

## Impact

- `auto_check_in/http.py`：`SessionProvider.new_session()` 返回带失败轮换的会话，所有适配器请求透明受益，无需改动适配器调用点。
- `tests/test_http.py`：新增失败轮换、粘性、全部失败、非代理错误不轮换、无代理行为不变等用例。
- 无新依赖、无新环境变量、无工作流/文档 env 变更（env 一致性检查不受影响）。
- 行为影响：代理列表中部分代理不可用时签到成功率提高；全部不可用时行为与现状一致（`site-unavailable`）。
