## Context

经抓包和页面验证，司机社登录与签到可以完全用 HTTP 完成：

- 签到请求为 GET：`plugin.php?id=k_misign:sign&operation=qiandao&formhash=<动态>&format=empty&inajax=1&ajaxtarget=JD_sign`，带 `Referer: /k_misign-sign.html` 和 `X-Requested-With: XMLHttpRequest`。
- 签到页 HTML 含 `<input type="hidden" name="formhash" value="...">`，每次值不同，必须现取。
- 签到接口返回三种形态：`<root><![CDATA[今日已签]]></root>`、空 CDATA `<root><![CDATA[]]></root>`（成功无提示）、`Discuz! System Error` HTML（会话失效）。
- 站点地址由用户直接提供（`base_url` 必填）。
- 登录走弹框 AJAX：GET `member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1&ajaxtarget=fwin_content_login` 返回 CDATA HTML 表单；表单含隐藏 `formhash`/`referer`、`username`/`password`/`questionid`/`answer`/`cookietime(2592000)`，**当前无验证码字段**。
- 登录 POST 已抓包确认：POST `member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash=<弹框值>&inajax=1`，body 为 `formhash`/`referer`/`username`/`password`（**32 位 MD5，非明文**）/`questionid=0`/`answer=`；请求以 iframe 表单方式提交，**成功响应为空（无数据）**，因此不能依赖响应文本判定，只能靠提交后的登录态确认。

## Login Flow (HTTP)

每个账号在同一 `requests.Session` 中按以下顺序登录：

1. **建立匿名会话**：GET `{base}/k_misign-sign.html`，会话 cookie 由 `requests.Session` 自动保留。
2. **取登录弹框**：GET `{base}/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1&ajaxtarget=fwin_content_login`，解析 CDATA HTML 中的表单：`formhash`、`referer`、`loginhash`（来自 form action）、`cookietime=2592000`；`questionid` 默认 0。
3. **可选验证码路径**：若表单出现 seccode 字段（未来站点策略变化），先 GET 验证码图并 OCR 后随表单提交；当前表单无验证码，此路径默认不启用。
4. **登录 POST**：POST `{base}/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash=<弹框值>&inajax=1`，body 为 `formhash`、`referer`、`username`、`password=md5(原密码)`、`questionid=0`、`answer=`，并带上 `cookietime=2592000` 保持登录态；headers 带 `Content-Type: application/x-www-form-urlencoded`、`Origin`、`Referer` 和 UA。MD5 与弹框页面 JS 行为一致，首次真实运行需确认单次 MD5 正确。
5. **成功判定**：登录 POST 响应为空属预期行为；以随后 GET 签到页呈现已登录状态为准（出现签到按钮而非登录链接），辅助判定为 session cookie 中出现 `SgL6_2132_auth`；否则重新取弹框（新 formhash/loginhash）在 `network.retries` 预算内重试，仍失败返回 `login-failed`。

## Sign-in Flow (HTTP)

登录成功后在同一 session 中：

1. GET `{base}/k_misign-sign.html`，解析 `input[name=formhash]`（签到页 formhash，与登录页不同来源）；页面含“今日已签”直接返回 `already-checked-in`。
2. GET 签到接口（带新 formhash、Referer、`X-Requested-With` 和 session cookie）。
3. 响应分类：`Discuz! System Error` → `login-failed`；CDATA `今日已签` → `already-checked-in`；CDATA 空 → `success`；其他 → 重取 formhash 重试一次 → `check-in-failed`。
4. 不采集签到统计；结果仅包含状态与脱敏原因。

## Multi-Site Parallel Runtime

- 启用站点：环境变量 `CHECK_IN_SITES`（逗号分隔，如 `sijishe,site2`）或配置默认列表。
- 站点隔离：每站独立环境变量 `SITE_<NAME>_BASE_URL`（必填）与 `SITE_<NAME>_ACCOUNTS`（必填）；非敏感默认值可放 `[sites.<name>]`，凭据只从环境注入。
- 并行执行：同进程内用线程池并行处理各站点，默认并行度为 `min(站点数, 4)`，可用 `CHECK_IN_MAX_WORKERS` 覆盖；每个站点独立 `requests.Session`，站点内账号串行，账号间不共享会话。
- 失败隔离：一站失败不中断其他站；所有站结束后统一汇总，任一失败则退出码为 1。
- GitHub Actions：单 job 内并行，线程级并发只占一台 runner，不占用并发 job 额度，总运行时间约等于最慢站点。

