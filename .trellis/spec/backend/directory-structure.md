# 目录结构

> 单包 Python 项目（`auto_check_in/`），配置驱动、按站点适配器扩展。

## 概述

这是一个 **单仓库单包** 项目（非 monorepo）：全部运行时代码在 `auto_check_in/` 包内，
每个站点由独立适配器实现登录与签到，通过 `ADAPTERS` 注册表按名称分发。
包外只有配置、测试和 CI 工作流。

```text
auto_check_in/
├── __init__.py        # 公开 API 再导出（Account, CheckInStatus, load_config, run ...）
├── cli.py             # argparse 入口（本地运行与 GitHub Actions 共用）
├── config.py          # TOML + 环境变量配置解析与校验（唯一配置入口）
├── runner.py          # 多站点并行调度（ThreadPoolExecutor），站点间隔离
├── models.py          # 领域模型：CheckInStatus / Account / AccountResult / RunSummary
├── errors.py          # 适配器异常层次（LoginError / CheckInError / SiteUnavailableError）
├── security.py        # 凭据脱敏（mask_username / redact_text）
├── http.py            # FailoverSession（直连优先 + 代理轮换）、SessionProvider、UA 池
├── pool.py            # 代理池按需分批拉取/解析/探测（fetch_pool_batch）
├── session.py         # cookie 会话缓存（JSON 文件，0600，md5 用户名文件名）
├── discuz.py          # Discuz 通用解析（formhash、登录弹框、响应分类）
├── notify.py          # 通知通道注册表（纯函数 + CHANNELS 元组，无全局可变状态）
└── adapters/
    ├── __init__.py    # ADAPTERS: dict[str, type[CheckInAdapter]] 注册表
    ├── base.py        # CheckInAdapter Protocol（适配器契约）
    └── sijishe.py     # SijisheAdapter：司机社纯 HTTP 实现（参考实现）

config/check-in.toml   # 非敏感默认配置（凭据禁止写入，见 config.py 校验）
tests/                 # unittest 测试（Test*.py + helpers.py 共享 fixture）
.github/workflows/     # check-in.yml 定时签到 + 测试
openspec/              # openspec 变更/规格记录
```

## 职责边界

| 关注点 | 放哪里 | 反例 |
|--------|--------|------|
| 站点 HTTP 登录/签到流程 | `adapters/<site>.py` 适配器 | 不放进 `runner.py` |
| Discuz 通用解析（formhash、登录弹框、已签判定） | `discuz.py` 纯函数 | 不复制到各适配器 |
| 跨站点编排与并行 | `runner.py` | 适配器内部不开线程池 |
| 配置解析/校验/环境隔离 | `config.py`（详见 [configuration.md](./configuration.md)） | CLI 里手工读环境变量 |
| 网络容错（直连优先/代理轮换） | `http.py` + `pool.py`（详见 [network-and-proxy.md](./network-and-proxy.md)） | 适配器自建 requests 逻辑 |
| 领域模型与状态枚举 | `models.py` | 适配器自定义状态字符串 |
| 凭据脱敏 | `security.py` | 各模块自写正则 |
| 通知渠道 | `notify.py`（详见 [notification-channels.md](./notification-channels.md)） | 渠道逻辑放进 CLI |

参考：`auto_check_in/adapters/sijishe.py` 复用 `discuz.py` 的
`parse_login_dialog` / `extract_formhash` / `classify_discuz_response`，而不是重新实现。

## 新增站点适配器流程

1. 新建 `auto_check_in/adapters/<name>.py`，实现 `CheckInAdapter` Protocol
   （`__init__(config: SiteConfig)` + `run(account: Account) -> AccountResult`，契约见 `base.py`）。
2. 在 `adapters/__init__.py` 的 `ADAPTERS` 字典注册：`{"<name>": <Name>Adapter}`。
3. 在 `config/check-in.toml` 的 `[sites.<name>]` 补充非敏感配置节。
4. 凭据/base_url 走环境变量（`SITE_<NAME>_BASE_URL` / `SITE_<NAME>_ACCOUNTS`），禁止写 TOML。
5. 新增 `tests/test_<name>.py`，用 `tests/helpers.py` 的 fixture 模拟站点响应。

参考现有实现：`adapters/sijishe.py` + `tests/test_sijishe.py`。

## 公共 API

`auto_check_in/__init__.py` 再导出公开符号（`Account`、`CheckInConfig`、`CheckInStatus`、
`RunSummary`、`load_config`、`parse_accounts`、`run` 等），`__all__` 显式声明。
新增公开符号时同步更新 `__init__.py` 与 `__all__`。
