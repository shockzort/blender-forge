"""Configuration resolution for bforge: locating the Blender binary, the
consuming project's forge.toml, and this toolkit's own repo root.

Stdlib only (tomllib requires Python >= 3.11; this project requires >= 3.12).
"""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any


class ForgeConfig:
    """Parsed forge.toml plus the path it was loaded from (may be absent)."""

    def __init__(self, path: Path | None, data: dict[str, Any]):
        self.path = path
        self.data = data

    @property
    def project_root(self) -> Path:
        """Directory that forge.toml lives in, or cwd if there is none."""
        return self.path.parent if self.path is not None else Path.cwd()

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def find_git_root(start: Path) -> Path | None:
    """Walk upward from `start` looking for a `.git` entry."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def find_forge_toml(start: Path | None = None) -> Path | None:
    """Search for forge.toml from `start` (default: cwd) upward, stopping at
    the git repository root (inclusive) per the plan's resolution rule.

    If `start` is not inside a git repo, the search walks all the way to the
    filesystem root - this keeps `bforge` usable outside of git too.
    """
    start = (start or Path.cwd()).resolve()
    git_root = find_git_root(start)
    current = start
    while True:
        candidate = current / "forge.toml"
        if candidate.is_file():
            return candidate
        if git_root is not None and current == git_root:
            return None
        if current.parent == current:
            return None
        current = current.parent


def load_config(start: Path | None = None) -> ForgeConfig:
    toml_path = find_forge_toml(start)
    data: dict[str, Any] = {}
    if toml_path is not None:
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
    return ForgeConfig(toml_path, data)


def find_blender(config: ForgeConfig | None = None) -> str | None:
    """Resolve the Blender executable: $BLENDER_PATH -> forge.toml
    [blender].path -> PATH.
    """
    env_path = os.environ.get("BLENDER_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    if config is not None:
        cfg_path = config.get("blender", "path")
        if cfg_path:
            candidate = Path(cfg_path)
            if not candidate.is_absolute() and config.path is not None:
                candidate = (config.path.parent / candidate).resolve()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    found = shutil.which("blender")
    if found:
        return found

    return None


def find_forge_repo_root() -> Path:
    """Locate the blender-forge toolkit's own root directory (the one
    containing runner_entry.py), regardless of whether bforge was installed
    editable or not, by walking up from this file. Only requires
    runner_entry.py + src/bforge (this very package) to exist, so it works
    from M1 onward, before src/forge/ (added in M2) exists.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "runner_entry.py").is_file() and (candidate / "src" / "bforge").is_dir():
            return candidate
    raise RuntimeError(
        f"cannot locate the blender-forge repo root (runner_entry.py not found above {here}); "
        "is bforge installed correctly?"
    )


def project_paths(config: ForgeConfig) -> dict[str, Path]:
    root = config.project_root
    recipes_dir = root / config.get("project", "recipes_dir", default="assets/recipes")
    output_dir = root / config.get("project", "output_dir", default="assets/generated")
    previews_dir = root / config.get("project", "previews_dir", default="assets/previews")
    return {
        "root": root,
        "recipes_dir": recipes_dir,
        "output_dir": output_dir,
        "previews_dir": previews_dir,
    }


def defaults(config: ForgeConfig) -> dict[str, Any]:
    return dict(config.get("defaults", default={}) or {})