## Session Cache

- 每个站点+账号的登录 cookie 保存在 `.runtime/sessions/<site>_<账号md5>.json`（权限 0600，目录已 gitignore）。
- 每次运行先加载并验证登录态：auth cookie 有效或签到页呈已登录状态则跳过登录直接签到。
- 签到返回 `login-failed`（会话失效）时清空 cookie、重新登录一次再签到；成功后写回缓存。
- 可用 `CHECK_IN_SESSION_CACHE=false` 关闭，`CHECK_IN_SESSION_DIR` 修改目录。

## Multi-Site Workflow Configuration

- 工作流不写死站点名：`SITE_CONFIGS`（JSON Secret）集中定义全部站点的 adapter/base_url/accounts；`CHECK_IN_SITES`（仓库变量或环境变量）可运行全部或子集，留空则运行 `SITE_CONFIGS` 全部键。
- 单站参数优先级：`SITE_<NAME>_*` 环境变量 > `SITE_CONFIGS` > TOML `[sites.<name>]`。
- 新增站点只需更新 `SITE_CONFIGS`（若为全新适配器类型还需注册 `ADAPTERS`），无需改动工作流 YAML。

## Goals / Non-Goals

**Goals:**

- 只保留登录与签到，全程纯 HTTP。
- 站点地址直接配置，无地址发现流程。
- 多站点单进程并行，环境数据完全隔离。
- 退出码规范（0/1/2），凭据脱敏。

**Non-Goals:**

- 不做站点内账号并行（各站点账号串行，降低触发风控的概率）。

## Decisions

1. **传输层**：`requests.Session` 统一 UA/Referer；每账号独立会话；可替换 session 工厂，若站点防护收紧可切 `curl_cffi`（同为 HTTP）。
2. **页面解析**：lxml XPath，见 Login/Sign-in Flow。
3. **配置**：`base_url` 必填；`CHECK_IN_SITES` + `SITE_<NAME>_*` 环境隔离；站点默认值放 `[sites.<name>]`。
4. **并行编排**：`ThreadPoolExecutor` 按站点并行；`CHECK_IN_MAX_WORKERS` 控制并发；站点内账号串行。
5. **退出码**：0 = 全部成功/已签到，1 = 任一账号失败，2 = 配置错误（启动前失败）。
6. **脱敏**：统一 redact 函数，结果消息、日志与通知不输出密码、cookie、验证码原文。
7. **测试**：HTML/XML fixture + mock session，覆盖登录、签到分类、并行编排、退出码与脱敏。
8. **调度**：GitHub Actions 单 job 内并行跑全部启用站点。

登录表单当前无验证码，因此 OCR 不作为运行时依赖；仅当弹框表单出现 seccode 字段时才启用可选 OCR 路径（后续按需引入）。

## Risks / Trade-offs

- [站点防护收紧] → session 工厂切 `curl_cffi`，仍为纯 HTTP。
- [站点响应文案变化] → 判定词集中为常量，失败输出脱敏摘要。
- [formhash/会话失效] → 每次现取；签到失败重取一次。
- [空 CDATA 无提示] → 保留响应摘要便于首次真实运行核对。
- [并行请求触发风控] → 并行度可配、站点内账号串行；必要时增加请求间隔。
- [登录 POST 响应为空] → 已确认预期行为；成功判定完全依赖提交后签到页登录态，不解析响应文本。

## Migration Plan

1. 实现登录+签到适配器与多站点并行编排。
2. fixture 单测 + 测试账号真实签到。
3. 手动触发 GitHub Actions 验证单 job 多站点并行。
4. 确认后归档本变更。

## Open Questions

- 默认并行度（4）是否合适，是否需要站点级请求间隔配置；账号级并行暂不做，后续按站点规模再评估。
- 密码单次 MD5 算法需在首次真实运行验证；未来是否出现验证码以真实弹框为准。
