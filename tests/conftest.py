"""Shared pytest configuration.

Tests marked `@pytest.mark.blender` spawn a real headless Blender
subprocess. They are auto-skipped when no Blender binary can be found via
$BLENDER_PATH or PATH, so the unit test suite always runs standalone.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


def _discover_blender() -> str | None:
    env = os.environ.get("BLENDER_PATH")
    if env and Path(env).is_file() and os.access(env, os.X_OK):
        return env
    return shutil.which("blender")


DISCOVERED_BLENDER_PATH = _discover_blender()


@pytest.fixture(scope="session")
def blender_path() -> str:
    if not DISCOVERED_BLENDER_PATH:
        pytest.skip("no blender binary found via $BLENDER_PATH or PATH")
    return DISCOVERED_BLENDER_PATH


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if DISCOVERED_BLENDER_PATH:
        return
    skip_blender = pytest.mark.skip(reason="no blender binary found via $BLENDER_PATH or PATH")
    for item in items:
        if "blender" in item.keywords:
            item.add_marker(skip_blender)
