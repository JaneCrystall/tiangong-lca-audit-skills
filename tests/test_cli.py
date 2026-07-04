from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

from tiangong_audit.cli import (
    audit_bundle,
    fetch_dataset,
    fetch_tasks,
    list_actions,
    process_pass_flow,
    validate_structure,
)

ROOT = Path(__file__).resolve().parents[1]


def test_audit_command_creates_review_bundle():
    with TemporaryDirectory() as temporary:
        output_dir = Path(temporary) / "audit"
        args = Namespace(
            input=str(ROOT / "tests/fixtures/projected-api/process-audit-input-noapproved-projected.json"),
            output_dir=str(output_dir),
        )
        assert audit_bundle(args) == 0
        assert {
            "normalized.json",
            "precheck.json",
            "precheck.md",
            "agent-review-request.md",
        } == {path.name for path in output_dir.iterdir()}
        request = (output_dir / "agent-review-request.md").read_text(encoding="utf-8")
        assert "程序预检不是最终审核结论" in request
        assert "最终审核意见必须合并程序预检中已经成立的问题" in request
        assert "不得因为问题已出现在预检中就在最终退回意见中省略" in request
        assert "process.object.consistency" in request
        assert "process.type.boundary_match" in request
        assert "process.boundary.cutoff_and_exclusions" in request
        assert "process.classification.process_fit" in request
        assert "处理、标准、路线" in request
        assert "上游背景过程" in request
        assert "总质量" in request
        assert "候选分类路径或候选范围" in request
        assert "核实条件" in request


