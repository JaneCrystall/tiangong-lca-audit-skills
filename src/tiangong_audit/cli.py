from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import logging
from uuid import uuid4

from tiangong_audit.normalizer import normalize_dataset
from tiangong_audit.process_pass_flow import (
    ModelPassWorkflow,
    ProcessPassFlowError,
    ProcessPassWorkflow,
)
from tiangong_audit.report.markdown import render_findings
from tiangong_audit.report.review_request import render_review_request
from tiangong_audit.rule_engine import run_deterministic_checks
from tiangong_audit.integrations import tiangong_api
from tiangong_audit.integrations.tidas_sdk import (
    TidasSdkValidationError,
    validate_enhanced,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CASE_SUBDIRS = ("intake", "snapshots", "findings", "reports", "corrections", "outputs")
REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    "skill/tiangong-lca-audit/SKILL.md",
    "skill/tiangong-lca-audit/agents/openai.yaml",
    "skill/tiangong-lca-audit/references/audit-policy.md",
    "skill/tiangong-lca-audit/references/input-contract.md",
    "skill/tiangong-lca-audit/references/process-audit.md",
    "skill/tiangong-lca-audit/references/model-audit.md",
    "skill/tiangong-lca-audit/references/output-contract.md",
    "skill/tiangong-lca-audit/references/correction-policy.md",
    "skill/tiangong-lca-audit/references/platform-operations.md",
    "skill/tiangong-lca-audit/references/taxonomy-guide.md",
    "skill/tiangong-lca-audit/rules/common.json",
    "skill/tiangong-lca-audit/rules/process.json",
    "skill/tiangong-lca-audit/rules/model.json",
    "skill/tiangong-lca-audit/assets/taxonomies/cfia-category-taxonomy.json",
    "skill/tiangong-lca-audit/assets/taxonomies/tiangong-category-paths.json",
    "skill/tiangong-lca-audit/assets/audit-result-template.md",
    "skill/tiangong-lca-audit/assets/approval-report-template.md",
    "skill/tiangong-lca-audit/assets/correction-record-template.md",
    "src/tiangong_audit/__init__.py",
    "src/tiangong_audit/normalizer/projected.py",
    "src/tiangong_audit/process_pass_flow.py",
    "src/tiangong_audit/rule_engine/engine.py",
    "src/tiangong_audit/report/markdown.py",
    "src/tiangong_audit/report/review_request.py",
    "tests/test_skill_contract.py",
    "tests/test_rules.py",
    "tests/test_content_hygiene.py",
    "tests/test_assets.py",
    "tests/test_evals.py",
    "tests/test_normalizer.py",
    "tests/test_process_pass_flow.py",
    "tests/test_rule_engine.py",
    "tests/test_cli.py",
    "docs/architecture.md",
    "docs/workflow.md",
    "docs/environment.md",
    "docs/tiangong-integration.md",
    "docs/asset-boundaries.md",
    "cases/.gitkeep",
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _validate_id(value: str) -> None:
    if not CASE_ID_PATTERN.match(value):
        raise SystemExit("Invalid case id. Use letters, numbers, dots, underscores, or hyphens.")


def _read_json(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_output(path: str | None, content: str) -> None:
    if not path or path == "-":
        sys.stdout.write(content)
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"Wrote: {target}")


def create_case(args: argparse.Namespace) -> int:
    _validate_id(args.case_id)
    case_dir = ROOT / "cases" / args.case_id
    if case_dir.exists() and not args.force:
        raise SystemExit(f"Case already exists: {case_dir}")

    for subdir in CASE_SUBDIRS:
        target = case_dir / subdir / "README.md"
        if args.force or not target.exists():
            _write_text(target, f"# {subdir}\n\n待补充。\n")

    readme = case_dir / "README.md"
    if args.force or not readme.exists():
        _write_text(
            readme,
            "# 审核案件\n\n"
            f"- 案件 ID：{args.case_id}\n"
            f"- 标题：{args.title}\n"
            f"- 创建日期：{args.created_at or date.today().isoformat()}\n"
            "- 状态：pending\n",
        )

    print(f"Created audit case workspace: {case_dir}")
    return 0


def check_workspace(_: argparse.Namespace) -> int:
    errors: list[str] = []
    for rel_path in REQUIRED_PATHS:
        if not (ROOT / rel_path).exists():
            errors.append(f"missing required path: {rel_path}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Tiangong LCA audit skill check passed.")
    return 0


def normalize_input(args: argparse.Namespace) -> int:
    try:
        normalized = normalize_dataset(_read_json(args.input))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Unable to normalize input: {error}") from error
    content = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    _write_output(args.output, content)
    return 0


def check_rules(args: argparse.Namespace) -> int:
    try:
        normalized = normalize_dataset(_read_json(args.input))
        result = run_deterministic_checks(normalized)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Unable to check rules: {error}") from error

    content = (
        render_findings(result)
        if args.format == "markdown"
        else json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    _write_output(args.output, content)
    return 1 if args.fail_on_blocking and result["summary"]["blocking"] else 0


def _has_validation_errors(result: dict) -> bool:
    if result.get("success") is False:
        return True
    return any(
        issue.get("severity") == "error"
        for issue in result.get("validationIssues", [])
        if isinstance(issue, dict)
    )


def validate_structure(args: argparse.Namespace) -> int:
    """Run schema-level validation through TIDAS SDK validateEnhanced()."""
    try:
        result = validate_enhanced(
            _read_json(args.input),
            entity_type=args.entity_type,
            mode=args.mode,
            include_warnings=args.include_warnings,
            timeout=args.timeout,
        )
    except (OSError, json.JSONDecodeError, TidasSdkValidationError) as error:
        print(f"ERROR: Unable to validate structure: {error}", file=sys.stderr)
        return 1

    _write_output(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 1 if args.fail_on_error and _has_validation_errors(result) else 0


def _get_current_user_id(client: tiangong_api.TiangongAPIClient) -> str:
    user = client._request("GET", "auth/v1/user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise tiangong_api.TiangongAuthError("Unable to resolve current platform user id")
    return str(user_id)


def process_pass_flow(args: argparse.Namespace) -> int:
    """Run the fixed process-dataset pass workflow."""
    try:
        client = tiangong_api.TiangongAPIClient(
            account_role=args.account_role,
            allow_writes=args.execute,
        )
        workflow = ProcessPassWorkflow(
            client=client,
            review_api=tiangong_api.ReviewAPI(client),
            dataset_api=tiangong_api.DatasetAPI(client),
            template_path=ROOT / "skill/tiangong-lca-audit/assets/approval-report-template.docx",
            current_user_id=_get_current_user_id(client),
            uuid_factory=lambda: str(uuid4()),
            today=date.today,
        )
        summary = workflow.execute(
            args.review_id,
            Path(args.output_dir),
            execute=args.execute,
        )
    except (OSError, json.JSONDecodeError, tiangong_api.TiangongAPIError, ProcessPassFlowError) as error:
        print(f"ERROR: Unable to run process pass flow: {error}", file=sys.stderr)
        return 1

    _write_output(getattr(args, "output", None), json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


def model_pass_flow(args: argparse.Namespace) -> int:
    """Run the fixed life-cycle-model pass workflow."""
    try:
        client = tiangong_api.TiangongAPIClient(
            account_role=args.account_role,
            allow_writes=args.execute,
        )
        workflow = ModelPassWorkflow(
            client=client,
            review_api=tiangong_api.ReviewAPI(client),
            dataset_api=tiangong_api.DatasetAPI(client),
            template_path=ROOT / "skill/tiangong-lca-audit/assets/approval-report-template.docx",
            current_user_id=_get_current_user_id(client),
            uuid_factory=lambda: str(uuid4()),
            today=date.today,
        )
        summary = workflow.execute(
            args.review_id,
            Path(args.output_dir),
            execute=args.execute,
        )
    except (OSError, json.JSONDecodeError, tiangong_api.TiangongAPIError, ProcessPassFlowError) as error:
        print(f"ERROR: Unable to run model pass flow: {error}", file=sys.stderr)
        return 1

    _write_output(getattr(args, "output", None), json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


def audit_bundle(args: argparse.Namespace) -> int:
    try:
        normalized = normalize_dataset(_read_json(args.input))
        result = run_deterministic_checks(normalized)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Unable to prepare audit: {error}") from error

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / "normalized.json"
    precheck_json_path = output_dir / "precheck.json"
    precheck_markdown_path = output_dir / "precheck.md"
    review_request_path = output_dir / "agent-review-request.md"

    normalized_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    precheck_json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    precheck_markdown_path.write_text(render_findings(result), encoding="utf-8")
    review_request_path.write_text(
        render_review_request(
            normalized_path.name,
            precheck_json_path.name,
            result,
        ),
        encoding="utf-8",
    )
    print(f"Audit bundle created: {output_dir}")
    print(f"Precheck conclusion: {result['conclusion']}")
    print(f"Next: run Agent semantic review using {review_request_path}")
    return 0


def fetch_tasks(args: argparse.Namespace) -> int:
    """Fetch a review queue from the platform."""
    try:
        account_role = getattr(args, "account_role", None) or args.role
        client = tiangong_api.TiangongAPIClient(account_role=account_role)
        review_api = tiangong_api.ReviewAPI(client)

        if args.role == "admin":
            response = review_api.get_admin_tasks(
                status=args.status or "unassigned",
                page=args.page,
                page_size=args.page_size,
            )
        else:
            response = review_api.get_member_tasks(
                status=args.status or "pending",
                page=args.page,
                page_size=args.page_size,
            )

        _write_output(
            args.output,
            json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        )
        return 0
    except tiangong_api.TiangongAPIError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def fetch_dataset(args: argparse.Namespace) -> int:
    """Fetch one process or lifecycle model from the platform."""
    try:
        client = tiangong_api.TiangongAPIClient(
            account_role=getattr(args, "account_role", None)
        )
        dataset_api = tiangong_api.DatasetAPI(client)
        if args.dataset_type == "auto":
            response = dataset_api.resolve_dataset(args.dataset_id, args.version)
        else:
            response = dataset_api.get_dataset(
                args.dataset_id,
                args.version,
                tiangong_api.DatasetType(args.dataset_type),
            )
        _write_output(
            args.output,
            json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        )
        return 0
    except tiangong_api.TiangongAPIError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def submit_result(args: argparse.Namespace) -> int:
    """Submit audit result to platform.

    IMPORTANT: This operation marks the task as completed.
    Ensure you have reviewed the findings before submitting.
    """
    try:
        # Load result from file
        result_data = _read_json(args.result)

        # Ask for confirmation
        if not args.force:
            print("\n" + "="*60)
            print("AUDIT RESULT SUBMISSION")
            print("="*60)
            print(f"Task ID: {result_data.get('review_task_id')}")
            print(f"Dataset ID: {result_data.get('dataset_id')}")
            print(f"Conclusion: {result_data.get('conclusion')}")
            print(f"Findings: {len(result_data.get('findings', []))}")
            print("="*60)

            confirm = input("\nSubmit this result to platform? (yes/no): ").lower()
            if confirm != "yes":
                print("Submission cancelled.")
                return 0

        # Convert to AuditResult model
        findings = [
            tiangong_api.AuditFinding(
                id=f.get("id", f"finding_{i}"),
                severity=tiangong_api.FindingSeverity(f["severity"]),
                title=f["title"],
                description=f["description"],
                evidence=f["evidence"],
                suggested_fix=f.get("suggested_fix"),
                related_field=f.get("related_field"),
                tags=f.get("tags", []),
            )
            for i, f in enumerate(result_data.get("findings", []))
        ]

        result = tiangong_api.AuditResult(
            review_task_id=result_data["review_task_id"],
            dataset_id=result_data["dataset_id"],
            conclusion=result_data["conclusion"],
            summary=result_data["summary"],
            findings=findings,
            auditor_notes=result_data.get("auditor_notes"),
        )

        # The write-capable client is created only after explicit confirmation.
        client = tiangong_api.TiangongAPIClient(
            account_role=getattr(args, "account_role", None),
            allow_writes=True,
        )
        review_api = tiangong_api.ReviewAPI(client)
        response = review_api.submit_result(result.review_task_id, result)

        print(f"✓ Audit result submitted successfully")
        print(f"  Task ID: {result.review_task_id}")
        print(f"  Conclusion: {result.conclusion}")

        if args.output:
            Path(args.output).write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"  Response saved to: {args.output}")

        return 0
    except tiangong_api.TiangongAPIError as e:
        print(f"ERROR: Failed to submit result: {e}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"ERROR: Invalid result format: {e}", file=sys.stderr)
        return 1


def list_actions(args: argparse.Namespace) -> int:
    """List platform operations that need to be executed based on audit result."""
    try:
        # Load audit result
        result_data = _read_json(args.result)

        # Convert to model
        findings = [
            tiangong_api.AuditFinding(
                id=f.get("id", f"finding_{i}"),
                severity=tiangong_api.FindingSeverity(f["severity"]),
                title=f["title"],
                description=f["description"],
                evidence=f["evidence"],
                suggested_fix=f.get("suggested_fix"),
                related_field=f.get("related_field"),
                tags=f.get("tags", []),
            )
            for i, f in enumerate(result_data.get("findings", []))
        ]

        result = tiangong_api.AuditResult(
            review_task_id=result_data["review_task_id"],
            dataset_id=result_data["dataset_id"],
            conclusion=result_data["conclusion"],
            summary=result_data["summary"],
            findings=findings,
            auditor_notes=result_data.get("auditor_notes"),
        )

        actions = tiangong_api.ReviewAPI.generate_platform_actions(result)

        # Format output
        output = {
            "task_id": result.review_task_id,
            "dataset_id": result.dataset_id,
            "conclusion": result.conclusion,
            "actions": [action.to_dict() for action in actions],
            "warnings": [
                "⚠️  Platform operations are for review only.",
                "⚠️  User must confirm before execution.",
                "⚠️  Operation failures do not affect audit findings.",
            ],
        }

        if args.format == "markdown":
            content = _format_actions_markdown(output)
            _write_output(args.output, content)
        else:
            _write_output(args.output, json.dumps(output, ensure_ascii=False, indent=2) + "\n")

        return 0
    except tiangong_api.TiangongAPIError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"ERROR: Invalid result format: {e}", file=sys.stderr)
        return 1


def _format_actions_markdown(output: dict) -> str:
    """Format platform actions as markdown."""
    lines = [
        "# Platform Operations",
        "",
        f"**Task ID:** {output['task_id']}",
        f"**Dataset ID:** {output['dataset_id']}",
        f"**Conclusion:** {output['conclusion']}",
        "",
        "## Pending Actions",
        "",
    ]

    for i, action in enumerate(output["actions"], 1):
        lines.append(f"### Action {i}: {action['action_type']}")
        lines.append(f"- **Target:** {action['target_id']}")
        if action["description"]:
            lines.append(f"- **Description:** {action['description']}")
        if action["parameters"]:
            lines.append("- **Parameters:**")
            for key, value in action["parameters"].items():
                lines.append(f"  - `{key}`: {json.dumps(value)}")
        lines.append("")

    lines.append("## Warnings")
    lines.append("")
    for warning in output["warnings"]:
        lines.append(f"- {warning}")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiangong-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-case", help="Create an audit case workspace")
    create_parser.add_argument("case_id")
    create_parser.add_argument("--title", default="未命名审核对象")
    create_parser.add_argument("--created-at")
    create_parser.add_argument("--force", action="store_true")
    create_parser.set_defaults(func=create_case)

    check_parser = subparsers.add_parser("check", help="Check workspace conventions")
    check_parser.set_defaults(func=check_workspace)

    lint_parser = subparsers.add_parser("lint", help="Alias for check")
    lint_parser.set_defaults(func=check_workspace)

    normalize_parser = subparsers.add_parser(
        "normalize", help="Normalize projected Tiangong process JSON"
    )
    normalize_parser.add_argument("--input", required=True, help="Input JSON path or - for stdin")
    normalize_parser.add_argument("--output", help="Output JSON path; defaults to stdout")
    normalize_parser.set_defaults(func=normalize_input)

    rules_parser = subparsers.add_parser(
        "check-rules", help="Run conservative deterministic checks on a process dataset"
    )
    rules_parser.add_argument("--input", required=True, help="Projected or normalized JSON path")
    rules_parser.add_argument("--output", help="Output path; defaults to stdout")
    rules_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    rules_parser.add_argument("--fail-on-blocking", action="store_true")
    rules_parser.set_defaults(func=check_rules)

    structure_parser = subparsers.add_parser(
        "validate-structure",
        help="Run TIDAS SDK validateEnhanced() schema validation",
    )
    structure_parser.add_argument("--input", required=True, help="TIDAS JSON path or - for stdin")
    structure_parser.add_argument("--output", help="Output JSON path; defaults to stdout")
    structure_parser.add_argument(
        "--entity-type",
        choices=(
            "process",
            "model",
            "lifeCycleModel",
            "contact",
            "flow",
            "source",
            "flowProperty",
            "unitGroup",
            "lciaMethod",
        ),
        default="process",
        help="TIDAS entity type; model is accepted as an alias for lifeCycleModel",
    )
    structure_parser.add_argument(
        "--mode",
        choices=("strict", "weak", "ignore"),
        default="strict",
        help="TIDAS SDK validation mode",
    )
    structure_parser.add_argument(
        "--include-warnings",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include SDK warnings in enhanced validation output",
    )
    structure_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Node SDK validation timeout in seconds",
    )
    structure_parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return non-zero when SDK validation reports errors",
    )
    structure_parser.set_defaults(func=validate_structure)

    pass_parser = subparsers.add_parser(
        "process-pass-flow",
        help="Create review report source and save process validation review draft",
    )
    pass_parser.add_argument("--review-id", required=True, help="Assigned review task id")
    pass_parser.add_argument(
        "--output-dir",
        required=True,
        help="Local evidence directory for generated payloads and readback snapshots",
    )
    pass_parser.add_argument("--output", help="Summary JSON path; defaults to stdout")
    pass_parser.add_argument(
        "--account-role",
        choices=("member",),
        default="member",
        help="Reviewer account role (default: member)",
    )
    pass_parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform writes. Without this flag the command prepares payloads only.",
    )
    pass_parser.set_defaults(func=process_pass_flow)

    model_pass_parser = subparsers.add_parser(
        "model-pass-flow",
        help="Create review report source and save life-cycle-model validation review draft",
    )
    model_pass_parser.add_argument("--review-id", required=True, help="Assigned review task id")
    model_pass_parser.add_argument(
        "--output-dir",
        required=True,
        help="Local evidence directory for generated payloads and readback snapshots",
    )
    model_pass_parser.add_argument("--output", help="Summary JSON path; defaults to stdout")
    model_pass_parser.add_argument(
        "--account-role",
        choices=("member",),
        default="member",
        help="Reviewer account role (default: member)",
    )
    model_pass_parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform writes. Without this flag the command prepares payloads only.",
    )
    model_pass_parser.set_defaults(func=model_pass_flow)

    audit_parser = subparsers.add_parser(
        "audit", help="Create a normalized audit bundle and run deterministic prechecks"
    )
    audit_parser.add_argument("--input", required=True, help="Projected or normalized JSON path")
    audit_parser.add_argument("--output-dir", required=True, help="Directory for the audit bundle")
    audit_parser.set_defaults(func=audit_bundle)

    # Platform integration commands
    fetch_parser = subparsers.add_parser("fetch-tasks", help="Fetch a platform review queue")
    fetch_parser.add_argument(
        "--role",
        choices=("admin", "member"),
        default="admin",
        help="Queue role: admin or member (default: admin)",
    )
    fetch_parser.add_argument(
        "--account-role",
        choices=("admin", "member"),
        help="Login account role; defaults to the selected queue role",
    )
    fetch_parser.add_argument(
        "--status",
        help="Queue status; defaults to unassigned for admin and pending for member",
    )
    fetch_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    fetch_parser.add_argument(
        "--page-size",
        type=int,
        default=10,
        help="Tasks per page (default: 10)",
    )
    fetch_parser.add_argument(
        "--output",
        help="Output JSON path; defaults to stdout"
    )
    fetch_parser.set_defaults(func=fetch_tasks)

    dataset_parser = subparsers.add_parser(
        "fetch-dataset", help="Fetch one process or lifecycle model from platform"
    )
    dataset_parser.add_argument("--dataset-id", required=True)
    dataset_parser.add_argument("--version", required=True)
    dataset_parser.add_argument(
        "--dataset-type",
        choices=("auto", "process", "model"),
        default="auto",
        help="Dataset type; defaults to automatic detection",
    )
    dataset_parser.add_argument(
        "--account-role",
        choices=("admin", "member"),
        help="Login account role; defaults to TIANGONG_ACTIVE_ACCOUNT or legacy credentials",
    )
    dataset_parser.add_argument("--output", help="Output JSON path; defaults to stdout")
    dataset_parser.set_defaults(func=fetch_dataset)

    submit_parser = subparsers.add_parser(
        "submit-result",
        help="Submit audit result to platform (REQUIRES CONFIRMATION)"
    )
    submit_parser.add_argument(
        "--result",
        required=True,
        help="Path to audit result JSON file or - for stdin"
    )
    submit_parser.add_argument(
        "--output",
        help="Output path for API response"
    )
    submit_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt"
    )
    submit_parser.add_argument(
        "--account-role",
        choices=("admin", "member"),
        default="member",
        help="Login account role for submitting the review result (default: member)",
    )
    submit_parser.set_defaults(func=submit_result)

    actions_parser = subparsers.add_parser(
        "list-actions",
        help="List platform operations needed for audit result (no execution)"
    )
    actions_parser.add_argument(
        "--result",
        required=True,
        help="Path to audit result JSON file or - for stdin"
    )
    actions_parser.add_argument(
        "--output",
        help="Output path; defaults to stdout"
    )
    actions_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format (default: json)"
    )
    actions_parser.set_defaults(func=list_actions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
