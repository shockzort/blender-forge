"""Street mailbox on a pillar: a demo prop showing the full recipe workflow -
palette material, multi-part bmesh construction, direct vertex tweaks (slanted
lid), a Godot collider suffix, and real-world metric sizing. Pivot at the
bottom center. Total height ~1.2 m.
"""

PARAMS = {
    "body_size": (0.45, 0.35, 0.50),   # body: width X, depth Y, height Z (metres)
    "body_bottom": 0.65,               # height of the body's underside above ground
    "lid_height": 0.08,                # slanted lid thickness
    "lid_slope": 0.05,                 # how far the lid drops toward the front face
    "pillar_size": 0.08,               # pillar cross-section
    "band_height": 0.05,               # accent band height
    "palette": ["#4F7CAC", "#2E2E2E", "#F2B233"],  # 0 body blue, 1 dark trim, 2 accent
    "color_body": 0,
    "color_trim": 1,
    "color_band": 2,
    "poly_budget": 300,
}


def build(ctx):
    from forge import export, lowpoly, palette

    p = ctx.params
    bx, by, bz = p["body_size"]
    z0 = p["body_bottom"]
    z_top = z0 + bz
    colors = p["palette"]

    pal_img = palette.create_palette_image(colors, name="MailboxPalette")
    pal_mat = palette.palette_material(pal_img, name="MailboxPaletteMat")

    def paint(obj, color_index):
        obj.data.materials.append(pal_mat)
        palette.assign_color(obj, color_index=color_index, palette_size=len(colors))
        return obj

    body = paint(
        lowpoly.create_box(size=(bx, by, bz), location=(0, 0, z0 + bz / 2), name="MailboxBody"),
        p["color_body"],
    )

    # Slanted lid: a box whose top-front (-Y) vertices are pulled down.
    lid = lowpoly.create_box(
        size=(bx + 0.02, by + 0.02, p["lid_height"]),
        location=(0, 0, z_top + p["lid_height"] / 2),
        name="MailboxLid",
    )
    lid_top_z = z_top + p["lid_height"] * 0.9
    for v in lid.data.vertices:
        if v.co.z > lid_top_z and v.co.y < 0:
            v.co.z -= p["lid_slope"]
    paint(lid, p["color_trim"])

    # Mail slot: a dark plate protruding slightly from the front face.
    slot = paint(
        lowpoly.create_box(
            size=(0.30, 0.02, 0.03),
            location=(0, -by / 2 - 0.008, z0 + bz * 0.78),
            name="MailboxSlot",
        ),
        p["color_trim"],
    )

    # Accent band, slightly wider than the body.
    band = paint(
        lowpoly.create_box(
            size=(bx + 0.012, by + 0.012, p["band_height"]),
            location=(0, 0, z0 + bz * 0.42),
            name="MailboxBand",
        ),
        p["color_band"],
    )

    ps = p["pillar_size"]
    pillar = paint(
        lowpoly.create_box(size=(ps, ps, z0), location=(0, 0, z0 / 2), name="MailboxPillar"),
        p["color_trim"],
    )
    foot = paint(
        lowpoly.create_box(size=(0.26, 0.22, 0.03), location=(0, 0, 0.015), name="MailboxFoot"),
        p["color_trim"],
    )

    visual = lowpoly.join([body, lid, slot, band, pillar, foot], name="Mailbox")
    lowpoly.shade_flat(visual)
    ctx.root_collection.objects.link(visual)

    # Convex collider around the body + lid; Godot generates a
    # ConvexPolygonShape3D from the `-convcolonly` suffix and drops the mesh.
    total_h = z_top + p["lid_height"]
    collider = lowpoly.create_box(
        size=(bx + 0.02, by + 0.02, total_h),
        location=(0, 0, total_h / 2),
        name=export.apply_suffix("Mailbox_collider", "collision_convex_only"),
    )
    ctx.root_collection.objects.link(collider)

    return ctx.root_collection
