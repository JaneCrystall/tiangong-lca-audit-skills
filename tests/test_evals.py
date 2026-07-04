import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "tests/evals/audit-evaluation-cases.json"


def test_eval_suite_covers_pass_and_fail_boundaries():
    payload = json.loads(EVALS.read_text(encoding="utf-8"))
    conclusions = {case["expectedConclusion"] for case in payload["cases"]}
    assert {"通过", "不通过"} <= conclusions


def test_failed_eval_cases_have_teaching_suggestions():
    payload = json.loads(EVALS.read_text(encoding="utf-8"))
    failed = [case for case in payload["cases"] if case["expectedConclusion"] == "不通过"]
    assert failed
    for case in failed:
        assert case["expectedIssuePoints"]
        assert all(point["shouldMentionSuggestion"] for point in case["expectedIssuePoints"])


def test_expected_issue_points_map_to_current_rules():
    payload = json.loads(EVALS.read_text(encoding="utf-8"))
    rule_ids = set()
    for path in (ROOT / "skill/tiangong-lca-audit/rules").glob("*.json"):
        rule_payload = json.loads(path.read_text(encoding="utf-8"))
        rule_ids.update(rule["id"] for rule in rule_payload["rules"])

    for case in payload["cases"]:
        for point in case.get("expectedIssuePoints", []):
            assert point["ruleId"] in rule_ids
