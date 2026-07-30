"""Unit tests for bforge.cli - argument parsing, result JSON assembly, and
the `new` command (pure filesystem, no Blender). Commands that need Blender
(doctor/build/preview/run/validate execution) are covered in
tests/test_integration_blender.py.
"""

from __future__ import annotations

import argparse
import json
import shutil

import pytest

from bforge import cli as bcli
from bforge import runner as brunner


# --- argument parsing ----------------------------------------------------


def test_doctor_subcommand_parses():
    args = bcli.build_parser().parse_args(["doctor"])
    assert args.command == "doctor"
    assert args.timeout == brunner.DEFAULT_TIMEOUT


def test_build_subcommand_parses_recipes_and_flags():
    args = bcli.build_parser().parse_args(["build", "a", "b", "--seed", "3", "--timeout", "60"])
    assert args.recipes == ["a", "b"]
    assert args.all is False
    assert args.seed == 3
    assert args.timeout == 60.0


def test_build_subcommand_all_flag():
    args = bcli.build_parser().parse_args(["build", "--all"])
    assert args.all is True
    assert args.recipes == []


def test_preview_subcommand_parses():
    args = bcli.build_parser().parse_args(["preview", "foo", "--angles", "8", "--size", "128x128"])
    assert args.recipe == "foo"
    assert args.angles == 8
    assert args.size == "128x128"


def test_run_subcommand_parses():
    args = bcli.build_parser().parse_args(["run", "script.py"])
    assert args.script == "script.py"
    assert args.seed == 0


def test_validate_subcommand_parses():
    args = bcli.build_parser().parse_args(["validate", "thing.glb"])
    assert args.target == "thing.glb"


def test_new_subcommand_parses_force_flag():
    args = bcli.build_parser().parse_args(["new", "widget", "--force"])
    assert args.name == "widget"
    assert args.force is True


def test_missing_subcommand_errors():
    with pytest.raises(SystemExit):
        bcli.build_parser().parse_args([])


# --- helpers ---------------------------------------------------------------


def test_parse_size_valid():
    assert bcli._parse_size("640x480") == (640, 480)
    assert bcli._parse_size("64X64") == (64, 64)


def test_parse_size_invalid():
    with pytest.raises(argparse.ArgumentTypeError):
        bcli._parse_size("not-a-size")


def test_merge_build_results_single_passthrough():
    result = brunner.empty_result()
    result["status"] = "ok"

    merged = bcli._merge_build_results([result], ["box"])

    assert merged is result


def test_merge_build_results_multi_all_ok():
    r1 = brunner.empty_result()
    r1.update(status="ok", artifacts=["a.glb"], duration_sec=1.0)
    r2 = brunner.empty_result()
    r2.update(status="ok", artifacts=["b.glb"], duration_sec=2.0)

    merged = bcli._merge_build_results([r1, r2], ["a", "b"])

    assert merged["status"] == "ok"
    assert merged["artifacts"] == ["a.glb", "b.glb"]
    assert merged["duration_sec"] == 3.0
    assert merged["error"] is None


def test_merge_build_results_multi_one_failure_propagates_error():
    r1 = brunner.empty_result()
    r1.update(status="ok")
    r2 = brunner.empty_result()
    r2.update(status="error", error="boom")

    merged = bcli._merge_build_results([r1, r2], ["a", "b"])

    assert merged["status"] == "error"
    assert "b: boom" in merged["error"]


# --- _print_result / exit-code gating --------------------------------------


def test_print_result_ok_status_no_validation_errors(capsys):
    result = brunner.empty_result()
    result["status"] = "ok"

    rc = bcli._print_result(result)

    assert rc == 0
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed["status"] == "ok"


def test_print_result_error_status_nonzero_exit(capsys):
    result = brunner.empty_result()
    result["status"] = "error"

    rc = bcli._print_result(result)

    assert rc == 1


def test_print_result_ok_status_but_validation_errors_still_fails(capsys):
    result = brunner.empty_result()
    result["status"] = "ok"
    result["validation"] = {"ok": False, "errors": ["triangle count too high"]}

    rc = bcli._print_result(result)

    assert rc == 1


def test_print_result_ok_status_validation_warnings_only_still_ok(capsys):
    result = brunner.empty_result()
    result["status"] = "ok"
    result["validation"] = {"ok": True, "errors": [], "warnings": ["big asset"]}

    rc = bcli._print_result(result)

    assert rc == 0


# --- `new` command (pure filesystem, no Blender) ---------------------------


def test_cmd_new_creates_recipe_from_template(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = bcli.main(["new", "widget"])

    assert rc == 0
    recipe_path = tmp_path / "assets" / "recipes" / "widget.py"
    assert recipe_path.is_file()
    text = recipe_path.read_text(encoding="utf-8")
    assert "widget" in text
    assert "__RECIPE_NAME__" not in text
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["status"] == "ok"
    assert printed["artifacts"] == [str(recipe_path)]


def test_cmd_new_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert bcli.main(["new", "widget"]) == 0
    capsys.readouterr()

    rc = bcli.main(["new", "widget"])

    assert rc == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "already exists" in printed["error"]


def test_cmd_new_force_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert bcli.main(["new", "widget"]) == 0
    capsys.readouterr()

    rc = bcli.main(["new", "widget", "--force"])

    assert rc == 0


def test_cmd_build_without_blender_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    rc = bcli.main(["build", "--all"])

    assert rc == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["status"] == "error"
    assert "blender executable not found" in printed["error"]
