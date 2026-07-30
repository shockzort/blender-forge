# Recipe cookbook

## Anatomy of a recipe

```python
"""Parcel box: a basic delivery prop. Real-world size: ~0.3 m carton."""

PARAMS = {
    "size": (0.35, 0.28, 0.22),   # metres (X width, Y depth, Z height)
    "tape_width": 0.05,           # tape strip on the lid
    # no "palette" key → the project palette from forge.toml is inherited
    # (PARAMS overrides defaults, so "palette": None would break inheritance)
    "poly_budget": 200,
}

def build(ctx):
    """ctx.root_collection — the asset's root collection: everything linked
    into it gets exported. ctx.params — PARAMS merged over [defaults];
    ctx.rng — random.Random(ctx.seed); the seed comes from
    `bforge build --seed N`, it does not belong in PARAMS."""
    from forge import lowpoly, palette
    ...
```

A full living example with comments is produced by `bforge new <name>`
(template `templates/recipe.py`).

Discipline:

- Every tunable goes into `PARAMS`, commented, with units. No magic numbers
  inside `build()`.
- The file docstring says what the asset is and why; update it when the
  recipe changes.
- One recipe = one asset (or a small kit via `PARAMS["variant"]`).
- Object names are ASCII: `ParcelBox`, `ParcelBox_collider-convcolonly`.

## The iteration loop

1. `bforge build <name>` → read the JSON (last stdout line).
2. If `error` is set → fix from the traceback, build again. Don't hide
   errors in try/except.
3. `bforge preview <name>` → **Read every PNG**. Check: silhouette (does the
   object read?), proportions against reality (a door is 2.1 m!), colors,
   black faces (normals).
4. One edit = one hypothesis. Keep a running note: "roof too flat →
   increasing pitch". Three changes at once = you won't know what worked.
5. Read every entry in `validation.warnings`; "accepted deliberately" is a
   fine outcome, silently ignoring is not.
6. Final build — then tell the user: the GLB path, tris/budget, anything
   still debatable.

## Typical constructions

**Box-based props** (crates, mailboxes, bins): create_box → scale → inset
the top face → extrude down (cavity/lid) → bevel edges (offset 0.01–0.03,
segments=1) → palette per face group (by normal/height).

**Cylindrical** (posts, hydrants, wheels): create_cone (cap_ends=True,
segments 6–10 — more is wasted on low-poly) → extrude/scale sections along
the height.

**Building kit piece** (wall/corner/window): a wall slab of an exact modular
width (e.g. 2.0 m) → inset for the window opening → extrude inward → frames
as separate thin boxes. Pivot at the module's corner, on the floor (for grid
snapping in Godot).

**Collider**: a simplified box/convex hull as a child object named
`<Name>_collider-convcolonly`, no material, around the visible geometry. A
box is enough for simple props.

**Random detail** (wear, scatter): only `ctx.rng.uniform/choice`; put the
amplitude in PARAMS.

## Pre-delivery checklist

- [ ] build: status=ok, tris ≤ budget, warnings reviewed
- [ ] previews inspected by eye from all angles
- [ ] real-world dimensions (metres), meaningful pivot (usually bottom
      center; kit pieces — the corner)
- [ ] the "front" faces -Y
- [ ] a collider exists and is named with a suffix
- [ ] project palette used; ≤ 2 materials
- [ ] rebuilding produces the same result (determinism)
