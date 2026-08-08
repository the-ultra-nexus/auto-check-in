## 1. 失败轮换实现

- [x] 1.1 `http.py` 新增 `FailoverSession(requests.Session)`：覆写 `request()`，捕获 `requests.exceptions.ProxyError` 时按序切换到下一个代理重试同一请求，成功即停止并保持该代理；全部尝试完仍失败时抛出最后一个错误
- [x] 1.2 轮换日志复用 `redact_text()` 脱敏（DEBUG 级别，凭据不进日志）
- [x] 1.3 `SessionProvider.new_session()` 返回 `FailoverSession`；无代理配置时行为与普通 `requests.Session` 一致

## 2. 测试

- [x] 2.1 `tests/test_http.py` 增加失败轮换用例：mock `requests.Session.request`，代理 A 抛 `ProxyError`、代理 B 成功 → 同一请求经 B 成功且日志脱敏
- [x] 2.2 全部代理失败 → 抛出最后一个错误（账号 `site-unavailable` 语义）
- [x] 2.3 粘性用例：B 成功后后续请求仍用 B；B 后续再失败会继续轮换
- [x] 2.4 非代理错误（如 HTTP 状态响应、非代理异常）不触发轮换；无代理时行为不变

## 3. 验证

- [x] 3.1 本地 `uv run python -m unittest discover -s tests -v` 全量通过，`compileall` 通过
- [ ] 3.2 手动集成：`SITE_SIJISHE_PROXY_URLS` 配置"1 个坏代理 + 1 个好代理"试运行，确认自动切换后签到成功；全部坏代理时确认 `site-unavailable`
