"""Godot-flavoured GLB export.

The settings in GODOT_GLTF_EXPORT_SETTINGS mirror what Godot 4.7 itself
passes to Blender when importing a .blend file (implementation plan §4.3):
export_format='GLB' (no default in 5.2, must be set explicitly), export_yup,
export_apply (bake modifiers), export_import_convert_lighting_mode='COMPAT',
export_extras (custom properties -> glTF extras), export_image_format='AUTO',
export_vertex_color='MATERIAL'.

Explicitly DISABLED: Draco, meshopt, gltfpack, GPU instancing - Godot 4.7
does not support these glTF extensions and silently drops the affected data
(implementation plan §4.3 / §6 risk table).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import bpy

# Suffix conventions Godot's glTF/scene importer recognizes on object names
# to auto-generate collisions/navigation/import hints. Kept here so recipes
# and forge.validate share one source of truth.
SUFFIXES = {
    "collision": "-col",                    # trimesh (static) collision sibling
    "collision_only": "-colonly",            # trimesh collision, no visual mesh imported
    "collision_convex": "-convcol",          # convex collision sibling, mesh kept as visual too
    "collision_convex_only": "-convcolonly",  # convex collision, no visual mesh imported
    "occluder": "-occ",
    "occluder_only": "-occonly",
    "navmesh": "-navmesh",
    "rigid": "-rigid",
    "no_import": "-noimp",
    "vertex_color": "-vcol",
}

# Suffixes whose objects Godot removes (or never shows) after import: they are
# import metadata, not visible geometry. Previews must hide them, otherwise an
# unmaterialed collider box renders on top of the actual asset.
NON_VISUAL_SUFFIXES = ("colonly", "convcolonly", "occonly", "navmesh", "noimp")


def apply_suffix(name: str, kind: str) -> str:
    """Returns `name` with the Godot import suffix for `kind` appended."""
    if kind not in SUFFIXES:
        raise KeyError(f"unknown Godot suffix kind {kind!r}, expected one of {sorted(SUFFIXES)}")
    return f"{name}{SUFFIXES[kind]}"


def is_non_visual(name: str) -> bool:
    """True if the object name carries a Godot suffix that removes it from the
    imported scene (collider-only, navmesh, noimp...). Matches Godot's rules:
    separators `-`, `_` or `$`, case-insensitive; Blender's numeric duplicate
    suffix (`.001`) is stripped first."""
    base = name.lower()
    if len(base) > 4 and base[-4] == "." and base[-3:].isdigit():
        base = base[:-4]
    return any(base.endswith(sep + suffix) for suffix in NON_VISUAL_SUFFIXES for sep in "-_$")


GODOT_GLTF_EXPORT_SETTINGS: dict[str, object] = {
    "export_format": "GLB",
    "export_yup": True,
    "export_apply": True,
    "export_import_convert_lighting_mode": "COMPAT",
    "export_extras": True,
    "export_image_format": "AUTO",
    "export_vertex_color": "MATERIAL",
    # Explicitly forbidden by the Godot 4.7 compatibility contract:
    "export_draco_mesh_compression_enable": False,
    "export_meshopt_compression_enable": False,
    "export_use_gltfpack": False,
    "export_gpu_instances": False,
}


def export_godot_glb(
    filepath: str,
    collection: bpy.types.Collection | None = None,
    objects: Sequence[bpy.types.Object] | None = None,
) -> str:
    """Exports `collection.all_objects` (or an explicit `objects` list) to a
    GLB at `filepath` using the Godot-compatible preset above. Returns
    `filepath`. Requires at least one object."""
    filepath = str(filepath)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    if objects is None:
        if collection is None:
            raise ValueError("export_godot_glb requires collection= or objects=")
        objects = list(collection.all_objects)
    else:
        objects = list(objects)
    if not objects:
        raise ValueError("export_godot_glb: no objects to export")

    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    # NOTE: view_layer.objects is a cached/evaluated view and does not
    # necessarily reflect objects just linked via collection.objects.link()
    # in background mode (no automatic depsgraph/view-layer sync). Use the
    # live Collection API (users_collection / all_objects) instead - see
    # README "A background-mode nuance" for the underlying story.
    for obj in scene.collection.all_objects:
        obj.select_set(False)
    for obj in objects:
        if not obj.users_collection:
            scene.collection.objects.link(obj)
        obj.select_set(True)

    with bpy.context.temp_override(
        active_object=objects[0],
        selected_objects=objects,
        selected_editable_objects=objects,
        view_layer=view_layer,
        scene=scene,
    ):
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            **GODOT_GLTF_EXPORT_SETTINGS,
        )

    return filepath
