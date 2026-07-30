"""Scene lifecycle: resetting to a clean, deterministic Blender session and
the runtime context (`Context`) handed to recipe build(ctx) functions and to
`bforge run` scripts.

Units: 1 Blender unit = 1 metre (Godot convention). Asset "front" = -Y.
"""

from __future__ import annotations

import random
from typing import Any

import bpy

ASSET_COLLECTION_NAME = "Asset"


def reset_scene(seed: int = 0, collection_name: str = ASSET_COLLECTION_NAME):
    """Resets Blender to a clean, empty scene (factory settings, no default
    cube/camera/light), sets metric units with scale_length=1.0 (1 unit = 1
    metre), and creates+links a fresh root collection for the asset being
    built.

    Returns (scene, root_collection).
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'

    # Fresh, deterministic RNG seed for anything that reads it directly
    # (recipes should prefer ctx.rng, see Context below).
    random.seed(seed)

    root = bpy.data.collections.new(collection_name)
    scene.collection.children.link(root)

    return scene, root


class Context:
    """Runtime context passed to `def build(ctx)` in recipes and exposed as
    the `ctx` global to `bforge run` scripts.

    Attributes:
        seed: the deterministic seed for this build.
        rng: a `random.Random(seed)` instance - the ONLY source of randomness
            recipes should use (never bare `random.*`), so builds are
            reproducible for a given seed.
        params: the recipe's PARAMS dict merged on top of the project's
            forge.toml [defaults] (PARAMS wins on key conflicts).
        root_collection: the collection new geometry should be linked into.
        scene: the (already reset) current bpy.types.Scene.
        artifacts / previews / warnings: free-form lists a `run` script can
            append to via add_artifact()/add_preview()/warn() to surface
            things in the final JSON result.
    """

    def __init__(self, seed: int, params: dict[str, Any], root_collection, scene):
        self.seed = seed
        self.rng = random.Random(seed)
        self.params = dict(params)
        self.root_collection = root_collection
        self.scene = scene
        self.artifacts: list[str] = []
        self.previews: list[str] = []
        self.warnings: list[str] = []

    def add_artifact(self, path: str) -> None:
        self.artifacts.append(str(path))

    def add_preview(self, path: str) -> None:
        self.previews.append(str(path))

    def warn(self, message: str) -> None:
        self.warnings.append(str(message))


def new_context(seed: int, params: dict[str, Any], collection_name: str = ASSET_COLLECTION_NAME) -> Context:
    """Convenience: reset_scene() + wrap the result in a Context."""
    scene, root = reset_scene(seed=seed, collection_name=collection_name)
    return Context(seed=seed, params=params, root_collection=root, scene=scene)
