# 代码复用思维指南

> **目的**：动手写新代码前先停下来思考——它是否已经存在？

---

## 问题

**重复代码是带来不一致 bug 的头号来源。**

当你复制粘贴或重写已有逻辑时：
- bug 修复不会传播
- 行为随时间分叉
- 代码库越来越难理解

---

## 写新代码之前

### 第 1 步：先搜索

```bash
# 搜索相似函数名
grep -r "functionName" .

# 搜索相似逻辑
grep -r "keyword" .
```

### 第 2 步：问自己这些问题

| 问题 | 如果是… |
|------|---------|
| 是否已有相似函数？ | 使用或扩展它 |
| 这个模式是否在别处使用？ | 遵循现有模式 |
| 能否做成共享工具？ | 放到正确的位置 |
| 我是否在从别的文件复制代码？ | **停下**——提取为共享代码 |

---

## 常见重复模式

### 模式 1：复制粘贴的函数

**坏**：把校验函数复制到另一个文件

**好**：提取到共享工具，按需 import

### 模式 2：相似组件

**坏**：新建一个与现有组件 80% 相似的新组件

**好**：用 props/变体扩展现有组件

### 模式 3：重复常量

**坏**：在多个文件中定义同一个常量

**好**：单一事实来源，到处 import

### 模式 4：重复的载荷字段提取

**坏**：多个消费者各自强转相同的 JSON/事件字段：

```typescript
const description = (ev as { description?: string }).description;
const context = (ev as { context?: ContextEntry[] }).context;
```

即使只有两行，这也是重复的契约逻辑——每个消费者现在都有自己的一套"什么是合法载荷"的定义。

**好**：把解码器、类型守卫或投影放到数据所有者旁边：

```typescript
if (isThreadEvent(ev)) {
  renderThreadEvent(ev);
}
```

**规则**：同一个未类型化载荷字段在 2 处以上被读取时，在出现第 3 个读取者之前，先创建共享类型守卫 / 归一化器 / 投影。

---

## 何时抽象

**抽象，当**：
- 同一代码出现 3 次以上
- 逻辑足够复杂、容易出 bug
- 可能有多人需要

**不抽象，当**：
- 只使用一次
- 是琐碎的一行代码
- 抽象比重复更复杂

---

## 批量修改之后

当你对多个文件做了相似修改：

1. **复查**：所有实例都覆盖到了吗？
2. **搜索**：用 grep 找遗漏
3. **考虑**：这部分是否应该抽象？

### Reducer 应使用穷举结构

当状态从类 action 的值（`action`、`kind`、`status`、`phase`）派生时，优先用带单个 `switch` 的 reducer，而不是散落的 `if/else` 更新。

```typescript
// 坏 - 分散的 action 状态迁移难以审计
if (action === "opened") { ... }
else if (action === "comment") { ... }
else if (action === "status") { ... }

// 好 - 单个 reducer 拥有完整的迁移表
switch (event.action) {
  case "opened":
    ...
    return;
  case "comment":
    ...
    return;
}
```

当事件日志是事实来源时这一点尤为重要：reducer 是文档化的回放模型，展示代码与命令不应重复实现该回放模型的片段。

---

## 提交前检查清单

- [ ] 已搜索过现有相似代码
- [ ] 没有应共享却被复制的逻辑
- [ ] 共享解码器之外没有重复的未类型化载荷字段提取
- [ ] 常量只定义在一处
- [ ] 相似模式遵循相同结构
- [ ] reducer/action 迁移只存在于单个 reducer 或命令分发器

---

## 陷阱：Python if/elif/else 无穷举检查

**问题**：Python 的 if/elif/else 链没有编译期穷举检查。当你在 `Literal` 类型（如 `Platform`）中新增一个值时，现有 if/elif/else 链会静默落入 `else`，使用错误默认值。

**症状**：新平台部分可用——某些方法返回 Claude 默认值而非平台特定值，且不报错。

**示例**（`cli_adapter.py`）：

```python
# 坏: "gemini" 落入 else，返回 "claude"
@property
def cli_name(self) -> str:
    if self.platform == "opencode":
        return "opencode"
    else:
        return "claude"  # gemini 静默得到 "claude"！

# 好: 每个平台显式分支
@property
def cli_name(self) -> str:
    if self.platform == "opencode":
        return "opencode"
    elif self.platform == "gemini":
        return "gemini"
    else:
        return "claude"
```

**预防**：向 Python `Literal` 类型新增值时，搜索所有对该类型做 switch 的 if/elif/else 链并补充显式分支。不要指望 `else` 对新值仍然正确。

---

## 陷阱：产生相同输出的非对称机制

**问题**：当两个不同机制必须产生相同的文件集合时（例如 init 用递归目录复制，update 用手工 `files.set()`），结构变更（重命名、移动、新增子目录）只会在自动机制中传播，手工机制会静默漂移。

**症状**：init 完美工作，但 update 把文件创建到错误路径或漏掉文件。

**预防**：
- **最佳**：消除不对称——让手工路径调用自动路径（例如 `collectTemplateFiles()` 调用 `getAllScripts()` 而不是维护自己的列表）
- **无法避免时**：加一个回归测试，比较两种机制的输出
- 迁移目录结构时，搜索所有引用旧结构的代码路径

**真实实例**：`trellis update` 曾用一份手写的 `files.set()` 列表跟踪 11 个脚本，而这些脚本 `getAllScripts()` 早已跟踪。修复：用 `for..of getAllScripts()` 循环替换手写列表。见 v0.4.0-beta.3 的 `update.ts` 重构。

---

## 模板文件注册（Trellis 框架专属）

> 说明：本节涉及 Trellis CLI 自身的源码结构，仅作为"单一注册点"思维模式的示例；本仓库（auto-check-in）不存在 `src/templates/trellis/` 路径，请勿照搬路径。

向 `src/templates/trellis/scripts/` 新增文件时：

**单一注册点**：`src/templates/trellis/index.ts`

1. 加 `export const xxxScript = readTemplate("scripts/path/file.py");`
2. 加进 `getAllScripts()` Map

仅此而已。`commands/update.ts` 直接使用 `getAllScripts()`——无需手工同步。

**为何重要**：未在 `getAllScripts()` 注册的话，`trellis update` 不会把文件同步到用户项目，bug 修复和新功能都无法传播。

**历史**：v0.4.0-beta.3 之前，`update.ts` 有自己的手写文件清单，经常与 `getAllScripts()` 失步，导致 `trellis update` 静默跳过 11 个 Python 文件。修复是消除重复清单，以 `getAllScripts()` 为单一事实来源。

### 新脚本快速检查

```bash
# 新增 .py 文件后，验证它已在 getAllScripts() 中：
grep -l "newFileName" src/templates/trellis/index.ts  # 应有匹配
```

### 模板同步约定

`.trellis/scripts/`（自举使用）与 `packages/cli/src/templates/trellis/scripts/`（模板）必须保持一致。编辑 `.trellis/scripts/` 后总是同步：

```bash
rsync -av --delete --exclude='__pycache__' .trellis/scripts/ packages/cli/src/templates/trellis/scripts/
```

**陷阱**：rsync 源/目标路径写错会产生嵌套垃圾目录（例如 `.trellis/scripts/packages/cli/...`）。运行前务必核对路径。
