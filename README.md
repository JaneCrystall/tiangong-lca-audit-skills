# Tiangong LCA Audit Skill

面向天工平台过程与模型数据集审核的自有 Skill。它把审核经验组织为一条可复核的决策链：

```text
输入充分性 → 证据 → 规则 → 发现 → 严重程度 → 结论 → 平台动作 → 纠偏
```

## 仓库分层

```text
skill/      可独立分发的审核能力
src/        平台 API、规则引擎和报告服务
tests/      Skill 合约、规则结构和回归案例
docs/       维护者文档
cases/      本地真实案件，默认不提交
```

`skill/tiangong-lca-audit/` 只保留审核运行时真正需要的内容：

- `SKILL.md`：唯一操作规程。
- `references/`：按任务读取的审核方法和政策。
- `rules/`：唯一机器可读规则源。
- `assets/`：审核输出模板与按需检索的分类数据。

历史审核意见只保留在 `tests/evals/` 用于回归，不作为运行时规则直接加载。

## 常用命令

```bash
PYTHONPATH=src python3 -m tiangong_audit.cli check
npm install
PYTHONPATH=src python3 -m tiangong_audit.cli create-case <case-id> --title "<审核对象>"

# 将天工 API 投影 JSON 标准化
PYTHONPATH=src python3 -m tiangong_audit.cli normalize \
  --input process.json \
  --output normalized.json

# 执行保守的确定性规则预检
PYTHONPATH=src python3 -m tiangong_audit.cli check-rules \
  --input normalized.json \
  --format markdown \
  --output findings.md

# 调用 TIDAS SDK validateEnhanced() 执行结构/schema 级校验
PYTHONPATH=src python3 -m tiangong_audit.cli validate-structure \
  --input process.json \
  --entity-type process \
  --mode strict \
  --fail-on-error \
  --output structure-validation.json

# 一条命令生成审核任务包
PYTHONPATH=src python3 -m tiangong_audit.cli audit \
  --input process.json \
  --output-dir cases/process-001/intake/audit-bundle

# 从平台读取管理员待分配任务
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-tasks \
  --role admin \
  --status unassigned \
  --output cases/platform-tasks.json

# 从平台读取副账号待二审任务
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-tasks \
  --role member \
  --status pending \
  --output cases/platform-member-tasks.json

# 按任务中的 data_id 和 data_version 自动读取过程或模型
PYTHONPATH=src python3 -m tiangong_audit.cli fetch-dataset \
  --dataset-id "<data_id>" \
  --version "<data_version>" \
  --account-role member \
  --output cases/platform-dataset.json

# 过程数据通过流程：先 dry-run 生成报告、source 和评论 payload
PYTHONPATH=src python3 -m tiangong_audit.cli process-pass-flow \
  --review-id "<review_id>" \
  --output-dir cases/process-pass/<case-id>

# 确认无误后执行真实写入：上传 DOCX、创建 source、暂存评论，不提交审核意见
PYTHONPATH=src python3 -m tiangong_audit.cli process-pass-flow \
  --review-id "<review_id>" \
  --output-dir cases/process-pass/<case-id> \
  --execute
```

## 当前能力边界

- 可以用 Skill 对已提供的过程或模型数据进行人工辅助审核。
- 可以生成结构化审核意见、通过报告草稿和纠偏记录。
- 可以通过命令标准化过程数据，并执行第一批保守的确定性规则预检。
- 可以通过 `audit` 一次生成标准化数据、预检结果和 Agent 语义审核任务。
- 可以通过 Supabase API 只读拉取审核任务，并自动识别和读取过程或模型数据。
- 可以通过 TIDAS TypeScript SDK 的 `validateEnhanced()` 执行结构/schema 级校验。
- 可以用 `process-pass-flow` 对已通过的过程数据执行固定通过流程：生成 DOCX、创建来源、暂存验证审查并读回验收。
- 尚未实现 Agent 语义审核编排；平台写操作默认禁用且不得自动提交。

架构和资产准入规则见 `docs/architecture.md` 与 `docs/asset-boundaries.md`。
