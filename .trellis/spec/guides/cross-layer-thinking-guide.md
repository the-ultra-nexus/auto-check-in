# 跨层思维指南

> **目的**：实现前先想清楚跨层数据流。

---

## 问题

**大多数 bug 发生在层边界**，而不是层内部。

常见跨层 bug：

- API 返回格式 A，前端期望格式 B
- 数据库存 X，服务转成 Y，却丢了数据
- 多个层用不同方式实现同一逻辑

---

## 实现跨层功能之前

### 第 1 步：画出数据流

画出数据如何流动：

```
来源 → 转换 → 存储 → 读取 → 转换 → 展示
```

对每个箭头问：

- 数据是什么格式？
- 可能出什么错？
- 谁负责校验？

### 第 2 步：识别边界

| 边界 | 常见问题 |
|------|---------|
| API ↔ 服务 | 类型不匹配、字段缺失 |
| 服务 ↔ 数据库 | 格式转换、null 处理 |
| 后端 ↔ 前端 | 序列化、日期格式 |
| 组件 ↔ 组件 | props 形状变化 |

### 第 3 步：定义契约

对每个边界：

- 精确的输入格式是什么？
- 精确的输出格式是什么？
- 可能发生哪些错误？

---

## 常见跨层错误

### 错误 1：隐式格式假设

**坏**：假设日期格式而不检查

**好**：在边界做显式格式转换

### 错误 2：校验分散

**坏**：在多个层校验同一件事

**好**：在入口处校验一次

### 错误 3：抽象泄漏

**坏**：组件知道数据库 schema

**好**：每层只认识相邻层

### 错误 4：每个消费者都解析同一载荷

**坏**：命令读取 JSONL 事件并内联强转字段：

```typescript
const thread = (ev as { thread?: string }).thread;
const labels = (ev as { labels?: string[] }).labels;
```

这看起来局部化，但意味着每个消费者都私有一份事件契约。下次字段变更会更新一个命令而漏掉另一个。

**好**：在事件边界解码一次，然后导出类型化投影：

```typescript
if (!isThreadEvent(ev)) return false;
return ev.thread === filter.thread;
```

**规则**：对追加型日志、JSON 流、RPC 载荷或配置文件，为以下内容创建唯一所有者：

- 事件 / 载荷类型定义
- 从 `unknown` 开始的类型守卫与归一化
- UI 命令使用的元数据投影
- 从事实来源回放状态的 reducer

渲染代码可以格式化字段，但不得重新定义载荷契约。

---

## 跨层功能检查清单

实现前：

- [ ] 画出了完整数据流
- [ ] 识别了所有层边界
- [ ] 定义了每个边界的格式
- [ ] 决定了校验位置

实现后：

- [ ] 用边界情况测试（null、空、非法）
- [ ] 验证了每个边界的错误处理
- [ ] 检查数据能往返无损
- [ ] 检查消费者 import 共享解码器 / 投影，而不是本地强转载荷字段
- [ ] 检查派生状态回指源事件标识（`seq`、`id`、`version`），而不是另造第二个游标

---

## 跨平台模板一致性（Trellis 框架专属）

> 说明：本节及以下"生成型运行时模板""版本化文档""模式探测"各节为 Trellis CLI 自身开发中的真实案例，仅作思维模式参考；本仓库（auto-check-in）无 `src/templates/`、`docs-site/` 等路径，请勿照搬路径。

在 Trellis 中，命令模板（如 `record-session.md`）以相同或近相同内容存在于**多个平台**。这是跨层边界。

### 修改任意命令模板后的检查清单

