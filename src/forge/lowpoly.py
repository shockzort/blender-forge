"""bmesh-based low-poly modelling helpers.

Design rule (implementation plan §6): geometry is built via bpy.data/bmesh,
never bpy.ops, EXCEPT where there is no reasonable data-API alternative -
join() uses bpy.ops.object.join() under context.temp_override() because it
is the only robust way to merge per-object material slots/indices.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector


def _bmesh_to_object(bm: "bmesh.types.BMesh", name: str) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return bpy.data.objects.new(name, mesh)


# --- primitives --------------------------------------------------------


def create_box(
    size: Sequence[float] = (1.0, 1.0, 1.0),
    name: str = "Box",
    location: Sequence[float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    """A box with dimensions `size` (metres), geometry baked at `location`
    (object transform stays identity). Not linked to any collection."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if any(location):
        bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _bmesh_to_object(bm, name)


def create_cylinder(
    radius: float = 0.5,
    depth: float = 1.0,
    segments: int = 16,
    cap_ends: bool = True,
    name: str = "Cylinder",
    location: Sequence[float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    """A cylinder (constant radius). Not linked to any collection."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=cap_ends, cap_tris=False, segments=segments,
        radius1=radius, radius2=radius, depth=depth,
    )
    if any(location):
        bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _bmesh_to_object(bm, name)


def create_prism(
    radius_bottom: float = 0.5,
    radius_top: float = 0.5,
    depth: float = 1.0,
    sides: int = 6,
    name: str = "Prism",
    location: Sequence[float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    """An N-sided prism/frustum (cone with `radius_top` == `radius_bottom`
    gives a straight prism; set them apart for a tapered shape / pyramid
    when radius_top=0). Not linked to any collection."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=sides,
        radius1=radius_bottom, radius2=radius_top, depth=depth,
    )
    if any(location):
        bmesh.ops.translate(bm, vec=Vector(location), verts=bm.verts)
    return _bmesh_to_object(bm, name)


# --- edit helpers (operate on an existing object's mesh in place) ------


def extrude_faces(obj: bpy.types.Object, face_indices: Iterable[int], translate: Sequence[float] = (0.0, 0.0, 0.0)) -> None:
    """Extrudes the given faces (by index) and moves the new geometry by
    `translate` (in the object's local space)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in face_indices]
    ret = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    if any(translate):
        bmesh.ops.translate(bm, vec=Vector(translate), verts=new_verts)
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def inset_faces(
    obj: bpy.types.Object,
    face_indices: Iterable[int],
    thickness: float = 0.05,
    depth: float = 0.0,
    individual: bool = True,
) -> None:
    """Insets the given faces (by index), either individually or as a
    single region."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in face_indices]
    op = bmesh.ops.inset_individual if individual else bmesh.ops.inset_region
    op(bm, faces=faces, thickness=thickness, depth=depth)
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def bevel_edges(
    obj: bpy.types.Object,
    edge_indices: Iterable[int],
    offset: float = 0.02,
    segments: int = 1,
) -> None:
    """Bevels the given edges (by index)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    edges = [bm.edges[i] for i in edge_indices]
    bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=segments, affect='EDGES')
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def remove_doubles(obj: bpy.types.Object, distance: float = 0.0001) -> None:
    """Merges vertices closer than `distance` apart (a.k.a. merge by distance)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=distance)
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def shade_flat(obj: bpy.types.Object) -> None:
    """Sets flat shading on every polygon (the low-poly default)."""
    for poly in obj.data.polygons:
        poly.use_smooth = False


def shade_smooth(obj: bpy.types.Object) -> None:
    for poly in obj.data.polygons:
        poly.use_smooth = True


def apply_transforms(obj: bpy.types.Object) -> None:
    """Bakes obj.matrix_world into the mesh data and resets the object's
    transform to identity (scale=1, rotation=0). Pure data-API, no bpy.ops -
    required by validate.py before export."""
    matrix = obj.matrix_world.copy()
    if obj.type == 'MESH' and obj.data is not None:
        obj.data.transform(matrix)
        obj.data.update()
    obj.matrix_world = Matrix.Identity(4)


def join(objects: Sequence[bpy.types.Object], name: str | None = None) -> bpy.types.Object:
    """Joins `objects` into the first one, correctly remapping material
    slots/indices. Uses bpy.ops.object.join() under context.temp_override()
    - there is no simple, robust bmesh-only equivalent that preserves
    per-object material assignments (plan §6 allows bpy.ops here)."""
    objects = list(objects)
    if not objects:
        raise ValueError("join() requires at least one object")
    if len(objects) == 1:
        target = objects[0]
    else:
        target = objects[0]
        scene = bpy.context.scene
        view_layer = bpy.context.view_layer
        for obj in objects:
            # users_collection is live (unlike view_layer.objects, which can
            # be stale right after a .link() in background mode).
            if not obj.users_collection:
                scene.collection.objects.link(obj)
        with bpy.context.temp_override(
            active_object=target,
            selected_editable_objects=objects,
            selected_objects=objects,
            view_layer=view_layer,
            scene=scene,
        ):
            bpy.ops.object.join()
    if name:
        target.name = name
    return target
