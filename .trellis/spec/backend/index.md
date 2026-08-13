# 后端开发规范

> auto-check-in 后端开发规范：以真实代码库为准绳的约定。

## 概述

单包 Python 项目（`auto_check_in/`）：纯 HTTP 多站点自动签到，站点由独立适配器实现，
凭据只走环境变量，跨层边界统一用 `AccountResult` + `CheckInStatus` 表达结果。
本目录的规范全部源自现有代码（文件路径可追溯），修改代码前先读对应文件。

## 规范索引

| 指南 | 说明 |
|------|------|
| [目录结构](./directory-structure.md) | 包布局、职责边界、新增适配器流程、公共 API |
| [配置规范](./configuration.md) | 配置来源优先级、敏感键拒绝、校验模式、新增配置项清单 |
| [错误处理](./error-handling.md) | 异常层次、状态枚举、适配器不抛业务异常、退出码 |
| [日志规范](./logging-guidelines.md) | logger 设置、级别、结构化 key=value、脱敏铁律 |
| [网络与代理](./network-and-proxy.md) | 直连优先、按需分批代理、失败轮换、池参数与约束 |
| [会话缓存](./session-cache.md) | cookie 会话缓存：格式、原子写、生命周期、可观测性、CI 契约 |
| [通知通道](./notification-channels.md) | 通道注册表、纯函数约定、SMTP 探测、新增通道流程 |
| [质量规范](./quality-guidelines.md) | 语言/工具链、代码风格、凭据安全、测试要求、禁止模式 |

> 无数据库模块：本项目持久化只有 `.runtime/sessions/` 下的 cookie 会话缓存
> （JSON 文件 + 0600 权限），完整约定见 [session-cache.md](./session-cache.md)。

## 关键规则速查

1. 凭据只走环境变量 / GitHub Secrets；TOML 禁止出现敏感键（写入即 `ConfigError`）。
2. 适配器 `run()` 永不抛业务异常，全部转 `AccountResult` + `CheckInStatus`。
3. 日志/结果/通知一律经 `redact_text` / `mask_username` 脱敏。
4. 数据类用 `@dataclass(frozen=True, slots=True)`；状态用 `StrEnum`；契约用 `Protocol`。
5. 测试用标准库 unittest；新增环境变量必须同步 `.env.example` 与 CI 工作流。