- [ ] 找到所有含同一命令的平台：`find src/templates/*/commands/trellis/ -name "<command>.*"`
- [ ] 更新所有平台副本（Markdown `.md` 与 TOML `.toml`）
- [ ] Gemini TOML：适配续行（`\\` vs `\`）与三引号字符串
- [ ] 运行 `/trellis:check-cross-layer` 验证无遗漏

**真实案例**：在 Claude 中把 `record-session.md` 更新为 `--mode record`，却忘了 iFlow、Kilo、OpenCode 与 Gemini——被跨层检查捕获。

---

## 生成型运行时模板升级一致性

部分生成文件既是文档也是运行时输入。在 Trellis 中，`.trellis/workflow.md` 会被 `get_context.py`、`workflow_phase.py`、SessionStart 过滤器与逐轮 hook 解析。模板变更必须同时对新 init 与升级路径验证。

### 修改运行时解析模板后的检查清单

- [ ] 找出读取该模板的**每个**运行时解析器，而不只是安装它的文件写入器
- [ ] 检查相关语法是否位于明显受管区域（如标签块）之外
- [ ] 验证全新 `init` 输出与写入旧 `.trellis/.version` 的版本化 `update` 场景
- [ ] 用旧版原始模板 fixture 添加升级回归，断言安装后的文件达到当前打包形态
- [ ] 更新拥有该运行时契约的后端规范

**真实案例**：Codex inline 模式把工作流平台标记从 `[Codex]` / `[Kilo, Antigravity, Windsurf]` 改为 `[codex-sub-agent]` / `[codex-inline, Kilo, Antigravity, Windsurf]`。全新 init 正确，但 `trellis update` 只合并 `[workflow-state:*]` 块，保留了块外过期标记。结果：升级项目拿到新 hook 脚本却沿用旧工作流路由，`get_context.py --mode phase --platform codex` 可能返回空的 Phase 2.1 详情。

---

## 版本化文档边界

版本化文档是跨层边界：源码路径、`docs.json` 版本路由、渲染的版本选择器必须描述同一条发布线。

### 编辑版本化文档前的检查清单

- [ ] 确定目标发布线：stable、beta 或 RC
- [ ] 验证编辑的 MDX 路径与该线匹配：
  - stable：`docs-site/{start,advanced,...}` 与 `docs-site/zh/{start,advanced,...}`
  - beta：`docs-site/beta/**` 与 `docs-site/zh/beta/**`
  - RC：`docs-site/rc/**` 与 `docs-site/zh/rc/**`
- [ ] 验证 `docs.json` 导航把版本标签指向相同路径
- [ ] 提交前 grep 反方向树中的发布线专属术语
- [ ] 把根发布路径下出现的 beta 内容视为源码路径 bug，而非渲染 bug

**真实案例**：一次仅 beta 的任务工作流变更，把 `prd.md` + `design.md` + `implement.md`、任务创建同意、Codex 模式横幅等内容写进了根 `start/` 与 `advanced/` 路径。文档站在 Release 选择器下提供了 0.6 beta 行为。修复：恢复根发布文档，把 0.6 内容移到 `beta/` 与 `zh/beta/`，并加 grep 审计根发布树中的 beta 标记。

---

## 模式探测检查清单

当 CLI 通过探测远程资源自动检测模式时（例如检查 `index.json` 是否存在来决定 marketplace 还是直接下载）：

### 实现前：

- [ ] 探测在**所有**使用其结果代码路径中运行（交互、`-y`、`--flag` 组合）
- [ ] 区分 404 与瞬时错误——不要都当作"未找到"
- [ ] 瞬时错误**中止或重试**，绝不静默切换模式
- [ ] 上下文变化时（如用户切换来源）**重置**共享状态（缓存、预取数据）
- [ ] **捷径路径**（如 `--template` 跳过选择器）必须有与探测路径相同的错误处理质量——检查下游函数不调用 catch-all 包装器

### 实现后：

- [ ] 追踪从探测结果到模式决策分支的每条路径——无落穿
- [ ] 外部格式契约（giget URI、原始 URL）有测试或至少以注释记录
- [ ] 元数据读取消费完整响应或用流式解析器——绝不用固定大小前缀当完整 JSON 解析
- [ ] 从解析片段重组复合标识时，验证**所有**字段都包含且**位置正确**（例如 `provider:repo/path#ref`，而非 `provider:repo#ref/path`）
- [ ] 验证捷径后调用的**动作函数**内部不使用旧 catch-all fetch——错误区分重要时，必须用探测质量变体

**真实案例**：自定义 registry 流程在 3 轮审查中出现 8 个 bug：(1) 探测只在交互模式运行；(2) 瞬时错误落入错误模式；(3) giget URI 的 `#ref` 位置错误；(4) 预取模板跨来源切换泄漏；(5) `--template` 捷径绕过探测，但 `downloadTemplateById` 内部用 catch-all `fetchTemplateIndex`，把超时变成"Template not found"。

**真实案例**：agent 会话更新提示用 `response.read(4096)` 拉取 npm `latest` 元数据后当作完整 JSON 解析。`@mindfoldhq/trellis` 包元数据超过 4 KB，JSON 被截断、解析静默失败，首次会话注入不显示更新提示。修复：解析前读完整响应，并加回归（`version` 后跟 8 KB 元数据尾）。

---

## 何时创建流程文档

当以下情况时创建详细流程文档：

- 功能跨越 3 个以上层
- 涉及多个团队
- 数据格式复杂
- 该功能以前出过 bug

---

## 事件日志 / 投影边界

追加型日志是跨层契约。单个事件流动如下：

```
CLI 输入 → 事件写入器 → events.jsonl → 读取器 → 过滤器 → reducer → 展示
```

### 新增事件类型或字段后的检查清单

- [ ] 把事件类型加进中央事件分类法
- [ ] 在事件层添加类型化事件变体或类型守卫
- [ ] 为来自用户输入或 JSON 的数组/对象字段添加归一化辅助
- [ ] `seq` / `id` 赋值只发生在事件写入器
- [ ] 过滤器与 reducer 消费类型化事件守卫，而非本地强转
- [ ] 展示代码消费 reducer 输出或类型化事件，而非原始 JSON
- [ ] 至少一个回归证明历史回放与实时过滤使用同一过滤模型

**真实案例**：线程通道新增 `kind: "thread"`、`description`、`context`、labels 与 `lastSeq`。第一版正确回放线程状态，但若干命令仍用本地强转重新解析事件载荷字段。修复：让核心事件层拥有 `ThreadChannelEvent` 与 `isThreadEvent`，让 `reduceChannelMetadata` 成为唯一的通道元数据投影，让 `reduceThreads` 成为唯一的线程回放 reducer。
