# Tiangong Integration

## 当前实现

平台使用 Supabase，而不是统一的 `/api/reviews` REST 接口。Runtime 中的实现位于：

- `src/tiangong_audit/integrations/tiangong_api/client.py`：认证、RPC、表读取和写保护。
- `src/tiangong_audit/integrations/tiangong_api/reviews.py`：管理员和审核员任务队列。
- `src/tiangong_audit/integrations/tiangong_api/datasets.py`：过程、模型详情和类型自动识别。

已验证的只读接口：

| 用途 | Supabase 接口 |
| --- | --- |
| 管理员任务队列 | `qry_review_get_admin_queue_items` |
| 审核员任务队列 | `qry_review_get_member_queue_items` |
| 单条审核任务 | `qry_review_get_items` |
| 过程详情 | `processes` |
| 模型详情 | `lifecyclemodels` |

## TIDAS SDK 结构校验

结构/schema 级校验通过官方 TypeScript SDK 完成，不在本仓库复制 schema 规则。首次使用前在仓库根目录安装 Node 依赖：

```bash
npm install
```

校验过程数据：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli validate-structure \
  --input cases/platform-dataset.json \
  --entity-type process \
  --mode strict \
  --fail-on-error \
  --output cases/structure-validation.json
```

模型数据使用 `--entity-type model`。该值会映射到 SDK 的 `lifeCycleModel` 实体类型。

命令会调用 `@tiangong-lca/tidas-sdk/core` 的 `createTidasEntity(...).validateEnhanced()`，输出 SDK 返回的 `success`、`validationIssues`、`warnings` 和必要的错误信息。加上 `--fail-on-error` 后，只要 SDK 返回 `success: false` 或错误级 `validationIssues`，命令就返回非零状态码，便于接入 CI 或审核流水线。

## 最简单的试用步骤

1. 复制 `.env.example` 为本地 `.env`，填写平台地址、公开 key、主账号
   `TIANGONG_ADMIN_*` 和副账号 `TIANGONG_MEMBER_*`。如果要使用网页里复制出来的
   临时通行证，分别填写 `TIANGONG_ADMIN_ACCESS_TOKEN` 或
   `TIANGONG_MEMBER_ACCESS_TOKEN`。
2. 保持 `TIANGONG_API_ALLOW_WRITES=false`。
3. 拉取管理员待分配任务：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-tasks \
  --role admin \
  --status unassigned \
  --output cases/platform-tasks.json
```

4. 拉取副账号待二审任务：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-tasks \
  --role member \
  --status pending \
  --output cases/platform-member-tasks.json
```

5. 从任务结果中找到 `data_id` 和 `data_version`，自动识别并拉取数据集。读取副账号
   被分配任务时，显式指定 `--account-role member`：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-dataset \
  --dataset-id "<data_id>" \
  --version "<data_version>" \
  --account-role member \
  --output cases/platform-dataset.json
```

命令中的 `--role` 表示读取哪类队列，`--account-role` 表示使用哪个登录账号。读取队列
时二者默认一致；读取单个数据集或提交审核结果时，建议按任务所属账号显式传入
`--account-role admin` 或 `--account-role member`。

## 过程数据通过流程命令

已人工确认为通过的过程数据，使用固定命令生成完整审查报告、创建本次来源数据集并暂存验证审查。默认不写平台，只在本地 `cases/` 生成 DOCX、source payload、comment payload 和摘要：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli process-pass-flow \
  --review-id "<review_id>" \
  --output-dir cases/process-pass/<case-id>
```

确认 payload 无误后，增加 `--execute` 才会执行真实写入：

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli process-pass-flow \
  --review-id "<review_id>" \
  --output-dir cases/process-pass/<case-id> \
  --execute
```

该命令只会上传 `external_docs/{uuid}.docx`、调用 `app_dataset_create` 创建 `sources`、调用 `app_review_save_comment_draft` 暂存评论，并随后读回 `comments` 和 `sources` 验收。它不会调用 `app_review_submit_comment`，不会把 member 待审核任务移入已审核队列。

真实平台响应包含姓名、邮箱和未公开数据集信息，只能保存在 `cases/`，不得提交。

## 接入阶段

1. 离线辅助：复制或导出数据，使用 skill 生成审核意见。
2. 半自动：通过 API 拉取待审核任务，人工确认后提交。
3. 平台内嵌：在审核页增加 AI 辅助审核面板。
4. 自动编排：人工确认后，由工具调用 API 执行分配、提交、通过或驳回。

当前只读拉取框架已实现。写操作默认禁用；即使代码支持保存草稿或提交意见，也必须在
人工确认后临时启用，不得默认执行分配、通过或驳回。

## 已知天工平台接入点

以下路径位于上游天工平台前端仓库，不属于本仓库：

- 审核管理页：`src/pages/Review`
- 管理员分配、通过、驳回：`src/services/reviews/api.ts`
- 审核员保存草稿、提交意见：`src/services/comments/api.ts`
- 过程必填字段：`src/pages/Processes/requiredFields.ts`
- 模型必填字段：`src/pages/LifeCycleModels/requiredFields.ts`
