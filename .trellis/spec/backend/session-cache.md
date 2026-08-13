# 会话缓存规范

> Cookie 会话缓存：跨运行复用有效登录态，失效自动重登，全程可观测（本项目的"持久层"）。

## 定位

本项目无数据库；唯一的持久化是 **cookie 会话缓存**（`auto_check_in/session.py`），
把每个账号的有效登录 cookie 落盘，下次运行免登录。它是核心特性，也是近期
`fix-unused-cache` 系列提交的主题（CI 专门守护"缓存必须被使用"），改动前先读本文件与
`tests/test_session_cache_stats.py`。

## 文件格式与路径

```python
# session.py::session_path
path = session_dir / f"{site_name}_{md5(username).hexdigest()}.json"
```

- 目录：`config.session_dir`，默认 `.runtime/sessions/`（`SessionCacheStats` 所在包的默认值）。
- 文件名：站点名 + **用户名 md5**（不落明文用户名），确定性、可跨运行命中。
- 内容 JSON：`{"saved_at": <epoch 秒>, "cookies": {name: value}}`。
- **权限 0600**（`save_cookies` 对临时文件与最终文件都 `os.chmod`）；任何密钥/token
  只允许放 `cookies` 字段，禁止存 `Account`（含密码）。

## 原子写与容错（session.py）

- 写入：先写 `*.tmp` → `os.chmod(0600)` → `os.replace` 原子替换 → 再 chmod 最终文件。
  绝不用"先删后写"或直接覆盖（崩溃会留下半截文件）。
- 读取：`load_cookies` **永不抛异常**——文件缺失 / JSON 损坏 / 类型异常一律返回 `{}`
  （静默降级为"无缓存"，下次走完整登录）。不要在调用处额外包 try/except 重复该逻辑。
- 过期：`max_age_seconds > 0` 时对比 `saved_at`，超期返回 `{}`；`0` 表示永不过期。

## 配置开关（config.py）

| 配置 | 环境变量 | 语义 |
|------|---------|------|
| `session_cache` (bool) | `CHECK_IN_SESSION_CACHE` | 是否启用缓存 |
| `session_dir` (Path) | `CHECK_IN_SESSION_DIR` | 缓存目录 |
| `session_max_age_seconds` (float) | `CHECK_IN_SESSION_MAX_AGE` | 最大有效期，`0` 关闭；**负数抛 ConfigError** |

## 适配器生命周期（sijishe.py，参考实现）

```text
run(account)
 ├─ _restore_session      # 启用缓存时加载 cookies 到 session；命中 bump(restored)
 ├─ _is_logged_in         # 先看 *_auth cookie，再看签到页 JD_sign 链接
 ├─ _login / _sign_in
 │   └─ 签到结果 LOGIN_FAILED 且本次是恢复的会话
 │        → bump(rejected) + session.cookies.clear() + 重新登录 + 重新签到
 └─ _persist_session      # 满足条件才落盘（见下）
```

关键不变量：

- **不保存匿名会话**：`_persist_session` 只有存在 `*_auth` 且非空的 cookie 才 `save_cookies`；
  否则记 `event=persist-skipped reason=no-auth-cookie`。这是 `fix-unused-cache` 修复的
  核心——防止"登录失败却把空会话当缓存存下来"。
- **禁用即跳过**：`session_cache=False` 时恢复/保存都直接跳过，记
  `event=persist-skipped reason=disabled`，不产生任何文件。
- **陈旧会话回收**：恢复的会话被站点拒绝（签到报 LOGIN_FAILED）时清空 cookie 重登，
  计 `rejected`，避免死循环复用坏缓存。

## 可观测性（SessionCacheStats）

- `SessionCacheStats`（`frozen=True, slots=True`）：`restored` / `rejected` / `saved` 三个计数器。
- `bump()` 返回**新实例**（不可变风格，不原地改）；`merge()` 类方法聚合多站点。
- 适配器暴露 `session_cache_stats` 属性（`SijisheAdapter` 有，runner 兜底 `SessionCacheStats()`）。
- runner 聚合后写入 `RunSummary`，`render()` 输出
  `会话缓存: 恢复 X / 被拒重登 Y / 新保存 Z`（全零时省略该行）。
- 日志事件统一 `event=<restored|rejected|saved|restore-miss|persist-skipped>`
  + `site=` + `mask_username(account)` + `cookies=<数量>`。

## CI 契约（.github/workflows/check-in.yml）

1. **Restore**：`actions/cache/restore@v4`，key `sessions-${{ runner.os }}-${{ github.ref }}-${{ github.run_id }}`，
   `restore-keys` 回退到 `sessions-${{ runner.os }}-${{ github.ref }}-`（同分支跨 run 复用）。
2. **Inspect**：统计 `session_files` / `session_size` 并列出文件（可观测）。
3. **Verify cache reuse**（cache-hit 时强制）：从输出解析
   `会话缓存: 恢复 X / 被拒重登 Y / 新保存 Z`；计数缺失、`restored=0` 或 `saved=0`
   都视为 **Unused session cache** 并 `exit 1`（失败 CI）。
4. **Save**：`Prepare cache save` 在目录为空时置 `skip=true`；`actions/cache/save@v4`
   在 `always()` 且未 skip 时执行。

> 改动 `render()` 的会话缓存行文案或缓存 key 结构时，必须同步更新 CI 的
> Verify/Prepare/Save 步骤与 `tests/test_github_workflow.py`。

## 测试覆盖

- `tests/test_session_cache_stats.py`：恢复命中/未命中、被拒重登、无 auth cookie 跳过、
  禁用跳过、计数器行渲染、`bump`/`merge`。
- `tests/test_common.py`：`test_session_cache_env`、`test_session_max_age_env`、
  `test_expired_cache_returns_empty`、`test_session_cache_stats_aggregated_from_adapters`。
- 新增缓存行为必须补对应测试；CI 的 Verify 步骤是最终回归闸门。

## 反模式

- 在 TOML 配置里声明缓存路径/开关以外的敏感字段，或把 cookie 值写进日志。
- 直接 `open(path, "w")` 覆盖会话文件（绕过 0600 + 原子替换）。
- 不检查 `*_auth` cookie 就 `save_cookies`（会保存匿名/失败会话，触发 CI Unused 失败）。
- 修改缓存 key / 输出文案而不改 CI 验证逻辑（CI 与代码必须同步）。
