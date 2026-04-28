# Puzzle 项目后续改进：Coding Agent 面试准备

面向问题：

- “如果继续优化这个项目，你会怎么做？”
- “后续能不能让 Agent 自己扩展游戏规则？”
- “怎么保证 Agent 写代码是安全、可回滚、可验证的？”
- “Coding Agent 和你现在的多 Agent 架构怎么结合？”

核心回答：

我会把当前系统从“Agent 辅助关卡设计”进一步扩展到“Agent 辅助规则与底层能力开发”。现有系统里已经有 `planner / generator / critic / controller` 的多 Agent 闭环，也预留了 `rule_refactor_agent` 节点。后续可以把这个节点升级成 Coding Agent 分支，让它在用户明确提出新增规则、扩展机制或修改求解器能力时，进入“方案设计 - 用户确认 - 代码修改 - 自动验证 - 失败修复 - 可回滚”的闭环。

## 一、为什么要加入 Coding Agent

当前系统主要解决的是“在已有规则内生成和修改关卡”。但如果用户想要的是新增机制，比如新的移动规则、新的格子效果、新的 goal 判定、新的求解器策略，仅靠修改关卡 JSON 不够，必须修改底层规则框架、前端编辑器、求解器和校验逻辑。

所以后续加入 Coding Agent 的价值是：

- 从“改内容”升级到“改能力”
- 让自然语言需求可以转化为规则框架或求解器代码改动
- 复用现有确定性验证和求解器回归，避免代码生成后不可用
- 让 Agent 不只是生成方案，而是能在受控边界内实现方案

面试可说：

> 这个项目当前已经能让 Agent 修改关卡内容，但规则和机制本身仍然需要人工开发。后续我希望加入 Coding Agent，让它在用户提出新增规则或底层机制扩展时，先分析现有代码和规则体系，再给出设计方案，用户确认后进入代码修改和自动验证流程。这样系统就能从“内容生成”演进到“能力扩展”。

## 二、Coding Agent 应该放在什么位置

不应该让 Coding Agent 固定接在 planner 后面每次都执行，而应该作为 planner 之后的条件分支。

推荐架构：

```text
用户请求
-> 前端 AI 对话框
-> Orchestrator
-> Planner Agent
-> Router / Controller
   -> 普通关卡修改：level generator / critic 闭环
   -> 底层规则扩展：coding agent 闭环
```

Planner 的输出需要增加类似字段：

```json
{
  "intent_type": "rule_extension",
  "execution_mode": "coding_plan",
  "requires_code_change": true
}
```

这样可以避免普通“调难度”“加障碍物”请求误触发代码修改。

面试可说：

> 我不会把 Coding Agent 设计成每次都执行的线性节点，而是把它放在 planner 后面的条件分支。Planner 先判断用户请求属于关卡内容修改还是底层规则扩展，如果只是改关卡，就走现有 generator/critic；如果需要新增机制或修改求解器，再路由到 Coding Agent。这样可以降低误修改代码的风险，也让职责边界更清楚。

## 三、Coding Agent 的两阶段模式

Coding Agent 不应该一上来就写代码，而应该分成两个阶段。

### 第一阶段：Proposal Mode

只分析，不改代码。

职责：

- 阅读现有代码结构
- 定位相关模块
- 分析新增规则会影响哪些层
- 输出修改方案
- 列出预计修改文件
- 说明兼容性风险
- 给出验证计划
- 等待用户确认

适合回答：

> 对底层规则进行修改风险比较高，所以第一阶段我会让 Coding Agent 只做 proposal。它先读代码、读规则包、读求解器接口，分析新增机制会影响哪些模块，比如前端编辑器、rule pack、求解器、校验器和回放逻辑。然后它输出修改方案和验证计划，只有用户确认后才进入执行阶段。

### 第二阶段：Execution Mode

用户确认后才允许写代码。

职责：

- 创建修改快照
- 检查文件权限边界
- 生成并应用 patch
- 编译、测试、运行求解器回归
- 如果失败，进入有限轮修复
- 如果成功，输出 diff、验证结果和变更说明

适合回答：

> 用户确认方案后，Coding Agent 才进入 execution mode。这个阶段它会基于白名单文件生成 patch，修改后运行编译、测试和求解器回归。如果失败，controller 会把错误反馈给 Coding Agent 做有限轮修复；如果仍然失败，就回滚或保留为 failed proposal。

## 四、红区、白区、灰区权限设计

为了保证安全，Coding Agent 需要文件权限边界。

### 白区：允许修改

这些是正常开发区域：

- `v1/java-solver/src/main/java/...`
- `v1/rulepacks/...`
- `v1/foundation/...`
- `src/core/...`
- `backend/ai/...`
- `backend/services/...`
- `docs/...`
- 测试用例目录

