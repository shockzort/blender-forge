"""Unit tests for bforge.runner.run_job() using a monkeypatched
subprocess.run - no real Blender involved. These exercise the JSON-contract
plumbing (result file read-back, missing-result handling, timeouts) that
the plan requires to be covered without Blender.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bforge import runner as brunner


def test_run_job_reads_result_file_written_by_the_job(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        job_path = Path(cmd[-1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        Path(job["result_path"]).write_text(
            json.dumps({
                "status": "ok",
                "artifacts": ["out.glb"],
                "previews": [],
                "validation": {"ok": True, "errors": [], "tris": 12},
                "blender_stderr_tail": "",
                "error": None,
                "duration_sec": 0.42,
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="banner\n", stderr="")

    monkeypatch.setattr(brunner.subprocess, "run", fake_run)

    result = brunner.run_job({"mode": "build"}, blender_path="fake-blender")

    assert result["status"] == "ok"
    assert result["artifacts"] == ["out.glb"]
    assert result["validation"]["tris"] == 12
    assert result["duration_sec"] >= 0.0


def test_run_job_builds_correct_command_line(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        job_path = Path(cmd[-1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        Path(job["result_path"]).write_text(json.dumps(brunner.empty_result() | {"status": "ok"}))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(brunner.subprocess, "run", fake_run)

    brunner.run_job({"mode": "doctor"}, blender_path="/path/to/blender", timeout=17)

    cmd = captured["cmd"]
    assert cmd[0] == "/path/to/blender"
    assert "--background" in cmd
    assert "--factory-startup" in cmd
    assert "--python" in cmd
    assert cmd[cmd.index("--python") + 1].endswith("runner_entry.py")
    assert cmd[-2] == "--"
    assert captured["timeout"] == 17


def test_run_job_missing_result_file_reports_error_with_tails(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="stdout line\n", stderr="stderr line\nboom-marker")

    monkeypatch.setattr(brunner.subprocess, "run", fake_run)

    result = brunner.run_job({"mode": "build"}, blender_path="fake-blender")

    assert result["status"] == "error"
    assert "without writing a result file" in result["error"]
    assert "boom-marker" in result["blender_stderr_tail"]


def test_run_job_timeout_is_reported_as_error(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout, output=b"", stderr=b"stuck-marker")

    monkeypatch.setattr(brunner.subprocess, "run", fake_run)

    result = brunner.run_job({"mode": "build"}, blender_path="fake-blender", timeout=5)

    assert result["status"] == "error"
    assert "timed out after 5" in result["error"]
    assert "stuck-marker" in result["blender_stderr_tail"]


def test_run_job_malformed_result_file_reports_error(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        job_path = Path(cmd[-1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        Path(job["result_path"]).write_text("{not valid json", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(brunner.subprocess, "run", fake_run)

    result = brunner.run_job({"mode": "build"}, blender_path="fake-blender")

    assert result["status"] == "error"
    assert "could not be parsed" in result["error"]


def test_empty_result_shape_matches_contract():
    result = brunner.empty_result()

    assert set(result.keys()) == {
        "status", "artifacts", "previews", "validation",
        "blender_stderr_tail", "error", "duration_sec",
    }
    assert result["status"] == "error"
    assert result["artifacts"] == []
    assert result["previews"] == []
