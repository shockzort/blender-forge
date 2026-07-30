# Palette workflow (low-poly texturing)

## The idea

One tiny palette texture (N×1 pixels, one pixel per color) for a whole asset
or a whole project. Every face's UVs are collapsed to the **center** of the
pixel with the desired color. This is the standard for stylized low-poly
(Kenney/Synty packs work exactly this way): one material, one draw call, no
texture resolution to manage, perfect compressibility.

Why not diffusion/AI textures: a palette style doesn't need them, and the
pipeline weight (ComfyUI, 8–16 GB VRAM) is out of proportion to the task.

## How forge.palette does it

```python
colors = ctx.params["palette"]
img = palette.create_palette_image(colors, name="Pal")     # hex colors → N×1 px image (bpy.data.images)
mat = palette.palette_material(img, name="PalMat")         # Principled + Image Texture (interpolation='Closest'!)
obj.data.materials.append(mat)
palette.assign_color(obj, color_index=0, palette_size=len(colors))                # all faces → pixel 0 center
palette.assign_color(obj, color_index=2, palette_size=len(colors), faces=[4, 5])  # specific faces (mesh.polygons indices)
```

Critical details:

- **interpolation='Closest'** on the Image Texture node — otherwise bilinear
  filtering blends neighboring palette colors.
- UVs land exactly at pixel centers, never on a boundary.
- Palette colors are sRGB hex; needing more than ~16 colors per asset is a
  sign the style is drifting.

## The project palette

Lives in `forge.toml` → `[defaults] palette = [...]`. A recipe may override
it in `PARAMS["palette"]`, but prefer the project palette by default:
consistency matters more than the "perfect" hue of one asset. Add new colors
only when the user asks. To inherit the project palette, omit the `palette`
key from `PARAMS` entirely — an explicit `"palette": None` would override
the default with `None` (PARAMS wins the merge) and break palette creation.

## The alternative: vertex colors

When: per-vertex gradients, baked pseudo-AO, or fully UV-free assets.

```python
attr = mesh.color_attributes.new("Col", type='BYTE_COLOR', domain='CORNER')
# ... fill attr.data[i].color ...
```

Chain requirements: the Color Attribute is wired into the material's Base
Color (export mode `MATERIAL`) OR export with
`export_vertex_color='ACTIVE'`; on the Godot side the **material** needs the
`-vcol` suffix.

Downsides: a known darkening issue in Godot's Compatibility renderer
(sRGB/linear), suffix magic, harder debugging. Default to the palette atlas;
choose vertex colors deliberately.

## Pseudo-AO and accents without textures

- A darkened palette color for "lower"/inner faces — cheap pseudo-AO.
- An emission pixel in the palette (separate Emission material) — for lamps
  and screens.
- Roughness: one scalar per material (0.8–0.9 for a matte style); don't
  build a map.

## Baking (when a palette isn't enough)

Procedural nodes → texture: only via Cycles bake (CPU, works headless).
Requires a UV unwrap and an active Image Texture node as the bake target.
This is a separate, expensive path — reach for it only when the style
clearly demands it (not implemented in forge; discuss with the user before
building a bake pipeline).