### 灰区：需要用户二次确认

这些改动影响范围较大：

- 跨前后端协议
- session store schema
- rule pack 兼容性变更
- 删除旧规则
- 大规模重构
- 构建配置

### 红区：禁止修改

这些是安全边界：

- `.git/`
- `.env`
- API key 或本地密钥
- session 数据库文件
- 用户数据
- 生产配置
- 未授权的大规模删除逻辑

面试可说：

> 我会给 Coding Agent 设置红区、白区和灰区。白区是允许直接修改的业务代码和测试代码；灰区是协议、schema、大规模重构这类需要二次确认的内容；红区是密钥、数据库、用户数据和 git 元数据等禁止修改的区域。这样可以把 Agent 写代码的能力限制在安全边界内。

## 五、回滚机制怎么设计

不要依赖危险的全局重置，而应该使用 patch 和快照机制。

推荐做法：

- 修改前记录文件快照和 hash
- 所有修改都以 patch 形式应用
- 每次验证结果与 patch 绑定
- 失败时可以自动修补、保留 diff 或回滚到快照
- 用户可以查看变更摘要后决定是否应用

可以抽象一个对象：

```text
CodeChangeSession
```

包含：

- `change_id`
- `requested_goal`
- `proposal`
- `allowed_files`
- `original_snapshots`
- `patches`
- `test_results`
- `status`
- `rollback_available`

面试可说：

> 我不会让 Coding Agent 直接不可控地改文件。执行前会创建 CodeChangeSession，记录目标、允许文件、原始快照、patch 和验证结果。每次修改都以 patch 形式落地，失败时可以回滚到修改前状态，也可以把失败 patch 保留下来给用户审查。

## 六、Coding Agent 需要哪些工具

Coding Agent 的核心不是“模型会写代码”，而是它能通过工具闭环完成代码任务。

### 只读工具

- `list_files`
- `search_code`
- `read_file`
- `read_docs`
- `inspect_symbol`

### 写入工具

- `apply_patch`
- `create_test`
- `update_rule_pack`
- `update_solver_case`

### 验证工具

- `run_unit_tests`
- `run_build`
- `run_java_solver_tests`
- `run_frontend_typecheck`
- `run_solver_regression`
- `validate_rule_pack`

### 安全工具

- `create_change_snapshot`
- `check_allowed_paths`
- `show_diff`
- `rollback_change`

面试可说：

> Coding Agent 的工具层会分成读、写、验证和安全四类。读工具负责理解代码库，写工具负责以 patch 形式修改，验证工具负责编译、测试和求解器回归，安全工具负责权限检查和回滚。这样它不是简单生成代码文本，而是能完成可验证的代码变更任务。

## 七、Coding Agent 的闭环流程

推荐闭环：

```text
Plan
-> Guard
-> Patch
-> Verify
-> Critique
-> Repair
-> Finalize
```

解释：

- `Plan`：产出修改目标、影响范围、文件列表、验证计划
- `Guard`：检查文件是否在白区、灰区或红区
- `Patch`：生成并应用最小代码修改
- `Verify`：运行编译、测试、求解器回归
- `Critique`：解释失败原因或确认成功
- `Repair`：失败时有限轮自修复
- `Finalize`：输出 diff、验证结果和用户说明

面试可说：

> Coding Agent 的核心闭环是规划、权限检查、修改、验证、审查和修复。只有验证通过后才输出最终结果；如果验证失败，就把测试或编译错误反馈给 agent 继续修复。这样它具备规划、修改、验证和回滚能力，而不是单次生成代码。

## 八、和现有项目怎么对接

现有系统已经有一个预留节点：

```text
rule_refactor_agent
```

后续可以演进成：

```text
rule_design_agent
-> coding_agent
-> code_critic
-> controller
```

推荐职责：

- `rule_design_agent`：只做规则方案和影响分析
- `coding_agent`：真正修改代码
- `code_critic`：审查代码和验证结果
- `controller`：决定接受、重试或回滚

这样更清晰，不会把“设计方案”和“执行修改”混在一个 Agent 里。

面试可说：

> 现有的 `rule_refactor_agent` 可以作为未来 Coding Agent 分支的入口，但我会把它拆成设计和执行两层。规则设计 agent 负责分析新增机制和影响范围，Coding Agent 负责代码修改，Code Critic 负责验证和审查，Controller 负责是否接受或重试。

## 九、八股知识点：为什么不能让 Agent 直接改代码

回答：

> 因为代码修改是高风险动作，直接让模型生成并覆盖文件容易出现不可控问题，比如误删代码、改错模块、破坏兼容性、引入安全风险或者无法回滚。所以必须有权限边界、patch 化修改、验证闭环和回滚机制。Agent 写代码的关键不是生成能力，而是可控执行能力。

