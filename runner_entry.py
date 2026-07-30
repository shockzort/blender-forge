"""Entry point executed INSIDE headless Blender by bforge/runner.py:

    blender --background --factory-startup --python runner_entry.py -- <job.json path>

Reads a job description from the JSON file given as the sole argument after
`--`, executes it (build / preview / validate_recipe / validate_glb / run /
doctor), and writes a JSON result to job["result_path"]. Any exception
anywhere in the job is caught here and turned into status="error" with the
full traceback in "error" - Blender's own stdout is too noisy to rely on, so
the result file is the only channel bforge reads.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import bpy  # noqa: E402  (must come after sys.path setup, though bpy is always importable here)

from forge import export as fexport  # noqa: E402
from forge import preview as fpreview  # noqa: E402
from forge import session  # noqa: E402
from forge import validate as fvalidate  # noqa: E402


def _load_job() -> dict[str, Any]:
    argv = sys.argv
    if "--" not in argv:
        raise SystemExit("runner_entry: expected '-- <job.json path>' on the command line")
    args = argv[argv.index("--") + 1:]
    if not args:
        raise SystemExit("runner_entry: missing job file path after '--'")
    job_path = Path(args[0])
    with open(job_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_result(result_path: str, result: dict[str, Any]) -> None:
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)


def _import_recipe(recipe_path: str) -> ModuleType:
    path = Path(recipe_path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load recipe module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _merged_params(job: dict[str, Any], recipe_module: ModuleType) -> dict[str, Any]:
    params: dict[str, Any] = dict(job.get("defaults") or {})
    params.update(getattr(recipe_module, "PARAMS", {}) or {})
    if job.get("param_overrides"):
        params.update(job["param_overrides"])
    return params


def _resolve_target_collection(build_return: Any, root_collection: "bpy.types.Collection") -> "bpy.types.Collection":
    if isinstance(build_return, bpy.types.Collection):
        return build_return
    return root_collection


def _build_recipe(job: dict[str, Any]) -> tuple["bpy.types.Collection", session.Context]:
    recipe_module = _import_recipe(job["recipe_path"])
    build_fn = getattr(recipe_module, "build", None)
    if not callable(build_fn):
        raise AttributeError(f"recipe {job['recipe_path']} has no build(ctx) function")

    seed = job.get("seed", 0)
    params = _merged_params(job, recipe_module)
    ctx = session.new_context(seed=seed, params=params)

    result_obj = build_fn(ctx)
    target_collection = _resolve_target_collection(result_obj, ctx.root_collection)
    return target_collection, ctx


def _run_build(job: dict[str, Any]) -> dict[str, Any]:
    target_collection, ctx = _build_recipe(job)
    poly_budget = ctx.params.get("poly_budget", job.get("poly_budget", fvalidate.DEFAULT_POLY_BUDGET))
    validation = fvalidate.validate_collection(target_collection, poly_budget=poly_budget)

    out: dict[str, Any] = {"validation": validation, "artifacts": [], "previews": []}
    if validation["ok"]:
        output_path = job["output_path"]
        fexport.export_godot_glb(output_path, collection=target_collection)
        out["artifacts"] = [output_path]
        out["status"] = "ok"
    else:
        out["status"] = "error"
        out["error"] = "validation failed: " + "; ".join(validation["errors"])
    return out


def _run_preview(job: dict[str, Any]) -> dict[str, Any]:
    target_collection, ctx = _build_recipe(job)
    angles = int(job.get("angles", 4))
    size = tuple(job.get("size", [640, 480]))
    previews_dir = job["previews_dir"]

    paths = fpreview.render_turntable(target_collection, previews_dir, angles=angles, size=size)

    poly_budget = ctx.params.get("poly_budget", fvalidate.DEFAULT_POLY_BUDGET)
    validation = fvalidate.validate_collection(target_collection, poly_budget=poly_budget)

    return {
        "status": "ok",
        "artifacts": [],
        "previews": [str(p) for p in paths],
        "validation": validation,
    }


def _run_validate_recipe(job: dict[str, Any]) -> dict[str, Any]:
    target_collection, ctx = _build_recipe(job)
    poly_budget = ctx.params.get("poly_budget", job.get("poly_budget", fvalidate.DEFAULT_POLY_BUDGET))
    validation = fvalidate.validate_collection(target_collection, poly_budget=poly_budget)
    return {
        "status": "ok" if validation["ok"] else "error",
        "artifacts": [],
        "previews": [],
        "validation": validation,
        "error": None if validation["ok"] else "validation failed: " + "; ".join(validation["errors"]),
    }


def _run_validate_glb(job: dict[str, Any]) -> dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    root = bpy.data.collections.new("Imported")
    scene.collection.children.link(root)

    view_layer = bpy.context.view_layer
    with bpy.context.temp_override(scene=scene, view_layer=view_layer):
        bpy.ops.import_scene.gltf(filepath=job["glb_path"])

    imported = list(bpy.context.selected_objects) or [o for o in scene.collection.objects]
    for obj in imported:
        for coll in list(obj.users_collection):
            if coll is not root:
                coll.objects.unlink(obj)
        if obj.name not in root.objects:
            root.objects.link(obj)

    poly_budget = job.get("poly_budget", fvalidate.DEFAULT_POLY_BUDGET)
    validation = fvalidate.validate_collection(root, poly_budget=poly_budget)
    return {
        "status": "ok" if validation["ok"] else "error",
        "artifacts": [],
        "previews": [],
        "validation": validation,
        "error": None if validation["ok"] else "validation failed: " + "; ".join(validation["errors"]),
    }


def _run_script(job: dict[str, Any]) -> dict[str, Any]:
    seed = job.get("seed", 0)
    params = job.get("defaults") or {}
    ctx = session.new_context(seed=seed, params=params)

    script_path = Path(job["script_path"]).resolve()
    code = script_path.read_text(encoding="utf-8")
    script_globals = {
        "__name__": "__main__",
        "__file__": str(script_path),
        "bpy": bpy,
        "ctx": ctx,
    }
    exec(compile(code, str(script_path), "exec"), script_globals)

    return {
        "status": "ok",
        "artifacts": list(ctx.artifacts),
        "previews": list(ctx.previews),
        "validation": None,
    }


def _run_doctor(job: dict[str, Any]) -> dict[str, Any]:
    """Environment sanity probe: real headless render + real glTF export in
    a throwaway scene. Deliberately implemented with raw bpy/bmesh (no
    `forge` import, unlike every other mode here) so it stays a pure "does
    Blender itself work" check, independent of the asset library's own
    correctness - if `forge` has a bug, `doctor` should still say Blender
    is fine."""
    import bmesh
    from mathutils import Vector

    tmp_dir = Path(job.get("tmp_dir", "/tmp"))
    tmp_dir.mkdir(parents=True, exist_ok=True)

    diag: dict[str, Any] = {
        "blender_version": bpy.app.version_string,
        "python_version": sys.version,
        "checks": {},
        "ok": False,
    }

    scene, _root = session.reset_scene(seed=0)

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    mesh = bpy.data.meshes.new("DoctorMesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("DoctorCube", mesh)
    scene.collection.objects.link(obj)

    mat = bpy.data.materials.new("DoctorMat")
    mat.use_nodes = True
    obj.data.materials.append(mat)

    render_path = tmp_dir / "doctor_render.png"
    try:
        scene.render.engine = 'BLENDER_EEVEE'  # direct assignment; addon engines are not enum-visible in -b
        scene.render.resolution_x = 64
        scene.render.resolution_y = 64
        scene.render.image_settings.file_format = 'PNG'

        cam_data = bpy.data.cameras.new("DoctorCam")
        cam = bpy.data.objects.new("DoctorCam", cam_data)
        scene.collection.objects.link(cam)
        cam.location = (3.0, -3.0, 3.0)
        direction = Vector((0.0, 0.0, 0.0)) - cam.location
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        scene.camera = cam

        sun_data = bpy.data.lights.new("DoctorSun", type='SUN')
        sun = bpy.data.objects.new("DoctorSun", sun_data)
        scene.collection.objects.link(sun)

        scene.render.filepath = str(render_path)
        with bpy.context.temp_override(scene=scene):
            bpy.ops.render.render(write_still=True)
        diag["checks"]["headless_render"] = render_path.exists() and render_path.stat().st_size > 0
    except Exception as exc:
        diag["checks"]["headless_render"] = False
        diag["checks"]["headless_render_error"] = repr(exc)

    glb_path = tmp_dir / "doctor_export.glb"
    try:
        for other in scene.collection.all_objects:
            other.select_set(False)
        obj.select_set(True)
        with bpy.context.temp_override(
            active_object=obj,
            selected_objects=[obj],
            selected_editable_objects=[obj],
            view_layer=bpy.context.view_layer,
            scene=scene,
        ):
            bpy.ops.export_scene.gltf(filepath=str(glb_path), use_selection=True, export_format='GLB')
        diag["checks"]["gltf_export"] = glb_path.exists() and glb_path.stat().st_size > 0
    except Exception as exc:
        diag["checks"]["gltf_export"] = False
        diag["checks"]["gltf_export_error"] = repr(exc)

    diag["ok"] = all(v is True for k, v in diag["checks"].items() if not k.endswith("_error"))
    return diag


_MODE_HANDLERS = {
    "build": _run_build,
    "preview": _run_preview,
    "validate_recipe": _run_validate_recipe,
    "validate_glb": _run_validate_glb,
    "run": _run_script,
}


def main() -> None:
    start = time.perf_counter()
    job = _load_job()
    result: dict[str, Any] = {
        "status": "error",
        "artifacts": [],
        "previews": [],
        "validation": None,
        "blender_stderr_tail": "",
        "error": None,
        "duration_sec": 0.0,
    }
    try:
        mode = job.get("mode")
        if mode == "doctor":
            diag = _run_doctor(job)
            result["validation"] = diag
            result["status"] = "ok" if diag.get("ok") else "error"
            if not diag.get("ok"):
                result["error"] = f"doctor checks failed: {diag.get('checks')}"
        elif mode in _MODE_HANDLERS:
            result.update(_MODE_HANDLERS[mode](job))
        else:
            raise ValueError(f"unknown job mode: {mode!r}")
    except Exception:
        result["status"] = "error"
        result["error"] = traceback.format_exc()

    result["duration_sec"] = round(time.perf_counter() - start, 3)
    _write_result(job["result_path"], result)


if __name__ == "__main__":
    main()
