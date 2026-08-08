## 1. SMTP 收件人

- [x] 1.1 `notify.py` 的 `smtp()` 读取 `SMTP_TO`，未设置时收件人回退 `SMTP_EMAIL`，`From` 保持 `SMTP_EMAIL`，`message["To"]` 沿用现有 `SMTP_NAME` 显示名格式
- [x] 1.2 `tests/test_notify.py` 增加用例：显式收件人、缺省回退、设置收件人时发件人不变
- [x] 1.3 `.github/workflows/check-in.yml` 增加 `SMTP_TO: ${{ secrets.SMTP_TO }}` 透传
- [x] 1.4 `README.md` 通知渠道表格、本地示例补充 `SMTP_TO` 说明（可选、单收件人、缺省为发件人）

## 2. 代理配置解析

- [x] 2.1 `config.py` 的 `NetworkConfig` 增加 `proxy_urls: tuple[str, ...] = ()`（保持向后兼容）
- [x] 2.2 新增 `parse_proxy_urls()`：逗号分隔，校验 `http(s)://host:port` 或 `http(s)://user:pass@host:port`，scheme 非 http/https 或 host 缺失抛 `ConfigError`
- [x] 2.3 站点循环中读取 `SITE_<NAME>_PROXY_URLS`（优先）→ `CHECK_IN_PROXY_URLS` → 空；解析结果传入 `NetworkConfig`
- [x] 2.4 TOML `[network]` / `[sites.<name>.network]` 出现 `proxy_urls` 时抛 `ConfigError` 并指引改用环境变量
- [x] 2.5 `tests/test_common.py` 增加用例：全局列表解析、站点级覆盖全局、非法条目报错、TOML 出现 `proxy_urls` 报错

## 3. 会话应用代理

- [x] 3.1 `http.py` 的 `SessionProvider` 接收 `NetworkConfig` 中的代理列表，round-robin 选取，`new_session()` 设置 `session.proxies = {"http": proxy, "https": proxy}`
- [x] 3.2 `new_session()` DEBUG 日志输出脱敏后的代理地址（复用 `redact_text`）
- [x] 3.3 新增 `tests/test_http.py`：无代理时 session 不带 proxies；两个代理三会话按 A、B、A 轮换

## 4. 代理凭据脱敏

- [x] 4.1 `security.py` 的 `redact_text` 增加正则：`scheme://user:pass@` → `scheme://***@`
- [x] 4.2 `tests/test_common.py`（或现有安全用例处）增加脱敏断言：错误消息与日志中的代理地址不含凭据子串

## 5. 文档与验证

- [x] 5.1 `config/check-in.toml` 的 `[network]` 注释说明代理只走环境变量（`CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS`）
- [x] 5.2 `README.md` 新增「代理试用」小节：环境变量示例、作用范围（仅站点流量）、与 `login-blocked` 排查的关系
- [x] 5.3 运行 `uv run pytest` 全量通过（仓库实际用 `uv run python -m unittest discover -s tests`，91 用例全绿；compileall 通过）
- [x] 5.4 手动集成验证：用户提供代理 IP 后配置 `SITE_SIJISHE_PROXY_URLS` 试运行，对比无代理结果的登录/签到状态；`--notify-only` 验证 SMTP 收件人
