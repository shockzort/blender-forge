"""__RECIPE_NAME__: describe what this asset is and why it exists here.
Keep this docstring up to date when you change the recipe - it is the first
thing a reviewer (human or Claude) reads.
"""

# Every tunable number/color goes here, with a comment. PARAMS is merged on
# top of the project's forge.toml [defaults] (PARAMS wins on conflicts), so
# only put things here that are specific to *this* asset.
PARAMS = {
    "size": 0.4,                                    # metres; 1 Blender unit = 1 metre in Godot
    "palette": ["#8B5A2B", "#D2B48C", "#3A3A3A"],    # hex colors, index 0..N-1
    "poly_budget": 300,                              # triangle budget checked by forge.validate
}


def build(ctx):
    """Builds the asset and returns its root object or collection.

    `ctx` (see forge/session.py) provides:
      ctx.seed             - int, the deterministic seed for this build
      ctx.rng              - random.Random(ctx.seed): the ONLY randomness
                              source you should use (never bare `random.*`
                              or anything time/hash-based) so the same seed
                              always produces the same mesh.
      ctx.params            - dict: this recipe's PARAMS merged on top of the
                              project's forge.toml [defaults].
      ctx.root_collection    - an empty bpy.types.Collection, already created
                              and linked into the (already reset) scene.
      ctx.scene              - the current bpy.types.Scene.

    Requirements checked by forge.validate / bforge build:
      - determinism: no randomness outside ctx.rng.
      - units: metres. Asset "front" faces -Y (Godot convention).
      - transforms applied before returning (scale == 1, rotation == 0) -
        call forge.lowpoly.apply_transforms(obj) on anything you moved/
        scaled/rotated via obj.location/obj.scale/obj.rotation_euler.
      - object names: ASCII only. Use forge.export.SUFFIXES / apply_suffix()
        for Godot collision hints, e.g. "<name>-convcolonly" for a simple
        invisible convex collider (see forge/export.py).
      - triangle count <= PARAMS["poly_budget"].
    """
    from forge import lowpoly, material, palette

    params = ctx.params
    size = params["size"]

    # 1. Palette image + material (nearest-neighbour sampled, so flat colors
    #    stay crisp). See forge/palette.py for the vertex-color alternative.
    pal_image = palette.create_palette_image(params["palette"], name="__RECIPE_NAME__Palette")
    pal_material = palette.palette_material(pal_image, name="__RECIPE_NAME__PaletteMat")

    # 2. Geometry, built with the bmesh-backed helpers in forge.lowpoly
    #    (never bpy.ops for modelling - keeps everything reliable headless).
    obj = lowpoly.create_box(size=(size, size, size), name="__RECIPE_NAME__")
    obj.data.materials.append(pal_material)
    palette.assign_color(obj, color_index=0, palette_size=len(params["palette"]))
    lowpoly.shade_flat(obj)
    lowpoly.apply_transforms(obj)  # no-op here (geometry was already baked at the origin), but explicit and cheap

    ctx.root_collection.objects.link(obj)

    # 3. (Optional) a simple invisible collider, Godot-suffixed so the glTF
    #    importer generates a ConvexPolygonShape3D automatically. Uncomment
    #    and adjust once the asset has a shape worth colliding with:
    #
    # collider = lowpoly.create_box(size=(size, size, size), name="__RECIPE_NAME__-convcolonly")
    # ctx.root_collection.objects.link(collider)

    return ctx.root_collection
