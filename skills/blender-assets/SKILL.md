---
name: blender-assets
description: Generates low-poly 3D game assets as deterministic Python recipes built by the bforge CLI in headless Blender and exported to Godot-ready GLB. Use when the user asks to create or modify a 3D model, prop, environment piece, or texture for a game.
argument-hint: "[asset description]"
license: MIT
compatibility: Requires the bforge CLI (blender-forge repo) and Blender >= 4.2; the consuming project should have a forge.toml.
allowed-tools: Read, Bash(bforge *)
---

# Blender Assets: assets-as-code

Every asset is a deterministic Python recipe in the game repo
(`<recipes_dir>/<name>.py`, usually `assets/recipes/`). You write or edit the
recipe, `bforge` builds the GLB and preview renders, you LOOK at the previews
(Read the PNGs), and iterate. Don't hand-edit GLBs and don't build production
assets through a live Blender session: a recipe in git can be regenerated,
diffed and tweaked forever; a session cannot.

## When to trigger

- The user asks to create, modify, or fix a 3D model, prop, environment kit
  piece, or palette texture for their game.
- The user asks to adjust an existing recipe (resize, recolor, add detail).
- Do NOT use for: 2D/UI art, editing third-party asset-pack files, or
  projects with no `forge.toml` (offer to set one up first — see the
  blender-forge README).

## Instructions

1. **Check the environment** (once per session): `bforge doctor` — the last
   stdout line is JSON; expect `"status": "ok"`. If not, fix what `error`
   says (usually `BLENDER_PATH` or a missing forge.toml).
2. **Find the project config**: `forge.toml` at the repo root defines the
   project palette, budgets, and directories. Pick asset colors from the
   project palette rather than inventing new ones — palette consistency is
   what makes a low-poly set look coherent; add new colors only when the
   user asks.
3. **Create or edit the recipe**: `bforge new <name>` scaffolds
   `<recipes_dir>/<name>.py`. Contract: a `PARAMS` dict (every tunable, with
   comments) plus `def build(ctx)`. Read
   [references/recipe-cookbook.md](references/recipe-cookbook.md) before
   writing your first recipe in a session.
4. **Build**: `bforge build <name>`. Read the JSON: `validation`
   (tris/budget, transforms, UV, warnings) and `error` (a full traceback —
   fix the root cause rather than wrapping code in try/except).
5. **Look with your eyes**: `bforge preview <name>` renders turntable PNGs.
   Open them (Read). Check: silhouette, proportions against real-world
   sizes, readability at gameplay distance, palette colors, no black
   (inverted-normal) faces.
6. **Iterate**: one hypothesis — one edit — one rebuild. Changing three
   things at once means you won't know what worked.
7. **Finish**: a final `bforge build` with no warnings (or with warnings you
   explicitly accept and mention). Tell the user the GLB path and that Godot
   imports it on editor focus (or `godot --headless --import`).

## Hard rules (violating any of these produces a broken or off-style asset)

- **Metres, 1 unit = 1 m.** A parcel is ~0.3 m, a door ~2.1 m, a floor ~3 m.
  Check the bounding box in `validation`.
- **The asset faces -Y** in Blender. Godot's importer (with the preset's
  `export_yup`) turns that into the engine's +Z "front" — hand-rotating for
  the engine breaks this.
- **Transforms applied**: scale=1, rotation=0 on every object (the validator
  blocks otherwise; use `forge.lowpoly.apply_transforms`).
- **Triangle budget** comes from `PARAMS["poly_budget"]`: props 100–500,
  buildings/kit pieces 500–2000. Don't optimize below silhouette
  readability.
- **Colliders via name suffixes**: `-convcolonly` (convex, for props),
  `-colonly` (exact concave, for static level geometry). Full table:
  [references/godot-conventions.md](references/godot-conventions.md).
- **Export only through `forge.export.export_godot_glb`** — the preset is
  already Godot-correct. Never enable Draco/meshopt/gltfpack/gpu_instances:
  Godot 4.7 silently drops those extensions' data.
- **Materials**: palette atlas via `forge.palette` (default) or vertex
  colors (a deliberate choice — see
  [references/palette-workflow.md](references/palette-workflow.md)).
  Procedural Blender node setups do not survive glTF export.
- **Determinism**: randomness only through `ctx.rng` (seeded). Rebuilding
  with the same seed must produce the same GLB.

## Writing recipe code

Use `bpy.data` + `bmesh`, not `bpy.ops`: operators depend on UI context and
fail unpredictably in headless mode. When an operator is unavoidable, wrap
it in `context.temp_override()`. Prefer the ready-made helpers in the
`forge` package (session/lowpoly/palette/material/export). For bmesh
patterns and Blender 5.x headless pitfalls, read
[references/bpy-patterns.md](references/bpy-patterns.md).

## Edge cases and debugging

- `status: error` → the full traceback is in the JSON `error` field. Fix the
  root cause; don't silence it.
- Black/inverted faces in previews → `bmesh.ops.recalc_face_normals`.
- Asset is the "wrong size" in Godot → transforms not applied, or units
  aren't metres.
- Model imports without colors → UVs outside [0,1] or a non-palette
  material; check `validation.warnings`.
- Asset invisible in previews → the object was never linked into the asset's
  root collection (`ctx.root_collection.objects.link(obj)`).
- Colliders invisible in previews — that's correct: objects suffixed
  `-colonly`/`-convcolonly`/`-navmesh`/`-noimp` are hidden from renders,
  just as Godot's import would drop them.
- Want a different random variation → rebuild with `--seed N` (the seed
  arrives via `ctx.seed`/`ctx.rng`; it does not belong in `PARAMS`).
