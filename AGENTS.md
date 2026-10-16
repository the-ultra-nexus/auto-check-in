# AGENTS.md

面向在此仓库工作的 AI 代理。人类读者请看 [README.md](README.md)。

## 这个项目在做什么

多站点自动签到。每个站点一个适配器，环境隔离，多站点并行。

**关键约束：穿过 Cloudflare 的站点必须走真实浏览器。** 这不是偏好，是实测结论：
纯 HTTP 客户端没有 JS 引擎，无论出口 IP 好坏都会撞上质询页。用 `requests` 测「这个
IP 行不行」是**无效实验**——403 的响应体就是 CF 的质询脚本（`window.__CF$cv$params`）。

## 架构

```
cli.main → runner.run → _run_site → adapter.run(account)
```

| 文件 | 职责 |
| --- | --- |
| `auto_check_in/cli.py` | CLI 入口，参数解析、退出码 |
| `auto_check_in/runner.py` | 多站点并行调度，逐账号调 adapter |
| `auto_check_in/config.py` | TOML + 环境变量加载，站点隔离，凭据禁写配置文件 |
| `auto_check_in/browser.py` | Chrome 工厂，可选 `--proxy-server` |
| `auto_check_in/proxy_setup.py` | 起本地 mihomo，按顺序回退拉订阅、并行测速选节点 |
| `auto_check_in/adapters/sijishe_browser.py` | 司机社浏览器适配器 |
| `auto_check_in/discuz.py` | Discuz 通用解析（formhash、响应分类；弹框工具供 HTTP 适配器用） |
| `auto_check_in/session.py` | cookie 缓存读写 |
| `auto_check_in/security.py` | 脱敏（含 `cf_clearance`） |

适配器契约见 `auto_check_in/adapters/base.py`：`run(account) -> AccountResult`。

## 改代码前必须知道的事

1. **判 Cloudflare 质询只看 `driver.title`。** CF 在**成功页面**里也注入
   `challenge-platform` / `__CF$cv$params`，用这两个字符串判会在正常页面上误报。
2. **`cf_clearance` 不能跨客户端复用。** 它绑定 TLS 指纹与会话，交给 `requests` /
   `curl_cffi` 全部 403。登录与签到必须在同一个浏览器会话内完成。
3. **节点定义必须原样保留。** 订阅里 vless 的 `tls`/`flow`/`reality-opts` 手写解析
   极易遗漏，生成残缺配置后所有节点都连不上。只替换 `rules`。
4. **订阅自带规则会触发 MMDB 下载。** 数千条含 `GEOIP` 的规则在受限网络下超时即
   fatal 退出（API 端口起不来）。必须换成一条 `MATCH,GLOBAL`。
5. **代理地址只走环境变量。** 写入 TOML 会 `ConfigError`（与凭据同等对待）。
6. **订阅源要按顺序回退。** 免费节点寿命以小时计，单个源失效不能让签到整体停摆。
   改源时必须每个源独立工作目录，否则上一个源的节点定义会污染下一个。
7. **选节点只能用 `/group/GLOBAL/delay`，不能读组的 `now`。** 测速前 `now` 就是列表
   首节点（默认值），组的 `history` 也始终为空；照着读会选中连不通的节点（曾显示
   延迟 0ms）。健康检查目标必须是**签到页**而非 `plugin.php`——存在「plugin.php 能开、
   签到页在浏览器里挂死」的节点。
8. **被 CF 拦下就换节点，不要原地等。** 免费源可用节点很多，质询等待与页面加载上限
   都压得较短（15s / 30s），超时即换下一个出口。
9. **凭据不进日志。** 一律经 `security.py` 的 `mask_username` / `redact_text`。
10. **缓存的 `*_auth` 不等于活会话。** 恢复 cookie 后 `_is_logged_in` 会为真并跳过登录，
   但服务端会话可能早已失效，此时 `plugin.php` 返回「您所在用户组不允许使用」。这类
   响应必须归类为 `LOGIN_FAILED`（`DISCUZ_NOT_LOGGED_IN_MARKERS`）才能触发重登；且
   重登前必须 `delete_all_cookies()`，否则同一个陈旧 cookie 会把重登再次骗过。

## 测试

标准库 `unittest`，无 pytest：

```bash
uv run python -m unittest discover -s tests -v
uv run python -m compileall auto_check_in tests
```

- `tests/helpers.py` 提供 `FakeDriver`（脚本化浏览器）与 `make_site_config`，
  适配器通过 `driver_factory` 注入，**测试不打真实网络**。
- `tests/test_github_workflow.py` 双向校验 `.env.example` 的 `@ci:secrets`/`@ci:vars`
  标记与 workflow `env` 映射。**新增环境变量必须同步登记，否则 CI 直接失败。**
- `tests/test_common.py` 的 `DependencyTests` 断言依赖里不含 `ddddocr` / `opencv` /
  `onnxruntime`（验证码 OCR 路线排除）。`selenium` 是必需的，不在排除之列。
- 构造适配器时传 `challenge_timeout_seconds=1`，否则等质询超时会拖慢整个测试套件。

## CI

`.github/workflows/check-in.yml` 单个 job：起本地 mihomo 选节点 → 浏览器经该端口签到。
`proxy_setup` 按平台下载 mihomo 的 `compatible` 构建（`linux`/`darwin` × `amd64`/`arm64`），
所以本地也能跑同一套。

## 已废弃（不要再引入）

- `pool.py` / `proxy_source.py`：免费代理池。实测 0/1000 能过质询，且用 `requests`
  测出来的结论本身就无效。
- `adapters/sijishe.py`：纯 HTTP 适配器。过不了 CF。
- `CHECK_IN_PROXY_POOL_URLS` / `CHECK_IN_PROXY_LIST_FILE` / `direct_first`：
  随代理池一并移除。`direct_first` 曾是「直连优先」开关，删除前已确认是死配置
  （只在 `config.py` 解析校验、零消费方）。

## 历史探测结论（避免重走弯路）

| 尝试 | 结果 |
| --- | --- |
| 免费代理池 | 0/1000 过质询（`requests` 测的，结论无效） |
| CI 上 headless Chrome 过页面级 | 可过，拿到 `cf_clearance` |
| `cf_clearance` 交给 HTTP 客户端 | 全部 403（绑定 TLS 指纹） |
| CI 上真实点击（trusted event） | 无用：登录动作本身让 CF 降级该会话 |
| Xvfb 有头模式 | 与 headless 结果一致 |
| **经订阅节点 + 真实浏览器** | **通过，CI 签到成功** |
| 串行逐节点探 TCP 可达 | 选出的节点浏览器仍 renderer 挂死：可达 ≠ 可用 |
| 读 url-test 组的 `now` 当测速结果 | 不可信，测速前就是列表首节点（延迟显示 0ms） |
| 探针盯 `plugin.php` | 存在「plugin.php 能开、签到页挂死」的节点，应以签到页为准 |
| 经订阅节点 + 真实浏览器（最终） | 通过；并行测速选节点，CI 21.3s 完成 |
