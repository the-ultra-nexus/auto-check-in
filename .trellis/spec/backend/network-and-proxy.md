# 网络与代理规范

> 网络容错核心：直连优先（direct-first）探测、按需分批代理补给、失败轮换、粘性直连。
> 涉及 `auto_check_in/http.py`（FailoverSession / SessionProvider）与 `auto_check_in/pool.py`。

## 设计目标（README 承诺的行为）

1. **0 池成本**：首个请求先直连，成功即用（粘性），不预先拉代理。
2. **按需分批**：直连失败才从多个 IP 池拉取一小批（并行粗探、凑满即停）。
3. **失败轮换**：代理连接失败或被站点拒绝（403/429/5xx）时自动切换下一个代理。
4. **批次耗尽再取下一批**，最多 `MAX_BATCHES` 批；池空/失败回退直连。

## FailoverSession（http.py）

- 继承 `requests.Session`，但 **`trust_env = False`**：忽略环境代理变量，站点流量只走
  直连或批内代理（防 CI/本机全局代理污染）。
- `ROTATE_STATUS_CODES = {403, 429, *range(500, 600)}`：命中即视为当前出口不可用并轮换
  （403 站点/WAF 拒绝、429 限流、5xx 代理上游或目标故障）。
- 直连优先（`direct_first=True` 默认）：
  - 直连成功 → 粘住直连，不再拉批；
  - 直连失败（传输异常或 ROTATE 状态码）→ `_acquire_batch()` 拉批重试；
  - 池不可用 → 若已有直连响应则回退该响应，否则抛原异常（`http.py::request`）。
- 批内轮换：`_proxy_index` 递增，回到批首时若批次数 < `MAX_BATCHES` 再取下一批；
  全部耗尽后返回最后一个可用响应或抛最后异常。
- 构造依赖注入：`pool_fetcher: Callable[[], tuple[str, ...]]` 可注入（测试替身用），
  参考 `tests/test_http.py::_pool_fetcher`。

## SessionProvider（http.py）

- 组装 `FailoverSession`：`network.proxy_pool_urls` 非空且给了 `probe_url` 时才挂
  `pool_fetcher`；`probe_url` 由适配器传 `base_url + sign_path`
  （`adapters/sijishe.py::__init__`）。
- 新会话统一 `session.headers.update({"User-Agent": random_user_agent()})`；
  请求头用 `ua_headers(extra)` 生成（`http.py::ua_headers`），UA 从 `USER_AGENTS`
  池随机，禁止硬编码单一 UA。

## 代理池（pool.py）

关键常量（改动需同步测试与 README）：

| 常量 | 值 | 语义 |
|------|-----|------|
| `BATCH_SIZE` | 5 | 每批凑满的可用代理数 |
| `MAX_BATCHES` | 5 | 单会话最多取批次数 |
| `PROBE_CONNECT_TIMEOUT` / `PROBE_TOTAL_TIMEOUT` | 2.0 / 4.0 s | 探测超时（connect, total） |
| `PROBE_CONCURRENCY` | 10 | 并行探测数 |
| `POOL_FETCH_TIMEOUT` | 10.0 s | 拉取池列表超时 |
| `POOL_MAX_BYTES` | 1 MiB | 池内容大小上限，超限抛错 |
| `POOL_MAX_ENTRIES` | 200 | 单池最多收录条目 |

- `parse_pool_entry`：支持 `host:port`、`http(s)://host:port`、空格/Tab 分隔表格行
  （前两列为 ip 和 port）；格式不符返回 `None`（静默跳过，不抛）。
- `fetch_pool_batch(pool_urls, probe_url)`：
  1. 多池 **并行**拉取（每个池一个线程），单池失败 `logger.warning` 降级继续；
  2. 按 `host:port` 去重（`_entry_key`，https 默认 443 / http 默认 80）；
  3. 并行粗探候选（`_probe_one`：2xx/3xx 视为可用），**凑满 `BATCH_SIZE` 即停**；
  4. 结束时 `executor.shutdown(wait=False, cancel_futures=True)`，不阻塞等待未完成探测。
- 空池/全失败返回空 tuple，调用方（FailoverSession）回退直连。

## 配置约束（config.py 强制）

- 代理池地址**只走环境变量** `CHECK_IN_PROXY_POOL_URLS`（逗号分隔多池）或
  GitHub Secret；TOML 里出现 `[network] proxy_urls / proxy_pool_urls` 或
  `[sites.*.network]` 下同键 → 直接 `ConfigError`（`config.py::load_config`）。
- `direct_first` **禁止写入 TOML**（检测即 `ConfigError`），只能经
  `SITE_<NAME>_DIRECT_FIRST` 环境变量或 `SITE_CONFIGS` JSON 的 `direct_first` 字段。
- 代理 URL 带 `user:pass@` 时，日志/异常必须 `redact_text`（`security.py` 的
  `_PROXY_USERINFO_RE`），示例见 `pool.py` / `http.py` 的 warning/debug 日志。

## 新增/修改网络行为时的验证

```bash
uv run python -m unittest tests.test_http tests.test_pool tests.test_common -v
```

- 直连优先/粘性/轮换路径各有 mock 用例（`test_http.py`）；解析/去重/探测有
  `test_pool.py` 用例；改常量或轮换逻辑必须补对应测试。
- 代理行为影响签到成败，属 `fix-proxy` 系列（提交历史），改动需保持
  「池空可回退直连」「失败可轮换」两条不变量。
