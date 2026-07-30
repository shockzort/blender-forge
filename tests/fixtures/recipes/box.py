"""Test fixture recipe: a simple crate/box used to exercise the M1/M2
pipeline end-to-end in tests/test_integration_blender.py - a palette
material, a `-convcolonly` collider sibling, well under the poly budget.
Not intended as a real game asset.
"""

PARAMS = {
    "size": 0.5,                                    # metres
    "palette": ["#8B5A2B", "#D2B48C", "#3A3A3A"],    # wood brown / tan / dark trim
    "poly_budget": 300,
}


def build(ctx):
    from forge import export, lowpoly, palette

    params = ctx.params
    size = params["size"]

    pal_image = palette.create_palette_image(params["palette"], name="BoxPalette")
    pal_material = palette.palette_material(pal_image, name="BoxPaletteMat")

    visual = lowpoly.create_box(size=(size, size, size), name="box")
    visual.data.materials.append(pal_material)
    palette.assign_color(visual, color_index=0, palette_size=len(params["palette"]))
    lowpoly.shade_flat(visual)
    ctx.root_collection.objects.link(visual)

    # A simple invisible convex collider, Godot-suffixed so the glTF
    # importer generates a ConvexPolygonShape3D and does NOT import a
    # visible mesh for it.
    collider_name = export.apply_suffix("box", "collision_convex_only")
    collider = lowpoly.create_box(size=(size, size, size), name=collider_name)
    ctx.root_collection.objects.link(collider)

    return ctx.root_collection
