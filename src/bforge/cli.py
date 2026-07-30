"""bforge command line interface.

Every subcommand prints exactly one JSON object as the LAST line of stdout,
matching the contract in implementation_plan.md §4.2:

    {"status": "ok|error", "artifacts": [...], "previews": [...],
     "validation": {...} | null, "blender_stderr_tail": "...",
     "error": "..." | null, "duration_sec": 1.23}

All human-readable progress/log lines go to stderr. Process exit code is 0
only when status == "ok" AND (validation is missing/None OR validation has
no blocking "errors").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bforge import config as bconfig
from bforge import runner as brunner


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _print_result(result: dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=False))
    ok = result.get("status") == "ok"
    validation = result.get("validation")
    if isinstance(validation, dict) and validation.get("errors"):
        ok = False
    return 0 if ok else 1


def _blender_missing_result() -> dict[str, Any]:
    result = brunner.empty_result()
    result["error"] = (
        "blender executable not found. Checked (in order): $BLENDER_PATH, "
        "forge.toml [blender].path, PATH. Set one of these to your Blender >=4.2 binary."
    )
    return result


def _resolve_recipe_path(name_or_path: str, paths: dict[str, Path]) -> Path:
    candidate = Path(name_or_path)
    if candidate.is_file():
        return candidate.resolve()
    candidate = paths["recipes_dir"] / name_or_path
    if candidate.is_file():
        return candidate.resolve()
    candidate = paths["recipes_dir"] / f"{name_or_path}.py"
    return candidate.resolve()


def _parse_size(text: str) -> tuple[int, int]:
    try:
        w_str, h_str = text.lower().split("x")
        return int(w_str), int(h_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid size {text!r}, expected WxH (e.g. 640x480)") from exc


def _merge_build_results(results: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    if len(results) == 1:
        return results[0]
    merged = brunner.empty_result()
    merged["status"] = "ok" if all(r.get("status") == "ok" for r in results) else "error"
    merged["artifacts"] = [a for r in results for a in r.get("artifacts", [])]
    merged["previews"] = [p for r in results for p in r.get("previews", [])]
    merged["validation"] = {name: r.get("validation") for name, r in zip(names, results)}
    merged["blender_stderr_tail"] = "\n---\n".join(
        r.get("blender_stderr_tail", "") for r in results if r.get("blender_stderr_tail")
    )
    errors = [f"{name}: {r.get('error')}" for name, r in zip(names, results) if r.get("error")]
    merged["error"] = "; ".join(errors) if errors else None
    merged["duration_sec"] = round(sum(r.get("duration_sec", 0.0) for r in results), 3)
    return merged


# --- subcommands -----------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    blender = bconfig.find_blender(config)
    if not blender:
        return _print_result(_blender_missing_result())

    _log(f"doctor: using blender at {blender}")
    job = {"mode": "doctor"}
    result = brunner.run_job(job, blender, timeout=args.timeout)

    diag = result.get("validation") or {}
    version_str = diag.get("blender_version", "")
    if version_str:
        try:
            major, minor = (int(x) for x in version_str.split(".")[:2])
        except ValueError:
            major, minor = (0, 0)
        if (major, minor) < (4, 2):
            result["status"] = "error"
            extra = f"blender version {version_str} is below the minimum supported 4.2"
            result["error"] = f"{result['error']}; {extra}" if result.get("error") else extra
        _log(f"doctor: blender {version_str}, checks={diag.get('checks')}")

    return _print_result(result)


def cmd_new(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    paths = bconfig.project_paths(config)
    paths["recipes_dir"].mkdir(parents=True, exist_ok=True)
    target = paths["recipes_dir"] / f"{args.name}.py"

    result = brunner.empty_result()
    if target.exists() and not args.force:
        result["error"] = f"{target} already exists (use --force to overwrite)"
        return _print_result(result)

    template_path = bconfig.find_forge_repo_root() / "templates" / "recipe.py"
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("__RECIPE_NAME__", args.name)
    target.write_text(text, encoding="utf-8")

    result["status"] = "ok"
    result["artifacts"] = [str(target)]
    result["duration_sec"] = 0.0
    _log(f"new: created recipe {target}")
    return _print_result(result)


def cmd_build(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    paths = bconfig.project_paths(config)
    blender = bconfig.find_blender(config)
    if not blender:
        return _print_result(_blender_missing_result())

    if args.all:
        recipe_paths = sorted(paths["recipes_dir"].glob("*.py"))
    else:
        recipe_paths = [_resolve_recipe_path(r, paths) for r in args.recipes]

    if not recipe_paths:
        result = brunner.empty_result()
        result["error"] = "no recipes to build (pass recipe names/paths, or use --all)"
        return _print_result(result)

    defaults = bconfig.defaults(config)
    results: list[dict[str, Any]] = []
    names: list[str] = []
    for recipe_path in recipe_paths:
        if not recipe_path.is_file():
            res = brunner.empty_result()
            res["error"] = f"recipe not found: {recipe_path}"
            results.append(res)
            names.append(recipe_path.stem)
            _log(f"build: {recipe_path.stem}: recipe not found")
            continue

        output_path = paths["output_dir"] / f"{recipe_path.stem}.glb"
        job = {
            "mode": "build",
            "recipe_path": str(recipe_path),
            "output_path": str(output_path),
            "defaults": defaults,
            "seed": args.seed,
        }
        _log(f"build: {recipe_path.stem}: running...")
        res = brunner.run_job(job, blender, timeout=args.timeout)
        results.append(res)
        names.append(recipe_path.stem)
        _log(f"build: {recipe_path.stem}: status={res.get('status')} error={res.get('error')}")

    return _print_result(_merge_build_results(results, names))


def cmd_preview(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    paths = bconfig.project_paths(config)
    blender = bconfig.find_blender(config)
    if not blender:
        return _print_result(_blender_missing_result())

    recipe_path = _resolve_recipe_path(args.recipe, paths)
    if not recipe_path.is_file():
        result = brunner.empty_result()
        result["error"] = f"recipe not found: {recipe_path}"
        return _print_result(result)

    previews_dir = paths["previews_dir"] / recipe_path.stem
    width, height = _parse_size(args.size)
    job = {
        "mode": "preview",
        "recipe_path": str(recipe_path),
        "previews_dir": str(previews_dir),
        "angles": args.angles,
        "size": [width, height],
        "defaults": bconfig.defaults(config),
        "seed": args.seed,
    }
    _log(f"preview: {recipe_path.stem}: rendering {args.angles} angle(s) at {width}x{height}...")
    result = brunner.run_job(job, blender, timeout=args.timeout)
    return _print_result(result)


def cmd_run(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    blender = bconfig.find_blender(config)
    if not blender:
        return _print_result(_blender_missing_result())

    script_path = Path(args.script).resolve()
    if not script_path.is_file():
        result = brunner.empty_result()
        result["error"] = f"script not found: {script_path}"
        return _print_result(result)

    job = {
        "mode": "run",
        "script_path": str(script_path),
        "defaults": bconfig.defaults(config),
        "seed": args.seed,
    }
    _log(f"run: executing {script_path}...")
    result = brunner.run_job(job, blender, timeout=args.timeout)
    return _print_result(result)


def cmd_validate(args: argparse.Namespace) -> int:
    config = bconfig.load_config()
    paths = bconfig.project_paths(config)
    blender = bconfig.find_blender(config)
    if not blender:
        return _print_result(_blender_missing_result())

    defaults = bconfig.defaults(config)
    target = Path(args.target)
    if target.suffix.lower() == ".glb":
        job = {
            "mode": "validate_glb",
            "glb_path": str(target.resolve()),
            "poly_budget": defaults.get("poly_budget", 300),
        }
    else:
        recipe_path = _resolve_recipe_path(args.target, paths)
        if not recipe_path.is_file():
            result = brunner.empty_result()
            result["error"] = f"target not found (not a .glb, and no recipe matches): {args.target}"
            return _print_result(result)
        job = {
            "mode": "validate_recipe",
            "recipe_path": str(recipe_path),
            "defaults": defaults,
            "seed": args.seed,
        }

    _log(f"validate: {args.target}...")
    result = brunner.run_job(job, blender, timeout=args.timeout)
    return _print_result(result)


# --- argument parsing --------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    timeout_parent = argparse.ArgumentParser(add_help=False)
    timeout_parent.add_argument(
        "--timeout", type=float, default=brunner.DEFAULT_TIMEOUT,
        help=f"Blender subprocess timeout in seconds (default: {brunner.DEFAULT_TIMEOUT:g})",
    )

    parser = argparse.ArgumentParser(
        prog="bforge",
        description="Asset-as-code CLI: drives headless Blender to build, preview, and validate game assets for Godot.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser(
        "doctor", parents=[timeout_parent],
        help="check the environment: blender found, version >= 4.2, headless render + glTF export probes",
    )
    p_doctor.set_defaults(func=cmd_doctor)

    p_new = sub.add_parser("new", help="create a new recipe from templates/recipe.py")
    p_new.add_argument("name", help="recipe name (file will be <recipes_dir>/<name>.py)")
    p_new.add_argument("--force", action="store_true", help="overwrite if the recipe already exists")
    p_new.set_defaults(func=cmd_new)

    p_build = sub.add_parser(
        "build", parents=[timeout_parent],
        help="build one or more recipes into GLB files (+ validation)",
    )
    p_build.add_argument("recipes", nargs="*", help="recipe names or paths (omit with --all)")
    p_build.add_argument("--all", action="store_true", help="build every recipe in recipes_dir")
    p_build.add_argument("--seed", type=int, default=0, help="deterministic seed passed to the recipe (default: 0)")
    p_build.set_defaults(func=cmd_build)

    p_preview = sub.add_parser(
        "preview", parents=[timeout_parent],
        help="render N turntable angle previews (PNG) for a recipe",
    )
    p_preview.add_argument("recipe", help="recipe name or path")
    p_preview.add_argument("--angles", type=int, default=4, help="number of azimuth angles to render (default: 4)")
    p_preview.add_argument("--size", default="640x480", help="render resolution WxH (default: 640x480)")
    p_preview.add_argument("--seed", type=int, default=0, help="deterministic seed passed to the recipe (default: 0)")
    p_preview.set_defaults(func=cmd_preview)

    p_run = sub.add_parser(
        "run", parents=[timeout_parent],
        help="run an arbitrary bpy script inside headless Blender (escape hatch, same JSON contract)",
    )
    p_run.add_argument("script", help="path to a .py script")
    p_run.add_argument("--seed", type=int, default=0, help="deterministic seed exposed via ctx.seed (default: 0)")
    p_run.set_defaults(func=cmd_run)

    p_validate = sub.add_parser(
        "validate", parents=[timeout_parent],
        help="validate an existing .glb file, or a recipe (built in-memory, not exported)",
    )
    p_validate.add_argument("target", help="path to a .glb, or a recipe name/path")
    p_validate.add_argument("--seed", type=int, default=0, help="deterministic seed for recipe targets (default: 0)")
    p_validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # CLI-level failure, not a Blender-side one
        result = brunner.empty_result()
        result["error"] = f"bforge CLI error: {exc!r}"
        return _print_result(result)


if __name__ == "__main__":
    sys.exit(main())
