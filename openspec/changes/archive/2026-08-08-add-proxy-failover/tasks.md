## 1. 失败轮换实现

- [x] 1.1 `http.py` 新增 `FailoverSession(requests.Session)`：覆写 `request()`，捕获 `requests.exceptions.ProxyError` 或响应命中 403/429/5xx 时按序切换到下一个代理重试同一请求，成功即停止并保持该代理；全部尝试完仍失败时抛出最后一个错误或返回最后一个被拒响应
- [x] 1.2 轮换日志复用 `redact_text()` 脱敏（DEBUG 级别，凭据不进日志）
- [x] 1.3 `SessionProvider.new_session()` 返回 `FailoverSession`；无代理配置时行为与普通 `requests.Session` 一致
- [x] 1.4 `FailoverSession` 设置 `trust_env=False`：站点会话忽略 shell 环境代理（`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`），站点流量只走配置的代理列表，未配置时直连

## 2. 测试

- [x] 2.1 `tests/test_http.py` 增加失败轮换用例：mock `requests.Session.request`，代理 A 抛 `ProxyError`、代理 B 成功 → 同一请求经 B 成功且日志脱敏
- [x] 2.2 全部代理失败 → 抛出最后一个错误（账号 `site-unavailable` 语义）
- [x] 2.3 粘性用例：B 成功后后续请求仍用 B；B 后续再失败会继续轮换
- [x] 2.4 403/429/5xx 状态码触发轮换；其他状态码（200/301/401/404）与非代理异常不触发轮换；全部被拒时返回最后一个响应；无代理时行为不变
- [x] 2.5 断言 `FailoverSession` 与 `new_session()` 返回的会话 `trust_env is False`（环境代理不劫持站点请求）
- [x] 2.6 轮换状态码用例：mock 返回 403/429/5xx 断言换下一个代理且日志脱敏；401/404 不轮换；全部被拒返回最后一个响应

## 3. 验证

- [x] 3.1 本地 `uv run python -m unittest discover -s tests -v` 全量通过，`compileall` 通过
- [x] 3.2 手动集成：runner 实测 run 31257331306（56 代理 Secret）验证自动切换：代理1 返回 403 触发轮换、代理2 连接失败触发轮换、代理3 全流程 200，轮换与粘性行为符合预期；全部坏代理时仍为 `site-unavailable` 语义（单测覆盖）
