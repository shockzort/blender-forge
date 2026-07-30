# bpy/bmesh patterns for headless low-poly work (Blender 5.x)

## The main rule

`bpy.data` + `bmesh` instead of `bpy.ops`. Operators (`bpy.ops.*`) depend on
UI context (`poll()`) and in headless mode often fail with
`RuntimeError: context is incorrect`. When an operator is unavoidable
(import/export, a few modifiers):

```python
with bpy.context.temp_override(active_object=obj, selected_objects=[obj]):
    bpy.ops.object.something()
```

The old way (`bpy.ops.op(ctx_dict)`) was removed in Blender 4.0.

## Blender 5.x headless pitfalls (verified on 5.2 LTS)

| Symptom | Cause / fix |
|---|---|
| `'CYCLES'` missing from the engine enum | Dynamic enums via `bl_rna` don't list addon engines. Just assign: `scene.render.engine = 'CYCLES'` |
| EEVEE not found | The 5.x identifier is `'BLENDER_EEVEE'` (not `BLENDER_EEVEE_NEXT`) |
| glTF export fails without a format | In 5.2 `export_format` has no default — pass `'GLB'` explicitly |
| File won't save to `//path` | `//` is relative to the .blend; without a saved .blend it resolves nowhere. Use absolute paths |
| Scene not empty at start | Factory startup contains a cube/camera/light. `bpy.ops.wm.read_factory_settings(use_empty=True)` |
| Timers/deferred callbacks never fire | In `-b`, `bpy.app.timers` don't tick. Everything must be synchronous |
| Stale depsgraph | After edits: `bpy.context.view_layer.update()`; to read modifier results use evaluated objects: `obj.evaluated_get(bpy.context.evaluated_depsgraph_get())` |
| Render "doesn't see" an object | The object isn't linked to the view layer: `collection.objects.link(obj)` and the collection must be under `scene.collection.children` |
| Object "missing" right after `.link()` | `view_layer.objects` can be stale in `-b`; check membership via `obj.users_collection` / `collection.all_objects` instead |

## bmesh: the skeleton of any generator

```python
import bmesh, bpy

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)                      # or create_cone, create_uvsphere...
# ... operations ...
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)        # always, before writing out!
mesh = bpy.data.meshes.new("Thing")
bm.to_mesh(mesh); bm.free()
obj = bpy.data.objects.new("Thing", mesh)
ctx.root_collection.objects.link(obj)
mesh.shade_flat()                                        # low-poly = flat shading
```

For common shapes this is already wrapped:
`forge.lowpoly.create_box/create_cylinder/create_prism` (+ `extrude_faces`,
`inset_faces`, `bevel_edges`, `remove_doubles`, `apply_transforms`, `join`).

## Frequent bmesh.ops

```python
# Extrude a face and move it
res = bmesh.ops.extrude_face_region(bm, geom=[face])
verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=verts, vec=(0, 0, 0.5))

# Inset (panels, windows)
res = bmesh.ops.inset_region(bm, faces=faces, thickness=0.05, depth=-0.02)

# Bevel (soften a silhouette cheaply: segments=1)
bmesh.ops.bevel(bm, geom=edges, offset=0.02, segments=1, affect='EDGES')

# Merge duplicate vertices (after mirrors/seams)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)

# Scale/rotate part of the geometry
import mathutils
bmesh.ops.scale(bm, verts=verts, vec=(1, 1, 2))
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=mathutils.Matrix.Rotation(0.5, 3, 'Z'))
```

Select faces by normal/position, not by index (indices are unstable):

```python
top = [f for f in bm.faces if f.normal.z > 0.9]
```

## Applying transforms without operators

```python
mesh.transform(obj.matrix_basis)     # bake the current transform into the mesh
obj.matrix_basis.identity()
```

## Counting triangles (the way the validator does)

```python
deps = bpy.context.evaluated_depsgraph_get()
ev = obj.evaluated_get(deps)
me = ev.to_mesh()
tris = len(me.loop_triangles) if me.loop_triangles else sum(len(p.vertices) - 2 for p in me.polygons)
ev.to_mesh_clear()
```

## Manual UVs (for the palette)

```python
uv = mesh.uv_layers.new(name="UVMap")
for poly in mesh.polygons:
    for li in poly.loop_indices:
        uv.data[li].uv = (u, v)
```

## Determinism

Only `ctx.rng` (`random.Random(seed)`). No module-level `random.*`, no
`id()`, no dict ordering derived from Blender object hashes.
