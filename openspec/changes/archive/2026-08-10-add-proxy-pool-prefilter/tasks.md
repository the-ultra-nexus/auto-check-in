## 1. 配置与 env 面

- [x] 1.1 `config.py`：移除静态代理列表解析与 env 接线（`CHECK_IN_PROXY_URLS` / `SITE_<NAME>_PROXY_URLS`，含 TOML 禁用提示与相关校验）
- [x] 1.2 `config.py`：`NetworkConfig` 新增 `proxy_pool_urls` 字段；解析 `CHECK_IN_PROXY_POOL_URLS`（逗号分隔、校验 URL 格式）；检测到 TOML 中写入池 URL 时抛 `ConfigError`
- [x] 1.3 补给/粗探参数用模块常量（`BATCH_SIZE=5`、`MAX_BATCHES=5`、粗探 connect 2s / total 4s、并发 10、拉池 1MB/10s、每池上限 200），不新增 env
- [x] 1.4 `SiteConfig` 新增 `direct_first: bool = True`：`SITE_<NAME>_DIRECT_FIRST` env 优先 > `SITE_CONFIGS` 每站点 `direct_first` 字段 > 默认 true；检测到 TOML `[sites.<name>]` 写 `direct_first` 时抛 `ConfigError`
- [x] 1.5 `.env.example` 删除静态代理两项、增加 `CHECK_IN_PROXY_POOL_URLS=  # @ci:secrets`；`check-in.yml` env 同步；运行 `tests/test_github_workflow.py` 确认双向校验通过

## 2. 池批次提供器 `auto_check_in/pool.py`

- [x] 2.1 并发拉池：全部池 URL 并发拉取（每池字节上限 1MB、超时 10s），失败跳过并 warn；池地址日志经 `redact_text()` 脱敏
- [x] 2.2 多格式解析：`host:port` / `http(s)://host:port` / 空白或制表符分隔表格取前两列；非法行跳过并计数；按 `host:port` 去重后截断上限
- [x] 2.3 短超时并行粗探：`ThreadPoolExecutor` 并发 10，connect 2s / total 4s，2xx/3xx 判可用，凑满 5 个可用（`BATCH_SIZE=5`）即提前终止；返回一批，不做全量排序

## 3. `FailoverSession` 按需补给

- [x] 3.1 站点级直连优先（`direct_first` 来自 `SiteConfig`）：`FailoverSession.request()` 首个站点请求先直连（短超时预算，复用粗探 connect 2s / total 4s），直连成功（2xx/3xx）→ 返回并粘住直连、不拉批；直连失败（403/429/5xx/超时/拒连/TLS）→ 才调用批次提供器拉批，用批内代理重试同一请求；站点 `direct_first=False` 时无条件先拉批再发请求
- [x] 3.2 `request()`：当前批次已全部尝试失败时，调用批次提供器取下一批继续重试同一请求；任一请求成功即停止获取
- [x] 3.3 触发边界：拉批仅由传输层失败（403/429/5xx/超时/拒连）触发；会话层失败（页面 200 但未登录 / 无 formhash / 签到 `login-failed`）不拉批，清 cookie 重新登录（复用当前批次，无批次则按登录路径拉批）
- [x] 3.4 上限：每请求最多 `MAX_BATCHES` 批；批次上限内全部失败时抛最后一个错误（账号 `site-unavailable` 语义）
- [x] 3.5 兜底：池拉取失败/取不到代理 → 直连 + warn，不中断 run
- [x] 3.6 日志：批次获取/耗尽聚合日志（避免每代理一行刷屏），代理地址脱敏；直连成功/失败计数（含失败原因）供实验期统计
- [x] 3.7 批次按站点隔离：每个站点的 `FailoverSession` 各自拉批、各自持有与轮换，站点间不共享批次（`_proxy_urls` 为会话实例级）
- [x] 3.8 `runner.py`：删除运行前预筛逻辑（不再替换 `network.proxy_urls`）

## 4. 配置与文档重组

- [x] 4.1 `openspec/config.yaml`：重写 context 为纯 HTTP 多站点现状（去掉 Selenium/OCR/ddddocr/onnxruntime；补代理池按需补给（批次按站点隔离）、失败轮换、会话缓存、多通知）；rules 补充代理池 env-only/脱敏/超时上限、流程边界
- [x] 4.2 `config/check-in.toml`：分区规范为 `[runtime] → [network] → [notification] → [sites.<name>]`；文件头写敏感信息与池 URL 禁止写入；`[network]` 注释列出补给/粗探模块常量当前值，不新增 TOML key
- [x] 4.3 README：代理池/边界章节同步按需补给机制（批次按站点隔离）；新增「命令行参数」表（`--config`/`--dry-run`/`--no-notify`/`--notify-only`/`--debug` 含缺省值）
- [x] 4.4 新增 `SITE_CONFIGS.example.json`：每站点 `base_url`/`accounts`/`sign_path`/`direct_first` 示例；README「SITE_CONFIGS 示例」与 `.env.example` 的 `SITE_CONFIGS` 行引用该文件；确认 git 跟踪（`git status` 显示 A，非忽略）
- [x] 4.5 删除 `scripts/test_proxy_connectivity.sh`（全量探活脚本已废弃，不再交付独立 CLI）；确认无残留引用

## 5. 测试

- [x] 5.1 静态代理用例移除/改写为池解析单测：三种格式、去重、非法行跳过、上限截断、TOML 写入报错
- [x] 5.2 粗探判定单测（mock requests）：2xx/3xx 可用、403/429/5xx/超时/拒连剔除
- [x] 5.3 直连优先单测（mock 批次提供器）：直连成功 → 返回且不拉批；直连失败 → 拉批后走代理重试；`direct_first=False` → 无条件先拉批；直连粘住后后续传输层失败 → 再拉批
- [x] 5.4 触发边界单测：页面 200 但 `login-failed` → 不拉批、清 cookie 重登（复用当前批次）；传输层失败 → 拉批
- [x] 5.5 补给逻辑单测（mock 批次提供器）：首请求取批、批次耗尽取下一批、成功粘性、`MAX_BATCHES` 内全败 → `site-unavailable`
- [x] 5.6 兜底单测：池拉取失败/取不到代理 → 直连，run 不中断
- [x] 5.7 批次站点隔离单测：两个站点会话各自拉批，互不共享批次
- [x] 5.8 `direct_first` 站点级解析单测：`SITE_<NAME>_DIRECT_FIRST` env > `SITE_CONFIGS` 每站点字段 > 默认 true；TOML 写入报错
- [x] 5.9 env 一致性：`.env.example` 与 workflow env、`test_github_workflow.py` 同步后全绿
- [x] 5.10 全量 `uv run python -m unittest discover -s tests -v` 与 `compileall` 通过

## 6. 验证

- [ ] 6.1 本地：配置 `CHECK_IN_PROXY_POOL_URLS`（jsdelivr https 池 + 备用池）跑 `--debug`，确认直连优先日志（直连成功/失败 → 拉批）与各站点独立补给日志、签到
- [ ] 6.2 CI：仓库设置 `CHECK_IN_PROXY_POOL_URLS` Secret 后 `workflow_dispatch` 复测，确认签到使用补给获得的代理
- [ ] 6.3 实验观测：连续运行 ≥7 个有效日，按站点统计直连成功率；某站点持续为 0 → 该站点 `direct_first` 改为 `false`（保留无条件先拉批路径）
- [ ] 6.4 回滚：仅新增模块与 env 与文档，revert 即可，无数据迁移
