# 审查报告草稿

正式通过报告使用同目录的 `approval-report-template.docx` 作为固定格式模板。
该 Markdown 只说明替换规则，不作为另一份报告正文来源。

## 使用规则

复制 `approval-report-template.docx` 生成每条通过数据的独立审查报告。模板使用稳定占位符，避免直接匹配 Word XML 中被分段的真实文本。除下列占位符外，不改写模板中的固定声明、合规表格、审查员信息和签字占位：

- `{{DATASET_NAME}}`：数据集名称。
- `{{DATASET_UUID_VERSION}}`：数据集 UUID 和版本号。
- `{{DATASET_LOCATION}}`：数据集位置，例如永久 URI、URL、联系点或数据库名称和版本。
- `{{REVIEW_METHOD_SCOPE}}`：审查方法及范围。
- `{{REVIEW_COMPLETION_DATE}}`：审查完成日期。

## 字段来源

- 数据集名称：使用平台数据集名称的中英文组合。
- 数据集 UUID 和版本号：使用当前审核任务的 `data_id` 和 `data_version`，写作 `{UUID}_{版本号}`。
- 数据集位置：使用数据集永久 URI；过程数据集形如 `https://lcdn.tiangong.earth/datasetdetail/process.xhtml?uuid={UUID}&version={版本号}`。
- 审查方法及范围：范围名称取“建模信息-数据集类型”，平台原始字段通常为 `modellingAndValidation.LCIMethodAndAllocation.typeOfDataSet`；写入报告时使用中文名称，例如 `Unit process, single operation` 写作 `单元过程，单一操作`，方法名称写作 `质量平衡`。
- 审查完成日期：使用执行报告生成当天日期，格式沿用模板，例如 `2026年6月23日 23/6/2026`。

本草稿不代表已完成平台提交或正式签字。
