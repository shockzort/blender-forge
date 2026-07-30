"""Palette-atlas workflow for low-poly materials: a tiny N x 1 pixel PNG
where each pixel is one flat color, and every face's UVs point at the center
of one pixel. This is the default (and more robust) alternative to vertex
colors - see README "Palette vs vertex colors".

PNG is generated purely through bpy.data.images (pixel buffer + save), no
PIL/Pillow and no other third-party imaging library.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import bpy


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#RRGGBB' or '#RGB' -> (r, g, b, a) floats in [0, 1]."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"invalid hex color: {hex_color!r}")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b, alpha)


def create_palette_image(colors: Sequence[str], name: str = "Palette") -> bpy.types.Image:
    """Creates an N x 1 bpy.types.Image, one pixel per color, in palette
    order (index i sits at pixel column i). The image is packed into the
    .blend so it survives without an external file (the glTF exporter will
    embed it into the GLB regardless)."""
    n = len(colors)
    if n == 0:
        raise ValueError("palette must contain at least one color")

    image = bpy.data.images.new(name, width=n, height=1, alpha=True)
    image.colorspace_settings.name = 'sRGB'
    pixels: list[float] = []
    for color in colors:
        pixels.extend(hex_to_rgba(color))
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()
    return image


def save_palette_image(image: bpy.types.Image, filepath: str) -> str:
    """Writes the palette image out as a standalone PNG (useful for
    inspection/tests; not required for GLB export, which embeds it)."""
    filepath = str(filepath)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    image.file_format = 'PNG'
    image.filepath_raw = filepath
    image.save()
    return filepath


def _bsdf_node(material: bpy.types.Material) -> bpy.types.Node:
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    raise RuntimeError(f"material {material.name!r} has no Principled BSDF node")


def palette_material(image: bpy.types.Image, name: str = "PaletteMaterial") -> bpy.types.Material:
    """A material sampling `image` with nearest-neighbour ('Closest')
    interpolation feeding Base Color - keeps flat palette colors crisp."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (150, 0)
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-200, 0)
    tex.image = image
    tex.interpolation = 'Closest'

    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    return mat


def assign_color(
    obj: bpy.types.Object,
    color_index: int,
    palette_size: int,
    faces: Sequence[int] | None = None,
    uv_layer_name: str = "UVMap",
) -> None:
    """Sets the UV coordinates of `faces` (all faces by default) to the
    center of the pixel for `color_index` in an N=palette_size wide palette
    image, i.e. u = (color_index + 0.5) / palette_size, v = 0.5."""
    if not (0 <= color_index < palette_size):
        raise ValueError(f"color_index {color_index} out of range for palette_size {palette_size}")

    mesh = obj.data
    uv_layer = mesh.uv_layers.active or mesh.uv_layers.new(name=uv_layer_name)

    u = (color_index + 0.5) / palette_size
    v = 0.5
    face_indices = range(len(mesh.polygons)) if faces is None else faces
    for poly_index in face_indices:
        poly = mesh.polygons[poly_index]
        for loop_index in poly.loop_indices:
            uv_layer.data[loop_index].uv = (u, v)
