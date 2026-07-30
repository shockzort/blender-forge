"""Asset validation (implementation plan §4.4).

Blocking errors (make the build fail / exit code != 0):
  - triangle count over budget
  - un-applied transform (scale != 1 or rotation != 0) on any object
  - degenerate faces (zero area)
  - UV coordinates outside [0, 1] when the object uses an image-textured
    (palette) material
  - non-ASCII object/collection names

Warnings only (do NOT fail the build):
  - non-manifold edges: legitimate for open meshes / planes (signage,
    foliage cards, etc.), so this is informational, not an error.
  - more than `max_materials` materials used.
  - overall bounding box bigger than 10 m or smaller than 1 cm (likely a
    unit mistake, but not necessarily wrong).
"""

from __future__ import annotations

from typing import Any

import bmesh
import bpy
from mathutils import Vector

DEFAULT_POLY_BUDGET = 300
DEFAULT_MAX_MATERIALS = 2
DEFAULT_MIN_DIM = 0.01
DEFAULT_MAX_DIM = 10.0
DEGENERATE_AREA_EPS = 1e-10
TRANSFORM_EPS = 1e-5


def _uses_image_texture(material: bpy.types.Material) -> bool:
    if material is None or not material.use_nodes or material.node_tree is None:
        return False
    return any(node.type == 'TEX_IMAGE' for node in material.node_tree.nodes)


def _transform_applied(obj: bpy.types.Object) -> bool:
    scale_ok = all(abs(s - 1.0) < TRANSFORM_EPS for s in obj.scale)
    if obj.rotation_mode == 'QUATERNION':
        q = obj.rotation_quaternion
        rot_ok = abs(q.w - 1.0) < TRANSFORM_EPS and all(abs(v) < TRANSFORM_EPS for v in (q.x, q.y, q.z))
    elif obj.rotation_mode == 'AXIS_ANGLE':
        rot_ok = abs(obj.rotation_axis_angle[0]) < TRANSFORM_EPS
    else:
        rot_ok = all(abs(r) < TRANSFORM_EPS for r in obj.rotation_euler)
    return scale_ok and rot_ok


def validate_collection(
    collection: bpy.types.Collection,
    poly_budget: int = DEFAULT_POLY_BUDGET,
    max_materials: int = DEFAULT_MAX_MATERIALS,
    min_dim: float = DEFAULT_MIN_DIM,
    max_dim: float = DEFAULT_MAX_DIM,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    mesh_objects = [o for o in collection.all_objects if o.type == 'MESH']
    if not mesh_objects:
        errors.append("collection has no mesh objects")

    if not collection.name.isascii():
        errors.append(f"collection name is not ASCII: {collection.name!r}")

    tris = 0
    materials: set[str] = set()
    transforms_applied = True
    names_ascii = collection.name.isascii()
    manifold = True
    uv_ok = True

    depsgraph = bpy.context.evaluated_depsgraph_get()
    world_min = Vector((float("inf"), float("inf"), float("inf")))
    world_max = Vector((float("-inf"), float("-inf"), float("-inf")))

    for obj in mesh_objects:
        if not obj.name.isascii():
            names_ascii = False
            errors.append(f"object name is not ASCII: {obj.name!r}")

        if not _transform_applied(obj):
            transforms_applied = False
            errors.append(
                f"object {obj.name!r} has an un-applied transform "
                f"(scale={tuple(round(s, 4) for s in obj.scale)}, "
                f"rotation_euler={tuple(round(r, 4) for r in obj.rotation_euler)})"
            )

        eval_obj = obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.to_mesh()
        eval_mesh.calc_loop_triangles()
        tris += len(eval_mesh.loop_triangles)
        eval_obj.to_mesh_clear()

        for mat in obj.data.materials:
            if mat is not None:
                materials.add(mat.name)

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        for face in bm.faces:
            if face.calc_area() <= DEGENERATE_AREA_EPS:
                errors.append(f"degenerate face (zero area) on {obj.name!r}, face index {face.index}")

        for edge in bm.edges:
            if not edge.is_manifold:
                manifold = False

        if any(_uses_image_texture(m) for m in obj.data.materials if m is not None):
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None:
                uv_ok = False
                errors.append(f"object {obj.name!r} uses an image-textured material but has no UV map")
            else:
                out_of_range = False
                for face in bm.faces:
                    for loop in face.loops:
                        u, v = loop[uv_layer].uv
                        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
                            out_of_range = True
                            break
                    if out_of_range:
                        break
                if out_of_range:
                    uv_ok = False
                    errors.append(f"object {obj.name!r} has UV coordinates outside [0, 1]")

        bm.free()

        for corner in obj.bound_box:
            world_co = obj.matrix_world @ Vector(corner)
            world_min.x = min(world_min.x, world_co.x)
            world_min.y = min(world_min.y, world_co.y)
            world_min.z = min(world_min.z, world_co.z)
            world_max.x = max(world_max.x, world_co.x)
            world_max.y = max(world_max.y, world_co.y)
            world_max.z = max(world_max.z, world_co.z)

    if not manifold:
        warnings.append(
            "mesh has non-manifold edges (open boundary) - fine for planes/open "
            "geometry, but double-check this is intentional"
        )

    if len(materials) > max_materials:
        warnings.append(f"{len(materials)} materials used, recommended <= {max_materials}")

    if tris > poly_budget:
        errors.append(f"triangle count {tris} exceeds budget {poly_budget}")

    if mesh_objects:
        dims = world_max - world_min
        positive_dims = [d for d in (dims.x, dims.y, dims.z) if d > 0]
        largest = max(dims.x, dims.y, dims.z)
        smallest = min(positive_dims) if positive_dims else 0.0
        if largest > max_dim:
            warnings.append(f"asset largest dimension {largest:.3f} m exceeds {max_dim} m")
        if positive_dims and smallest < min_dim:
            warnings.append(f"asset smallest dimension {smallest:.4f} m is below {min_dim} m")

    return {
        "tris": tris,
        "budget": poly_budget,
        "materials": len(materials),
        "manifold": manifold,
        "uv_ok": uv_ok,
        "transforms_applied": transforms_applied,
        "names_ascii": names_ascii,
        "warnings": warnings,
        "errors": errors,
        "ok": len(errors) == 0,
    }
