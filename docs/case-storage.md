# Case Storage

## Representation Decision

- Entity: 审核案件归档
- Product role: 本地审核证据、报告和平台操作记录
- Primary consumers: 审核 Agent、人工复核者、回归评测维护者
- Truth status: 报告是人工复核材料；平台操作记录是审计日志
- Recommended freedom level: F2 半结构化投影
- Recommended representation: 稳定清单文件 + Markdown 报告 + 压缩原始快照

## 推荐目录

```text
cases/
  index.jsonl
  active/
    <batch-id>/
      manifest.json
      reports/<review-id>.md
      evidence/<review-id>.md
      snapshots/<review-id>/{task.json,dataset.json.gz,linked.json.gz}
      operations/<review-id>.jsonl
  archive/
    YYYY/MM/<batch-id>/
```

## 原则

- 根目录只保留 `index.jsonl`、`active/` 和 `archive/`，不再平铺批次文件。
- 使用审核任务 ID 作为稳定文件名，不使用 `01-dataset` 等仅在当前批次有效的序号。
- `manifest.json` 保存批次统计和任务映射；`index.jsonl` 每条任务一行，支持 `rg`、脚本和后续 UI 检索。
- 报告与证据保留可读 Markdown；体积较大的原始数据集和关联数据使用 gzip 压缩。
- 平台分配、提交、通过、驳回等写操作追加到 `operations/<review-id>.jsonl`，不覆盖历史。
- 审核完成且平台操作结束后，将整个批次从 `active/` 移入按年月组织的 `archive/`。

## 建议索引字段

```json
{
  "review_id": "uuid",
  "dataset_id": "uuid",
  "version": "01.01.000",
  "dataset_type": "process",
  "name_zh": "数据集名称",
  "conclusion": "pass",
  "platform_state": "assigned",
  "batch_id": "batch-id",
  "report": "archive/2026/06/batch-id/reports/uuid.md"
}
```

## 迁移策略

先让新批次使用该结构。旧案件保持原位并在 `index.jsonl` 中登记；确认引用和脚本均兼容后，再按批次渐进迁移，避免一次性搬动破坏历史链接。
