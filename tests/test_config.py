"""Unit tests for bforge.config - no Blender required."""

from __future__ import annotations

import shutil

import pytest

from bforge import config as bconfig


def _make_exe(path):
    path.write_text("#!/bin/sh\necho fake-blender\n")
    path.chmod(0o755)
    return path


# --- forge.toml discovery ------------------------------------------------


def test_find_forge_toml_walks_up_from_cwd(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "forge.toml").write_text('[project]\nrecipes_dir = "assets/recipes"\n')
    nested = repo / "assets" / "recipes"
    nested.mkdir(parents=True)

    found = bconfig.find_forge_toml(nested)

    assert found == repo / "forge.toml"


def test_find_forge_toml_stops_at_git_root(tmp_path):
    outer_toml = tmp_path / "forge.toml"
    outer_toml.write_text("[project]\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    cwd = repo / "sub"
    cwd.mkdir()

    # forge.toml exists ABOVE the git root but must not be found: the
    # search must stop at (inclusive of) the git root.
    found = bconfig.find_forge_toml(cwd)

    assert found is None


def test_find_forge_toml_none_when_absent(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    assert bconfig.find_forge_toml(repo) is None


def test_find_forge_toml_found_at_git_root_itself(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "forge.toml").write_text("[project]\n")

    assert bconfig.find_forge_toml(repo) == repo / "forge.toml"


def test_load_config_parses_toml(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "forge.toml").write_text(
        '[project]\nrecipes_dir = "r"\n\n[defaults]\npoly_budget = 250\n'
    )

    cfg = bconfig.load_config(tmp_path)

    assert cfg.get("project", "recipes_dir") == "r"
    assert cfg.get("defaults", "poly_budget") == 250
    assert cfg.get("nonexistent", "key", default="fallback") == "fallback"


def test_load_config_empty_when_no_forge_toml(tmp_path):
    (tmp_path / ".git").mkdir()

    cfg = bconfig.load_config(tmp_path)

    assert cfg.path is None
    assert cfg.data == {}


# --- find_blender ----------------------------------------------------------


def test_find_blender_prefers_env_var(tmp_path, monkeypatch):
    fake = _make_exe(tmp_path / "fake-blender")
    monkeypatch.setenv("BLENDER_PATH", str(fake))

    assert bconfig.find_blender(None) == str(fake)


def test_find_blender_falls_back_to_forge_toml_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    fake = _make_exe(tmp_path / "fake-blender")
    toml_path = tmp_path / "forge.toml"
    cfg = bconfig.ForgeConfig(toml_path, {"blender": {"path": str(fake)}})

    assert bconfig.find_blender(cfg) == str(fake)


def test_find_blender_resolves_relative_forge_toml_path(tmp_path, monkeypatch):
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = _make_exe(bin_dir / "fake-blender")
    toml_path = tmp_path / "forge.toml"
    cfg = bconfig.ForgeConfig(toml_path, {"blender": {"path": "bin/fake-blender"}})

    assert bconfig.find_blender(cfg) == str(fake.resolve())


def test_find_blender_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/blender" if name == "blender" else None)

    assert bconfig.find_blender(None) == "/usr/bin/blender"


def test_find_blender_none_when_nothing_found(monkeypatch):
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert bconfig.find_blender(None) is None


def test_find_blender_env_var_ignored_if_not_executable(tmp_path, monkeypatch):
    not_exe = tmp_path / "not-executable"
    not_exe.write_text("nope")
    monkeypatch.setenv("BLENDER_PATH", str(not_exe))
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert bconfig.find_blender(None) is None


# --- find_forge_repo_root ----------------------------------------------


def test_find_forge_repo_root_locates_runner_entry():
    root = bconfig.find_forge_repo_root()

    assert (root / "runner_entry.py").is_file()
    assert (root / "src" / "bforge").is_dir()


# --- project_paths / defaults -------------------------------------------


def test_project_paths_defaults(tmp_path):
    cfg = bconfig.ForgeConfig(tmp_path / "forge.toml", {})

    paths = bconfig.project_paths(cfg)

    assert paths["root"] == tmp_path
    assert paths["recipes_dir"] == tmp_path / "assets" / "recipes"
    assert paths["output_dir"] == tmp_path / "assets" / "generated"
    assert paths["previews_dir"] == tmp_path / "assets" / "previews"


def test_project_paths_custom(tmp_path):
    data = {"project": {"recipes_dir": "recipes", "output_dir": "out", "previews_dir": "prev"}}
    cfg = bconfig.ForgeConfig(tmp_path / "forge.toml", data)

    paths = bconfig.project_paths(cfg)

    assert paths["recipes_dir"] == tmp_path / "recipes"
    assert paths["output_dir"] == tmp_path / "out"
    assert paths["previews_dir"] == tmp_path / "prev"


def test_project_paths_uses_cwd_without_forge_toml(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cfg = bconfig.ForgeConfig(None, {})

    paths = bconfig.project_paths(cfg)

    assert paths["root"] == tmp_path


def test_defaults_returns_dict(tmp_path):
    cfg = bconfig.ForgeConfig(tmp_path / "forge.toml", {"defaults": {"poly_budget": 500}})

    assert bconfig.defaults(cfg) == {"poly_budget": 500}


def test_defaults_empty_when_absent(tmp_path):
    cfg = bconfig.ForgeConfig(tmp_path / "forge.toml", {})

    assert bconfig.defaults(cfg) == {}
