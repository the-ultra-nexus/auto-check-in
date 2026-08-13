# 质量规范

> 代码质量标准：Python 3.12 + uv、不可变数据类、依赖最小化、凭据安全、unittest。

## 语言与工具链

- Python **>= 3.12**（`pyproject.toml` `requires-python`；CI 用 3.12）。
- 包管理用 **uv**：`uv sync --locked` 安装，`uv run auto-check-in ...` 运行。
- 每个模块文件顶部写 `from __future__ import annotations`（全库统一，见所有模块）。
- 第三方依赖仅 `requests` 与 `lxml`；其余用标准库
  （`tomllib`、`concurrent.futures`、`smtplib`、`hashlib` 等）。新增依赖需在 PRD 说明理由。

## 代码风格

- **类型注解全覆盖**：函数签名、数据类字段、`dict[str, ...]` / `tuple[str, ...]` 泛型。
- 领域与配置模型用 `@dataclass(frozen=True, slots=True)`（不可变）：
  `models.py` 的 `Account` / `AccountResult` / `RunSummary`、`config.py` 的
  `NetworkConfig` / `SiteConfig` / `CheckInConfig`。
- 状态用 `enum.StrEnum`（`CheckInStatus`），配合属性方法（`successful` / `label`）。
- 可变聚合（`RunSummary.results`）用 `field(default_factory=list)`，不用可变默认值。
- 契约用 `typing.Protocol`（`adapters/base.py::CheckInAdapter`）；构造器/依赖注入用
  `Callable` 参数（`session_factory`、`pool_fetcher`）便于测试替身。
- 模块用中英混合 docstring 均可，但**注释风格与既有模块保持一致**（本库偏中文说明）。

## 凭据与配置安全（最高优先级）

- 凭据（密码、cookie、token、代理 user:pass）**只走环境变量 / GitHub Secrets**，
  `config/check-in.toml` 禁止出现 `accounts` / `password` / `passwd` / `secret` / `token` /
  `cookie(s)`、代理池 URL、`direct_first` —— 写入即抛 `ConfigError`（`config.py`
  `_SENSITIVE_SITE_KEYS` 与相关显式检查）。
- 会话缓存文件权限 **0600**，写采用「临时文件 + `os.replace`」原子替换；完整约定见
  [session-cache.md](./session-cache.md)（格式、生命周期、CI 契约）。
- 所有对外输出（结果、通知、日志、异常消息）先经 `security.py` 的 `redact_text` / `mask_username`。
- 环境变量清单单一事实来源是 `.env.example`，`@ci:secrets` / `@ci:vars` 标记 CI 必须透传；
  `tests/test_github_workflow.py` 双向校验该文件与 `.github/workflows/check-in.yml` 的一致性，
  **新增环境变量必须同步两边**。

## 测试要求

- 框架：标准库 **unittest**（非 pytest）。运行命令：
  ```bash
  uv run python -m unittest discover -s tests -v
  ```
- 测试类命名 `<Subject>Tests(unittest.TestCase)`，方法名 `test_<行为描述>`；测试文件按模块
  划分（`test_http.py`、`test_pool.py`、`test_sijishe.py`、`test_notify.py` 等）。
- 共享 fixture 放 `tests/helpers.py`（假站点 HTML、`write_config`、FakeCookie 等），
  测试文件间不互相 import 私有数据。
- HTTP 用 `unittest.mock`（`mock.Mock` / `mock.patch`）打桩，不发起真实网络；
  适配器测试通过 `session_factory` / `session_provider` 注入替身（见 `sijishe.py` 构造器）。
- 新增站点适配器、配置路径、会话缓存行为必须有对应测试；CI 在定时签到前跑
  `test_github_workflow` 校验 env 覆盖，签到后用 `session_files` 指标验证缓存可观测
  （防止「未使用缓存」回归，见提交历史 `fix-unused-cache` 系列）。

## 禁止模式

- **禁止**把凭据写进日志/结果/配置/`print`；禁止 `repr(Account)`。
- **禁止**适配器向 runner 抛裸异常（应转 `AccountResult`，见 error-handling.md）。
- **禁止** `except: pass` 或空 `except Exception` 吞错：要么转状态码，要么 `logger.warning`
  记录后按业务语义处理（`pool.py::fetch_pool_batch` 是合法示例：单池失败降级继续）。
- **禁止**在 `notify.py` 引入模块级可变全局状态 —— 通道是纯函数 + `CHANNELS` 元组，
  每渠道独立超时（`TIMEOUT = 15`），异常不影响其他渠道（`_safe`）。
- **禁止**在 TOML 里放代理池地址或 `direct_first`（必须环境变量/SITE_CONFIGS）。
- **禁止**把 Discuz 解析逻辑复制进各适配器 —— 复用 `discuz.py`。

## 验证命令

```bash
uv run python -m unittest discover -s tests -v   # 全部测试
uv run auto-check-in --config config/check-in.toml --dry-run  # 配置+账号校验（不访问站点）
```
