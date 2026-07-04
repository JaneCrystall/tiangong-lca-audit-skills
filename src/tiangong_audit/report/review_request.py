from __future__ import annotations

from typing import Any


def render_review_request(normalized_path: str, precheck_path: str, result: dict[str, Any]) -> str:
    identity = result["dataset"]
    name = identity["name"].get("zh") or identity["name"].get("en") or identity["name"].get("raw")
    semantic_review = result.get("semantic_review", {})
    required_rule_ids = semantic_review.get("required_rule_ids") or []
    semantic_lines = "\n".join(f"- `{rule_id}`" for rule_id in required_rule_ids)
    if not semantic_lines:
        semantic_lines = "- 按 `skill/tiangong-lca-audit/SKILL.md` 和 `rules/*.json` 完成核心语义审核。"
    return f"""# Agent 语义审核任务

- 数据集类型：{result["dataset_type"]}
- 数据集名称：{name or "未识别"}
- 数据集 ID / 版本：{identity.get("id") or "-"} / {identity.get("version") or "-"}
- 程序预检结论：{result["conclusion"]}

## 输入

- 标准化数据：`{normalized_path}`
- 程序预检发现：`{precheck_path}`

## 执行要求

使用 `skill/tiangong-lca-audit/SKILL.md` 完成语义审核：

1. 读取标准化数据和程序预检发现。
2. 最终审核意见必须合并程序预检中已经成立的问题；可以合并同类问题或补充证据，但不得因为问题已出现在预检中就在最终退回意见中省略。
3. 重点审核程序不能可靠判断的对象、边界、分类合理性、关键流完整性、来源代表性和跨窗口关系。
4. 按 `skill/tiangong-lca-audit/references/audit-policy.md` 聚合完整审核结论。
5. 按 `skill/tiangong-lca-audit/references/output-contract.md` 输出最终审核结果，分为证据型报告和平台退回意见两层。

## 必须语义复核的核心规则

{semantic_lines}

## 语义复核动作清单

- 对象一致性：逐项对比基本名称、处理、标准、路线、一般性说明、技术描述和核心输出；同一数值和单位若对应不同规格对象，必须核查是否造成对象或规格误导。
- 数据集类型与边界：核查数据集类型是否有边界和聚合层级证据支撑；多个前景操作聚合时，不得仅因字段填写为单一操作而默认可信。
- 边界与输入输出：核查一般性说明中的包含/排除活动是否与输入输出冲突；若说明排除上游生产负荷，但输入为生产混合、市场混合或链接上游背景过程的产品流，必须合并为边界一致性问题。
- 截断和完整性：核查数据切断和完整性原则是否包含定量截断标准、覆盖率、排除活动和跨系统边界流；不能只因来源未列出就默认制造能耗或辅助材料可截断。
- 功能单位或基准流：核查参考输出数量、单位、年产量或参考产量与技术描述中的总质量、单件质量或关键物料投入量是否闭合；必要时要求补充量值参考或定量产品属性。
- 流语义和分类：在底层流类型、参考属性、参考单位或分类路径可见时，核查其是否与流名称、材料属性、用途和技术描述一致；分类判断应保留候选依据，分类类平台意见必须写出候选分类路径或候选范围，无法确认唯一候选时写明核实条件。
- 来源归属：区分来源项目背景、来源参数、LCIA 结果和当前数据集自身建模内容；不得把来源研究背景直接当作当前数据集边界。

程序预检不是最终审核结论。最终结论必须由 Agent 语义审核和人工确认共同形成。
"""