关键词：

- sandbox
- permission boundary
- patch-based editing
- rollback
- automated verification
- human confirmation

## 十、八股知识点：Coding Agent 和普通代码生成有什么区别

回答：

> 普通代码生成通常只是根据 prompt 输出一段代码，而 Coding Agent 是一个闭环系统。它会先理解需求和代码库，再生成修改计划，应用 patch，运行测试或编译，根据错误继续修复，最后输出通过验证的结果。区别在于 Coding Agent 具备工具调用、状态管理、自动验证和多轮修复能力。

关键词：

- codebase grounding
- tool calling
- planning
- test feedback loop
- self-repair

## 十一、八股知识点：为什么需要用户确认

回答：

> 新增规则或修改底层机制会影响现有规则包、求解器、前端编辑器和旧关卡兼容性。这类需求通常存在多种设计方案，不能让 Agent 默认选择并直接修改。因此我会先让它进入 proposal mode，输出影响分析和修改计划，用户确认后再进入 execution mode。这样可以把设计决策和代码执行分离。

关键词：

- human-in-the-loop
- proposal mode
- execution mode
- design approval

## 十二、八股知识点：如何验证 Coding Agent 的结果

回答：

> 验证应该分层进行。第一层是编译和类型检查，保证代码能运行；第二层是单元测试，验证局部逻辑；第三层是求解器回归，验证新增规则没有破坏现有关卡；第四层是端到端或手动验收，确认用户需求真的被满足。只有这些验证通过，Coding Agent 才能输出最终修改结果。

关键词：

- compile check
- unit test
- regression test
- solver regression
- acceptance criteria

## 十三、八股知识点：如果验证失败怎么办

回答：

> 验证失败后不应该直接把失败结果交给用户，而是把错误信息作为 observation 反馈给 Coding Agent，让它进入有限轮 repair。比如最多修复 2 到 3 轮。如果仍然失败，就回滚到修改前状态，或者把失败 patch 和错误原因作为 proposal 返回给用户。这样可以避免无限循环和不可控修改。

关键词：

- bounded retry
- error observation
- repair loop
- rollback
- failed proposal

## 十四、八股知识点：为什么适合你这个项目

回答：

> 这个项目天然适合加入 Coding Agent，因为它已经具备几个基础条件：第一，有明确的规则包和求解器接口；第二，有确定性验证工具，能判断修改是否可用；第三，有多 Agent 编排和 controller 机制；第四，已经预留了 rule_refactor 节点。也就是说，后续不是从零做 Coding Agent，而是在现有可验证 Agent 闭环上扩展一条代码修改分支。

关键词：

- existing tool layer
- deterministic verifier
- LangGraph orchestration
- reserved rule_refactor branch
- controlled extension

## 十五、30 秒总结版

如果面试官问“后续还能怎么改进”，可以这样答：

> 我后续想加入 Coding Agent，把系统从“Agent 辅助关卡生成”扩展到“Agent 辅助规则和求解器开发”。具体做法是把现有预留的 `rule_refactor_agent` 升级成条件分支：planner 先判断是否需要底层代码变更，如果需要，Coding Agent 先进入 proposal mode，分析代码结构、影响范围和验证计划，用户确认后才进入 execution mode。执行阶段会设置红区、白区和灰区权限边界，以 patch 形式修改代码，并运行编译、测试和求解器回归。如果失败，就有限轮修复或回滚。这样它不是单纯生成代码，而是具备规划、修改、验证和回滚能力的受控 Coding Agent。

## 十六、1 分钟展开版

> 未来我会把这个项目进一步扩展成能支持底层能力演进的 Agent 系统。现在 Agent 主要能在已有规则内改关卡，但如果用户提出新增游戏机制、修改求解器行为或扩展规则包，就需要代码层面的变更。所以我会在 planner 后面增加一个 coding branch，由 planner 判断是否是 rule extension，再路由到 Coding Agent。
>
> 这个 Coding Agent 不会直接写代码，而是分两阶段执行。第一阶段是 proposal mode，只读代码，分析影响范围、修改文件、兼容性风险和验证计划，等待用户确认。第二阶段才是 execution mode，它会基于红区、白区、灰区权限策略，以 patch 形式修改代码，然后运行编译、测试和求解器回归。如果验证失败，controller 会把错误反馈给它做有限轮修复；如果仍失败，就回滚或输出失败 proposal。
>
> 这样设计的核心是安全和可验证。Agent 写代码本身不难，难的是控制它改哪里、怎么验证、失败怎么恢复。所以我会把它做成一个带权限边界、自动验证和可回滚机制的 coding workflow，而不是一个直接输出代码文本的聊天机器人。

