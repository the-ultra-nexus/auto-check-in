## Why

当前 `sijishe.py` 将站点访问、浏览器驱动、验证码识别、登录、签到、用户信息抓取和通知混在一个模块中，并且把浏览器路径、站点地址和账号占位值硬编码在入口里。它难以测试、难以扩展到其他签到站点，也容易在定时运行时泄露凭据或留下验证码截图。现在重写可以先建立稳定的运行契约，再逐步增加签到配置。

## What Changes

- **BREAKING** 将签到流程拆分为配置、站点适配器、浏览器会话、结果模型和通知层；保留 `python sijishe.py` 与云函数 `handler` 入口兼容性。
- 引入独立的 TOML 配置文件（可由环境变量覆盖），支持站点、浏览器、重试、超时和通知等配置，并预留多个签到适配器。
- 以结构化的账号解析和运行结果取代全局可变状态；支持 `XSIJISHE` 的 `账号&密码`、多账号换行或 `@` 分隔格式。
- 将 GitHub Actions 作为推荐调度入口，凭据和通知令牌只从 GitHub Actions Secrets 注入，仓库只提交模板配置。
- 为纯逻辑增加单元测试，并提供脱离真实站点的 dry-run/集成验证边界。
- 明确敏感文件、浏览器产物和运行日志的忽略规则，避免提交账号、Cookie、验证码和截图。

## Capabilities

### New Capabilities

- `check-in-runtime`: 可配置、可测试、可观测的多账号签到运行时。
- `secure-configuration`: 配置文件、环境变量和 GitHub Actions Secrets 的分层配置与敏感信息保护。
- `scheduled-execution`: GitHub Actions 定时执行、手动触发和失败通知的运行契约。

### Modified Capabilities

- 无（仓库当前没有已登记的主规格）。

## Impact

- 重写 `sijishe.py`，并将可复用代码移入 `auto_check_in/` 包。
- 新增 `config/` 配置模板、`.github/workflows/` 调度工作流和 `tests/` 单元测试。
- 调整 `pyproject.toml` 的依赖和 CLI 入口；继续使用现有 `notify.py` 通知实现。
- 真实站点 HTML、验证码、Chrome/Chromedriver 版本和网络可用性仍是外部集成前提；单元测试不访问真实站点。
