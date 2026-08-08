## Context

现有 `sijishe.py` 是单文件脚本，使用模块级全局变量串联 Selenium、requests、OCR 和通知。登录页结构、发布页地址、Chrome 路径和测试账号占位值散落在代码中；异常处理也可能在工作目录留下截图或验证码。运行目标包括本地 CLI、青龙/云函数兼容入口和 GitHub Actions 定时任务。

约束：真实站点是不可控的外部边界，验证码识别需要 ddddocr，浏览器需要 Chrome/Chromedriver；凭据只能在运行时注入。重写应减少全局状态，保证网络请求有超时，并让每个账号都有可通知的最终状态。

## Goals / Non-Goals

**Goals:**

- 将通用运行流程与司机社站点适配逻辑分离，并用协议支持未来站点适配器。
- 使用类型化 TOML 配置和环境变量覆盖，支持多账号、浏览器、重试、发现地址和通知选项。
- 在 GitHub Actions 中安全地使用 Secrets，默认不输出密码、Cookie、验证码或完整响应体。
- 保留 `sijishe.py` 的脚本和 `handler(event, context)` 入口，并提供可测试的纯函数。
- 在不访问真实站点的情况下覆盖配置、账号解析、状态映射和错误汇总。

**Non-Goals:**

- 不绕过或修改站点验证码策略，不保证第三方站点 DOM 永久稳定。
- 不在本次重写中实现第二个具体站点适配器或通知服务重写。
- 不将账号密码提交到仓库、配置文件或 GitHub Actions 日志。

## Decisions

1. **包结构和适配器协议**：新增 `auto_check_in` 包，定义 `CheckInAdapter` 协议和 `CheckInRunner`。`SijisheAdapter` 负责发布页发现、登录、签到和用户信息抽取；核心只消费 `AccountResult`。选择协议而不是继承深层基类，是为了让未来适配器只实现所需方法。
2. **配置分层**：提交 `config/check-in.toml` 作为非敏感默认值；`load_config()` 读取显式路径后应用环境变量覆盖，凭据只从 `XSIJISHE` 或 GitHub Secret 读取。使用 `tomllib` 和 dataclass 校验，避免 YAML 运行时依赖和隐式类型转换。
3. **浏览器生命周期**：每次运行创建一个 `BrowserSession`，使用 Selenium `Service` 配置 driver，支持 headless、binary、driver、user-agent 和超时。账号之间清理 cookie，`finally` 确保 quit；截图仅在显式 debug 配置下写入受忽略的目录。
4. **网络与 OCR 边界**：适配器使用带默认超时的 `requests.Session`；OCR 在需要时惰性初始化。解析函数接受 HTML/字节输入并返回结构化数据，单测不启动浏览器或调用网络。
5. **结果与通知**：每个账号返回 `SUCCESS`, `ALREADY_CHECKED_IN`, `LOGIN_FAILED`, `SITE_UNAVAILABLE`, `CHECK_IN_FAILED`, `CONFIG_ERROR` 等稳定状态；通知层只接收脱敏后的汇总文本。部分账号失败不会阻止其他账号，进程最终以失败数量决定退出码。
6. **调度入口**：`sijishe.py` 作为薄兼容层调用 CLI/runner；GitHub Actions 使用 `workflow_dispatch` 和 cron，Secrets 通过 `env` 注入，工作流权限设为只读。这样本地、青龙和 GitHub 使用同一业务入口。

## Risks / Trade-offs

- [站点 DOM 或发布页变化] → 所有选择器和 URL 规则集中在 `SijisheAdapter`，失败返回明确状态并通知；保留手工集成检查。
- [GitHub runner 缺少兼容 Chrome/Chromedriver] → 工作流安装稳定 Chrome，代码允许显式配置 binary/driver；启动失败按配置错误通知。
- [OCR 依赖体积和 Intel Mac 兼容性] → 保留现有锁定版本并惰性导入，纯逻辑命令不要求初始化 OCR。
- [账号输入格式错误] → 解析时逐项校验并脱敏报告，不打印原始 payload。
- [第三方通知失败遮蔽签到结果] → 通知发送独立捕获异常，先保留控制台摘要并以签到结果作为主要退出码。

## Migration Plan

1. 提交新包、配置模板、测试和 GitHub Actions；先用 `--dry-run`/单元测试验证。
2. 将仓库 Secrets `XSIJISHE` 及通知所需变量配置到 GitHub 项目，手动触发 workflow 验证单账号。
3. 确认真实签到和通知后切换 cron；旧脚本入口保留为兼容代理。
4. 回滚时恢复旧入口文件和 workflow，Secrets 无需迁移。

## Open Questions

- 司机社当前有效域名和登录 DOM 可能变动；首次部署需以真实页面确认选择器。
- 是否需要将通知渠道从现有 `notify.py` 拆为独立包，留待后续变更。
