# Godot 4.x conventions for exported assets

Source: Godot 4.7 documentation and the `modules/gltf` sources (verified
2026-07). Applies to glTF/GLB.

## Name suffixes (auto-processing on import)

Separators `-`, `$` or `_`, case-insensitive (`-col` == `_COL`). The suffix
goes on the **object** name in Blender (the glTF node), except where noted.

| Suffix | What Godot does | When to use |
|---|---|---|
| `-col` | Mesh kept + child StaticBody3D with **exact** (concave) collision | Level geometry where collision = visible mesh |
| `-convcol` | Mesh kept + **convex** collision (ConvexPolygonShape3D) | Simple/movable objects |
| `-colonly` | Mesh REMOVED, only a StaticBody3D with concave collision remains | Separate invisible collision mesh (simplified) |
| `-convcolonly` | Mesh removed, convex collision (convex decomposition) | Invisible prop collider — **the default for props** |
| `-occ` / `-occonly` | Occluder3D (with mesh / instead of mesh) | Visibility optimization, large static geometry |
| `-navmesh` | NavigationMesh, source mesh removed | NPC navigation |
| `-rigid` | Imported as RigidBody3D | Physics objects |
| `-vehicle` / `-wheel` | Child VehicleBody3D / VehicleWheel3D | VehicleBody3D-based vehicles |
| `-noimp` | Node/animation skipped entirely | Helper geometry (preview rigs etc.) |
| `loop` / `cycle` | On an **Action/animation name** (no hyphen needed): loop flag | Looping animations |
| `-alpha` | On a **material**: TRANSPARENCY_ALPHA | Glass, foliage |
| `-vcol` | On a **material**: albedo from vertex colors (+sRGB flag) | Vertex-color workflow |

Prop collider pattern: a simplified child mesh named
`<Name>_collider-convcolonly` with no material.

## Axes, scale, topology

- Godot: right-handed, **Y-up**, camera looks down -Z; an asset's "front" is
  +Z in Godot.
- **In Blender: the asset's "front" is -Y** (+Y is the back). The exporter
  (`export_yup=True`) converts Blender's Z-up — never rotate by hand for the
  engine.
- Scale: glTF and Godot use metres, 1 unit = 1 m.
  `scene.unit_settings.scale_length` does NOT affect glTF export — work in
  default units and treat them as metres.
- Apply transforms before export (scale=1, rot=0) — otherwise editor
  selection and physics behave oddly.
- glTF always triangulates on export. N-gons are forbidden (the validator
  catches them); triangulate non-planar quads yourself (a Triangulate
  modifier — `export_apply=True` applies it) to control the diagonal.

## Export (already baked into `forge.export.export_godot_glb`)

`export_format='GLB'` (explicitly — no default in Blender 5.2),
`export_yup=True`, `export_apply=True` (applies modifiers; incompatible with
shape keys), `export_import_convert_lighting_mode='COMPAT'`,
`export_extras=True` (custom properties → metadata),
`export_image_format='AUTO'`, `export_vertex_color='MATERIAL'`.

**Permanently forbidden** (Godot 4.7 does not support these; data is lost
SILENTLY — glTF `extensionsUsed` is ignored without errors):

- `export_draco_mesh_compression_enable`
- `export_meshopt_compression_enable`, `export_use_gltfpack`
- `export_gpu_instances` (EXT_mesh_gpu_instancing — open Godot issue
  #109280; build MultiMesh batching on the Godot side instead)

## Materials

- Only the **canonical Principled BSDF graph** survives: Base Color (value
  or Image Texture), Metallic/Roughness (values or an ORM texture:
  G=roughness, B=metallic), Normal Map (through a Normal Map node,
  Non-Color), Emission. Anything else (Mix Shader, procedural textures,
  Color Ramp) does NOT export — bake it or avoid it.
- Textures: PNG/JPEG (other formats get converted, slower).
- **Backface culling**: disabled by default in Blender → Godot sets
  cull_mode=Disabled (costly). Set `material.use_backface_culling = True`
  for opaque geometry.
- Vertex colors: the `MATERIAL` export mode requires the Color Attribute to
  be wired into Base Color; on the Godot side the material needs the `-vcol`
  suffix. Known nuance: Godot's Compatibility renderer darkens vertex colors
  (sRGB). The palette atlas is more reliable.

## On the Godot side

- Put GLBs in the project (e.g. `res://assets/generated/`) — Godot imports
  on editor focus; headless: `godot --headless --path <project> --import`.
- Commit `.import` files to git together with the GLBs.
- Metadata from custom properties (glTF extras) is reachable via
  `GLTFDocumentExtension`/import scripts — useful for game semantics (type,
  layer, etc.).
- Linked duplicates (shared mesh data) → several MeshInstance3D sharing one
  ArrayMesh: memory is not duplicated, but that is not MultiMesh batching.
