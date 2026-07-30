"""Headless turntable preview renders (EEVEE by default - see the
implementation plan's confirmed-by-experiment note: EEVEE and Cycles-CPU
both render fine with no DISPLAY set).

A framing camera is placed around the collection's world-space bounding box,
at `elevation_deg` above the horizon, at N equally-spaced azimuth angles. A
single sun + a flat world background provide enough light to see shape and
palette colors; this is a review tool, not a beauty render.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import bpy
from mathutils import Vector

DEFAULT_ENGINE = 'BLENDER_EEVEE'  # direct assignment; do not probe enum_items (plan §2 nuance)
DEFAULT_ELEVATION_DEG = 30.0
SUN_OBJECT_NAME = "ForgePreviewSun"
CAMERA_OBJECT_NAME = "ForgePreviewCam"
WORLD_NAME = "ForgePreviewWorld"


def _world_bounds(objects: Sequence[bpy.types.Object]) -> tuple[Vector, float]:
    mesh_objects = [o for o in objects if o.type == 'MESH']
    if not mesh_objects:
        raise ValueError("no mesh objects to frame for preview")
    mn = Vector((float("inf"), float("inf"), float("inf")))
    mx = Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in mesh_objects:
        for corner in obj.bound_box:
            world_co = obj.matrix_world @ Vector(corner)
            mn.x = min(mn.x, world_co.x)
            mn.y = min(mn.y, world_co.y)
            mn.z = min(mn.z, world_co.z)
            mx.x = max(mx.x, world_co.x)
            mx.y = max(mx.y, world_co.y)
            mx.z = max(mx.z, world_co.z)
    center = (mn + mx) / 2
    radius = max((mx - mn).length / 2, 0.05)
    return center, radius


def _collection_bounds(collection: bpy.types.Collection) -> tuple[Vector, float]:
    return _world_bounds(list(collection.all_objects))


def _ensure_lighting(scene: bpy.types.Scene) -> None:
    if SUN_OBJECT_NAME not in bpy.data.objects:
        light_data = bpy.data.lights.new(f"{SUN_OBJECT_NAME}Data", type='SUN')
        light_data.energy = 3.0
        sun = bpy.data.objects.new(SUN_OBJECT_NAME, light_data)
        sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))
        scene.collection.objects.link(sun)

    world = scene.world or bpy.data.worlds.new(WORLD_NAME)
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs[0].default_value = (0.05, 0.05, 0.06, 1.0)
        background.inputs[1].default_value = 1.0


def _place_camera(scene: bpy.types.Scene, center: Vector, distance: float, azimuth_deg: float, elevation_deg: float) -> bpy.types.Object:
    cam_data = bpy.data.cameras.get(CAMERA_OBJECT_NAME) or bpy.data.cameras.new(CAMERA_OBJECT_NAME)
    cam = bpy.data.objects.get(CAMERA_OBJECT_NAME) or bpy.data.objects.new(CAMERA_OBJECT_NAME, cam_data)
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    offset = Vector((
        distance * math.cos(el) * math.sin(az),
        -distance * math.cos(el) * math.cos(az),
        distance * math.sin(el),
    ))
    location = center + offset
    cam.location = location
    direction = center - location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    return cam


def _configure_render(scene: bpy.types.Scene, size: tuple[int, int], engine: str) -> None:
    scene.render.engine = engine
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False


def render_turntable(
    collection: bpy.types.Collection,
    out_dir: str,
    angles: int = 4,
    size: tuple[int, int] = (640, 480),
    elevation_deg: float = DEFAULT_ELEVATION_DEG,
    engine: str = DEFAULT_ENGINE,
) -> list[Path]:
    """Renders `angles` PNGs (angle_0.png, angle_1.png, ...) evenly spaced
    around the collection's bounding box, into `out_dir`. Returns the list
    of written file paths."""
    if angles < 1:
        raise ValueError("angles must be >= 1")

    scene = bpy.context.scene
    _configure_render(scene, size, engine)
    _ensure_lighting(scene)

    # Godot strips collider-only/navmesh/noimp objects at import; hide them
    # here too, both from the render and from the camera framing, otherwise
    # an unmaterialed collider box covers the actual asset.
    from forge.export import is_non_visual

    hidden = [obj for obj in collection.all_objects if is_non_visual(obj.name)]
    visual = [obj for obj in collection.all_objects if not is_non_visual(obj.name)]
    prev_hide = {obj.name: obj.hide_render for obj in hidden}

    center, radius = _world_bounds(visual) if visual else _collection_bounds(collection)
    distance = radius * 3.0 + 0.5

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    try:
        for obj in hidden:
            obj.hide_render = True
        for i in range(angles):
            azimuth = i * (360.0 / angles)
            _place_camera(scene, center, distance, azimuth, elevation_deg)
            frame_path = out_path / f"angle_{i}.png"
            scene.render.filepath = str(frame_path)
            with bpy.context.temp_override(scene=scene):
                bpy.ops.render.render(write_still=True)
            written.append(frame_path)
    finally:
        for obj in hidden:
            obj.hide_render = prev_hide.get(obj.name, False)

    return written


def render_still(
    target: bpy.types.Object | bpy.types.Collection,
    filepath: str,
    size: tuple[int, int] = (256, 256),
    azimuth_deg: float = 45.0,
    elevation_deg: float = DEFAULT_ELEVATION_DEG,
    engine: str = DEFAULT_ENGINE,
) -> Path:
    """Renders a single framing shot of `target` (an object or a
    collection) to `filepath`. Used by `bforge doctor`'s render probe."""
    scene = bpy.context.scene
    _configure_render(scene, size, engine)
    _ensure_lighting(scene)

    if isinstance(target, bpy.types.Collection):
        center, radius = _collection_bounds(target)
    else:
        if target.name not in scene.collection.all_objects:
            scene.collection.objects.link(target)
        center, radius = _world_bounds([target])

    distance = radius * 3.0 + 0.5
    _place_camera(scene, center, distance, azimuth_deg, elevation_deg)

    frame_path = Path(filepath)
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frame_path)
    with bpy.context.temp_override(scene=scene):
        bpy.ops.render.render(write_still=True)

    return frame_path
