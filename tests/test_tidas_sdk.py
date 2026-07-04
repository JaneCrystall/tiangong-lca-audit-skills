from __future__ import annotations

import json
import subprocess

import pytest

from tiangong_audit.integrations.tidas_sdk import (
    TidasSdkValidationError,
    validate_enhanced,
)


def test_validate_enhanced_calls_tidas_sdk_validate_enhanced(monkeypatch):
    payload = {"processDataSet": {"processInformation": {}}}
    calls: list[dict] = []

    def fake_run(command, *, input, text, capture_output, timeout, check):
        calls.append(
            {
                "command": command,
                "input": json.loads(input),
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
                "check": check,
            }
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "success": True,
                    "mode": "strict",
                    "validationIssues": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = validate_enhanced(payload, entity_type="process")

    assert result == {"success": True, "mode": "strict", "validationIssues": []}
    assert calls[0]["input"] == {
        "data": payload,
        "entityType": "process",
        "validationConfig": {"mode": "strict", "includeWarnings": True},
    }
    script = calls[0]["command"][-1]
    assert "createTidasEntity" in script
    assert ".validateEnhanced()" in script


def test_validate_enhanced_raises_on_sdk_failure(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="Cannot find package '@tiangong-lca/tidas-sdk'",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(TidasSdkValidationError, match="@tiangong-lca/tidas-sdk"):
        validate_enhanced({}, entity_type="process")
