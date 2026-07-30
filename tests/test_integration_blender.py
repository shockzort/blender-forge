"""Integration tests that spawn a real headless Blender. Skipped
automatically when no Blender binary can be found (see conftest.py).

Run explicitly against a known Blender with, e.g.:
    BLENDER_PATH=/path/to/blender uv run pytest -m blender
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bforge import runner as brunner
from bforge.cli import main as bforge_main

pytestmark = pytest.mark.blender

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BOX_RECIPE = FIXTURES_DIR / "recipes" / "box.py"


def _last_json_line(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out.splitlines()[-1])


# --- M1: doctor / run --------------------------------------------------


def test_doctor_is_green(blender_path, monkeypatch, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)

    rc = bforge_main(["doctor"])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert result["status"] == "ok"
    diag = result["validation"]
    assert diag["checks"]["headless_render"] is True
    assert diag["checks"]["gltf_export"] is True
    major, minor = (int(x) for x in diag["blender_version"].split(".")[:2])
    assert (major, minor) >= (4, 2)


def test_doctor_timeout_is_reported_as_error(blender_path, monkeypatch, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)

    rc = bforge_main(["doctor", "--timeout", "0.01"])

    result = _last_json_line(capsys)
    assert rc == 1
    assert result["status"] == "error"
    assert "timed out" in result["error"]


def test_run_valid_script_exits_ok_status_ok(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    script = tmp_path / "ok_script.py"
    script.write_text(
        "assert ctx.seed == 0\n"
        "from forge import lowpoly\n"
        "obj = lowpoly.create_box(size=(0.1, 0.1, 0.1), name='RunTest')\n"
        "ctx.scene.collection.objects.link(obj)\n"
        "ctx.add_artifact('marker')\n",
        encoding="utf-8",
    )

    rc = bforge_main(["run", str(script)])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert result["status"] == "ok"
    assert result["error"] is None
    assert result["artifacts"] == ["marker"]


def test_run_broken_script_exits_nonzero_with_full_traceback(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    script = tmp_path / "bad_script.py"
    script.write_text(
        "def broken():\n"
        "    raise RuntimeError('boom-for-integration-test')\n"
        "broken()\n",
        encoding="utf-8",
    )

    rc = bforge_main(["run", str(script)])

    result = _last_json_line(capsys)
    assert rc != 0
    assert result["status"] == "error"
    assert "boom-for-integration-test" in result["error"]
    assert "Traceback (most recent call last):" in result["error"]


def test_run_nonexistent_script_reports_error_without_spawning_blender(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)

    rc = bforge_main(["run", str(tmp_path / "does_not_exist.py")])

    result = _last_json_line(capsys)
    assert rc == 1
    assert result["status"] == "error"
    assert "not found" in result["error"]


# --- M2: build / preview / validate ------------------------------------


def test_build_fixture_box_produces_valid_glb_under_budget(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)  # no forge.toml here -> defaults under tmp_path/assets/*

    rc = bforge_main(["build", str(BOX_RECIPE)])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert result["status"] == "ok"
    validation = result["validation"]
    assert validation["ok"] is True
    assert validation["tris"] <= 300
    assert validation["errors"] == []

    assert len(result["artifacts"]) == 1
    glb_path = Path(result["artifacts"][0])
    assert glb_path.is_file()
    assert glb_path.stat().st_size > 0
    assert glb_path.read_bytes()[:4] == b"glTF"


def test_build_fixture_box_glb_reimports_without_errors(blender_path, monkeypatch, tmp_path, capsys):
    """Acceptance criterion for M2: the produced GLB must round-trip back
    into Blender (import_scene.gltf on a clean scene) without errors."""
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)
    assert bforge_main(["build", str(BOX_RECIPE)]) == 0
    glb_path = Path(_last_json_line(capsys)["artifacts"][0])

    reimport_result = brunner.run_job(
        {"mode": "validate_glb", "glb_path": str(glb_path), "poly_budget": 300},
        blender_path,
    )

    assert reimport_result["status"] == "ok", reimport_result
    assert reimport_result["error"] is None
    assert reimport_result["validation"]["errors"] == []


def test_build_fixture_box_has_convcolonly_collider_node(blender_path, monkeypatch, tmp_path, capsys):
    import struct

    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)
    assert bforge_main(["build", str(BOX_RECIPE)]) == 0
    glb_path = Path(_last_json_line(capsys)["artifacts"][0])

    data = glb_path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + json_len])
    node_names = [n.get("name") for n in doc.get("nodes", [])]

    assert "box-convcolonly" in node_names


def test_build_seed_determinism_same_seed_same_triangle_count(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    assert bforge_main(["build", str(BOX_RECIPE), "--seed", "42"]) == 0
    first = _last_json_line(capsys)["validation"]["tris"]

    assert bforge_main(["build", str(BOX_RECIPE), "--seed", "42"]) == 0
    second = _last_json_line(capsys)["validation"]["tris"]

    assert first == second


def test_build_recipe_with_bad_transform_fails_validation(blender_path, monkeypatch, tmp_path, capsys):
    recipe = tmp_path / "broken_recipe.py"
    recipe.write_text(
        "PARAMS = {'poly_budget': 300}\n"
        "def build(ctx):\n"
        "    from forge import lowpoly\n"
        "    obj = lowpoly.create_box(size=(1, 1, 1), name='broken')\n"
        "    obj.scale = (2.0, 2.0, 2.0)\n"
        "    ctx.root_collection.objects.link(obj)\n"
        "    return ctx.root_collection\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    rc = bforge_main(["build", str(recipe)])

    result = _last_json_line(capsys)
    assert rc != 0
    assert result["status"] == "error"
    assert result["validation"]["transforms_applied"] is False
    assert not (tmp_path / "assets" / "generated" / "broken_recipe.glb").exists()


def test_build_recipe_over_poly_budget_fails_validation(blender_path, monkeypatch, tmp_path, capsys):
    recipe = tmp_path / "toobig_recipe.py"
    recipe.write_text(
        "PARAMS = {'poly_budget': 5}\n"
        "def build(ctx):\n"
        "    from forge import lowpoly\n"
        "    obj = lowpoly.create_cylinder(radius=0.5, depth=1.0, segments=32, name='toobig')\n"
        "    ctx.root_collection.objects.link(obj)\n"
        "    return ctx.root_collection\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    rc = bforge_main(["build", str(recipe)])

    result = _last_json_line(capsys)
    assert rc != 0
    assert result["status"] == "error"
    assert result["validation"]["tris"] > 5
    assert "exceeds budget" in "; ".join(result["validation"]["errors"])


def test_preview_renders_requested_angle_count(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    rc = bforge_main(["preview", str(BOX_RECIPE), "--angles", "4", "--size", "64x64"])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert len(result["previews"]) == 4
    for preview_path in result["previews"]:
        path = Path(preview_path)
        assert path.is_file()
        assert path.stat().st_size > 0
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_validate_recipe_directly_without_export(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    rc = bforge_main(["validate", str(BOX_RECIPE)])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert result["artifacts"] == []  # validate never exports
    assert result["validation"]["ok"] is True


def test_build_all_flag_builds_every_recipe_in_recipes_dir(blender_path, monkeypatch, tmp_path, capsys):
    recipes_dir = tmp_path / "assets" / "recipes"
    recipes_dir.mkdir(parents=True)
    (recipes_dir / "box.py").write_text(BOX_RECIPE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    monkeypatch.chdir(tmp_path)

    rc = bforge_main(["build", "--all"])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert len(result["artifacts"]) == 1
    assert Path(result["artifacts"][0]).name == "box.glb"


def test_non_visual_suffix_predicate_and_preview_hiding(blender_path, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BLENDER_PATH", blender_path)
    script = tmp_path / "non_visual.py"
    script.write_text(
        "from forge.export import is_non_visual\n"
        "assert is_non_visual('Box_collider-convcolonly')\n"
        "assert is_non_visual('Box_collider_CONVCOLONLY')\n"
        "assert is_non_visual('ground-colonly.001')\n"
        "assert is_non_visual('nav$navmesh')\n"
        "assert is_non_visual('helper-noimp')\n"
        "assert not is_non_visual('Box')\n"
        "assert not is_non_visual('Wall-col')\n"        # visual mesh kept by Godot
        "assert not is_non_visual('Crate-convcol')\n"   # visual mesh kept by Godot
        "assert not is_non_visual('colonly')\n"         # suffix needs a separator
        ,
        encoding="utf-8",
    )

    rc = bforge_main(["run", str(script)])

    result = _last_json_line(capsys)
    assert rc == 0, result
    assert result["status"] == "ok"
