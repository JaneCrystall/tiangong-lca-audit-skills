# Architecture

## 决策模型

本项目围绕统一审核对象设计：

```text
AuditInput
  → Evidence
  → RuleApplication
  → Finding
  → Conclusion
  → PlatformAction
  → Correction
```

- `AuditInput`：平台数据、模型结构、截图或用户描述。
- `Evidence`：可指回具体字段、交换或节点的事实。
- `RuleApplication`：确定性规则或需要专业判断的审核方法。
- `Finding`：阻断、建议、人工确认或信息缺口。
- `Conclusion`：通过、不通过、信息不足或需人工确认。
- `PlatformAction`：结论确认后的独立操作。
- `Correction`：人工修正及其规则或评测沉淀。

## 分层

### Skill 产品层

`skill/tiangong-lca-audit/` 必须自足：

- `SKILL.md` 保存唯一执行流程。
- `references/` 保存按需加载的审核方法。
- `rules/` 保存唯一机器可读规则源。
- `assets/` 保存输出模板和大型查询数据。

Skill 不保存来源材料、开发文档、测试或占位代码。

### Runtime 工程层

`src/tiangong_audit/` 用于实现 API 输入、标准化、规则执行和报告渲染。Runtime 可以读取 Skill 规则，但不能重新定义审核政策。

当前 Runtime 已提供：

- `normalize`：将天工过程投影 JSON 转换为 `tiangong-audit-normalized-v1`。
- `check-rules`：执行保守的确定性预检并输出 JSON 或 Markdown。
- `audit`：生成标准化数据、预检结果和 Agent 语义审核任务包。

预检只执行证据充分的保守规则。当前投影数据未稳定提供交换参考单位，因此 Runtime 不自动进行跨单位数量守恒判断。

下一阶段将在标准化数据和预检结果之上编排 Agent 语义审核。

### 验证层

`tests/` 验证：

- Skill 资源导航没有断链。
- 结构化规则满足统一 schema。
- Skill 不重新积累来源型材料和重复摘要。
- 真实纠偏能通过脱敏回归案例复现。

### 案件层

`cases/` 保存本地案件证据、发现、报告和纠偏，默认不提交。
