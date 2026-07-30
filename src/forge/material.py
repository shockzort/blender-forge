"""Canonical materials: only what survives the glTF/Godot round-trip.

glTF's PBR metallic-roughness model maps onto a handful of Principled BSDF
inputs (Base Color, Metallic, Roughness, Emission); everything else in the
node tree (procedural textures, complex node graphs, ...) is dropped silently
by the exporter. Keep material graphs to exactly what's below.

Two workflows are offered:
  - simple_material(): a flat Base Color / Metallic / Roughness, no texture.
  - vertex_color_material(): reads a Color Attribute (vertex colors) into
    Base Color - the alternative to palette.py's image-texture atlas. Note
    the known sRGB darkening nuance in Godot's Compatibility renderer (see
    README).
"""

from __future__ import annotations

from typing import Sequence

import bpy


def _bsdf_node(material: bpy.types.Material) -> bpy.types.Node:
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    raise RuntimeError(f"material {material.name!r} has no Principled BSDF node")


def _set_input(node: bpy.types.Node, identifier: str, value) -> None:
    socket = node.inputs.get(identifier)
    if socket is None:
        raise KeyError(f"node {node.name!r} has no input {identifier!r}")
    socket.default_value = value


def simple_material(
    name: str,
    base_color: Sequence[float] = (0.8, 0.8, 0.8, 1.0),
    metallic: float = 0.0,
    roughness: float = 0.5,
) -> bpy.types.Material:
    """A flat-colored Principled material - only Base Color/Metallic/
    Roughness are set, all of which survive glTF export."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = _bsdf_node(mat)
    color = tuple(base_color) if len(base_color) == 4 else (*base_color, 1.0)
    _set_input(bsdf, "Base Color", color)
    _set_input(bsdf, "Metallic", metallic)
    _set_input(bsdf, "Roughness", roughness)
    mat.diffuse_color = color  # viewport/solid-shading preview only
    return mat


def vertex_color_material(name: str, attribute_name: str = "Col") -> bpy.types.Material:
    """A material that reads vertex colors (Color Attribute `attribute_name`)
    into Base Color. Pair with set_vertex_colors() and export with
    export_vertex_color='MATERIAL' (forge.export default)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = _bsdf_node(mat)

    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = attribute_name
    attr.location = (-200, 0)
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def set_vertex_colors(
    obj: bpy.types.Object,
    color: Sequence[float],
    attribute_name: str = "Col",
    faces: Sequence[int] | None = None,
) -> None:
    """Paints a flat color onto a BYTE_COLOR/CORNER color attribute, on all
    faces by default."""
    mesh = obj.data
    attr = mesh.color_attributes.get(attribute_name)
    if attr is None:
        attr = mesh.color_attributes.new(name=attribute_name, type='BYTE_COLOR', domain='CORNER')

    rgba = tuple(color) if len(color) == 4 else (*color, 1.0)

    if attr.domain == 'CORNER':
        face_indices = range(len(mesh.polygons)) if faces is None else faces
        for poly_index in face_indices:
            poly = mesh.polygons[poly_index]
            for loop_index in poly.loop_indices:
                attr.data[loop_index].color = rgba
    else:  # POINT domain: one entry per vertex
        vert_indices = range(len(mesh.vertices)) if faces is None else set(
            v for i in faces for v in mesh.polygons[i].vertices
        )
        for vert_index in vert_indices:
            attr.data[vert_index].color = rgba
