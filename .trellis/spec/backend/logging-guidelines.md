# 日志规范

> 标准库 `logging`，结构化 `key=value` 日志行，全程凭据脱敏。

## 基础设置（`auto_check_in/log.py`）

- 使用标准库 `logging`（无第三方日志库），logger 名固定 `auto_check_in`。
- 仅 `cli.py::main` 调用 `setup_logging(debug=args.debug)`；格式
  `"%(asctime)s %(levelname)s %(name)s %(message)s"`。
- 级别：`--debug` 标志或 `CHECK_IN_LOG_LEVEL` 环境变量（`DEBUG` / `INFO` 等），默认 `INFO`。
- 其他模块直接 `from .log import logger`，**不**自己调 `basicConfig` / 建新 logger。

## 级别约定

| 级别 | 用途 | 示例位置 |
|------|------|---------|
| DEBUG | 请求细节、代理轮换原因、登录步骤 | `http.py` 直连失败/代理轮换；`sijishe.py` 登录步骤 |
| INFO | 站点/账号结果、会话缓存事件、代理批次、配置识别 | `runner.py` 每账号结果；`session.py` 事件；`config.py` site recognized |
| WARNING | 代理池拉取失败、配置未知键、账号处理中的异常细节 | `pool.py` 拉取失败；`config.py::_warn_unknown`；`sijishe.py` 站点请求失败 |

`requests` 库的请求级日志由 `basicConfig` 统一带出，不额外配置。

## 结构化格式

日志行用 `key=value` 字段，冒号/空格描述放后面：

```python
logger.info(
    "site=%s account=%d username=%s status=%s duration=%.2fs",
    site.name, index, mask_username(account.username), result.status.value, elapsed,
)
```

惯用字段：
- `site=<name>`、`account=<序号>`、`username=<脱敏>`（必须 `mask_username`）
- `status=<CheckInStatus.value>`、`duration=%.2fs`（秒，两位小数）
- 会话缓存事件用 `event=<restored|rejected|saved|restore-miss|persist-skipped>` +
  `cookies=<数量>`（`sijishe.py::_restore_session` / `_persist_session`）
- 代理用 `proxies=<数量>` / `usable=`；代理 URL 必须 `redact_text`（可能含 user:pass）

参考：`runner.py::_run_site`、`sijishe.py` 的 session-cache 事件日志。

## 脱敏铁律（`security.py`）

- **任何日志/输出/结果消息不得出现**：密码、cookie 值、token、代理 `user:pass`、
  24+ 位十六进制串。用 `redact_text(...)` 统一处理。
- 用户名用 `mask_username`（前 2 + `***` + 末 1）。
- 敏感字段只记录是否填充：`login form fields: formhash=filled password_md5=filled`
  （`sijishe.py::_post_login`），绝不记录值。
- 异常消息进日志/结果前先 `redact_text(str(exc))[:200]`（`sijishe.py::run`）。
- `Account` 数据类 docstring 明确「Never include this object in logs」
  （`models.py`）；不要 `repr(account)` 或把 `Account` 塞进日志。

## 反模式

- 把 `account.password` / cookie 值 / `BARK_PUSH` 等凭据直接拼进日志字符串。
- 用 `print()` 代替 `logger` 输出诊断（`print` 只用于 CLI 面向用户的最终结果与错误）。
- 在模块导入期创建多个 logger 实例或重设 `basicConfig`。
- 日志文案包含未脱敏的完整 URL（URL 可含 query 参数/路径片段）。