def test_fetch_tasks_selects_admin_queue(monkeypatch, capsys):
    class FakeReviewAPI:
        def __init__(self, client):
            pass

        def get_admin_tasks(self, **kwargs):
            assert kwargs == {"status": "unassigned", "page": 1, "page_size": 10}
            return {"items": [], "total": 0, "page": 1, "page_size": 10}

    monkeypatch.setattr(
        "tiangong_audit.cli.tiangong_api.TiangongAPIClient",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.ReviewAPI", FakeReviewAPI)

    args = Namespace(
        role="admin",
        status="unassigned",
        page=1,
        page_size=10,
        output=None,
    )
    assert fetch_tasks(args) == 0
    assert '"total": 0' in capsys.readouterr().out


def test_fetch_tasks_uses_member_account_for_member_queue(monkeypatch, capsys):
    class FakeReviewAPI:
        def __init__(self, client):
            assert client == "member-client"

        def get_member_tasks(self, **kwargs):
            assert kwargs == {"status": "pending", "page": 1, "page_size": 10}
            return {"items": [], "total": 0, "page": 1, "page_size": 10}

    def fake_client(*, account_role=None):
        assert account_role == "member"
        return "member-client"

    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.TiangongAPIClient", fake_client)
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.ReviewAPI", FakeReviewAPI)

    args = Namespace(
        role="member",
        account_role=None,
        status=None,
        page=1,
        page_size=10,
        output=None,
    )
    assert fetch_tasks(args) == 0
    assert '"total": 0' in capsys.readouterr().out


def test_fetch_dataset_uses_explicit_account_role(monkeypatch, capsys):
    class FakeDatasetAPI:
        def __init__(self, client):
            assert client == "member-client"

        def resolve_dataset(self, dataset_id, version):
            return {"dataset_type": "process", "data": {"id": dataset_id, "version": version}}

    def fake_client(*, account_role=None):
        assert account_role == "member"
        return "member-client"

    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.TiangongAPIClient", fake_client)
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.DatasetAPI", FakeDatasetAPI)

    args = Namespace(
        dataset_id="dataset-1",
        version="01.01.000",
        dataset_type="auto",
        account_role="member",
        output=None,
    )
    assert fetch_dataset(args) == 0
    assert '"dataset_type": "process"' in capsys.readouterr().out


def test_fetch_dataset_reads_requested_type(monkeypatch, capsys):
    class FakeDatasetAPI:
        def __init__(self, client):
            pass

        def get_dataset(self, dataset_id, version, dataset_type):
            assert dataset_id == "dataset-1"
            assert version == "01.01.000"
            assert dataset_type.value == "process"
            return {"id": dataset_id, "version": version}

    monkeypatch.setattr(
        "tiangong_audit.cli.tiangong_api.TiangongAPIClient",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.DatasetAPI", FakeDatasetAPI)

    args = Namespace(
        dataset_id="dataset-1",
        version="01.01.000",
        dataset_type="process",
        output=None,
    )
    assert fetch_dataset(args) == 0
    assert '"id": "dataset-1"' in capsys.readouterr().out


def test_fetch_dataset_auto_resolves_type(monkeypatch, capsys):
    class FakeDatasetAPI:
        def __init__(self, client):
            pass

        def resolve_dataset(self, dataset_id, version):
            return {"dataset_type": "model", "data": {"id": dataset_id, "version": version}}

    monkeypatch.setattr(
        "tiangong_audit.cli.tiangong_api.TiangongAPIClient",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.DatasetAPI", FakeDatasetAPI)

    args = Namespace(
        dataset_id="dataset-1",
        version="01.01.000",
        dataset_type="auto",
        output=None,
    )
    assert fetch_dataset(args) == 0
    assert '"dataset_type": "model"' in capsys.readouterr().out


def test_list_actions_does_not_require_platform_credentials(tmp_path, monkeypatch, capsys):
    for name in (
        "TIANGONG_SUPABASE_URL",
        "TIANGONG_SUPABASE_ANON_KEY",
        "TIANGONG_SUPABASE_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    result_path = tmp_path / "result.json"
    result_path.write_text(
        '{"review_task_id":"review-1","dataset_id":"dataset-1",'
        '"conclusion":"manual_review","summary":"Needs review","findings":[]}',
        encoding="utf-8",
    )

    args = Namespace(result=str(result_path), output=None, format="json")

    assert list_actions(args) == 0
    assert '"action_type": "submit_review_comment"' in capsys.readouterr().out


def test_validate_structure_writes_tidas_enhanced_result(tmp_path, monkeypatch, capsys):
    input_path = tmp_path / "dataset.json"
    input_path.write_text('{"processDataSet": {"processInformation": {}}}', encoding="utf-8")

    def fake_validate(payload, *, entity_type, mode, include_warnings, timeout):
        assert payload == {"processDataSet": {"processInformation": {}}}
        assert entity_type == "process"
        assert mode == "weak"
        assert include_warnings is True
        assert timeout == 15
        return {
            "success": False,
            "mode": "weak",
            "validationIssues": [{"code": "required_missing", "path": ["name"]}],
        }

    monkeypatch.setattr("tiangong_audit.cli.validate_enhanced", fake_validate)

    args = Namespace(
        input=str(input_path),
        output=None,
        entity_type="process",
        mode="weak",
        include_warnings=True,
        timeout=15,
        fail_on_error=True,
    )

    assert validate_structure(args) == 1
    output = capsys.readouterr().out
    assert '"success": false' in output
    assert '"required_missing"' in output


def test_process_pass_flow_cli_runs_workflow(monkeypatch, tmp_path, capsys):
    calls = {}

    class FakeWorkflow:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def execute(self, review_id, output_dir, *, execute):
            calls["execute"] = {
                "review_id": review_id,
                "output_dir": output_dir,
                "execute": execute,
            }
            return {
                "task_id": review_id,
                "source_id": "source-1",
                "comment_state_code": 0,
            }

    monkeypatch.setattr("tiangong_audit.cli.ProcessPassWorkflow", FakeWorkflow)
    monkeypatch.setattr(
        "tiangong_audit.cli.tiangong_api.TiangongAPIClient",
        lambda **kwargs: "member-client",
    )
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.ReviewAPI", lambda client: "review-api")
    monkeypatch.setattr("tiangong_audit.cli.tiangong_api.DatasetAPI", lambda client: "dataset-api")
    monkeypatch.setattr("tiangong_audit.cli._get_current_user_id", lambda client: "reviewer-1")

    args = Namespace(
        review_id="review-1",
        output_dir=str(tmp_path),
        account_role="member",
        execute=True,
    )

    assert process_pass_flow(args) == 0
    assert calls["init"]["client"] == "member-client"
    assert calls["init"]["review_api"] == "review-api"
    assert calls["init"]["dataset_api"] == "dataset-api"
    assert calls["init"]["current_user_id"] == "reviewer-1"
    assert calls["execute"] == {
        "review_id": "review-1",
        "output_dir": tmp_path,
        "execute": True,
    }
    assert '"source_id": "source-1"' in capsys.readouterr().out
