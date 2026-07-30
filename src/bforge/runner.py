"""Runs a "job" inside headless Blender and reads back its JSON result.

Mechanics (see docs §4.2 of the implementation plan): we invoke

    <blender> --background --factory-startup --python runner_entry.py -- <job.json path>

Blender's own stdout is noisy (version banners, addon spam, glTF exporter
progress, ...), so runner_entry.py never relies on stdout for the result: it
writes a JSON file to a temp path we hand it, and this module reads that file
back. Blender's stderr tail is always captured and forwarded so failures are
diagnosable even when the result file could not be written.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from bforge import config as bconfig

DEFAULT_TIMEOUT = 120.0
STDERR_TAIL_LINES = 60


def empty_result() -> dict[str, Any]:
    """A JSON-contract-shaped result, defaulting to a failure state."""
    return {
        "status": "error",
        "artifacts": [],
        "previews": [],
        "validation": None,
        "blender_stderr_tail": "",
        "error": None,
        "duration_sec": 0.0,
    }


def _tail(text: str | None, n_lines: int = STDERR_TAIL_LINES) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])


def run_job(job: dict[str, Any], blender_path: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Runs `job` (a dict with at least a "mode" key, see runner_entry.py)
    inside headless Blender and returns a dict matching the JSON contract.

    Never raises for "expected" failure modes (blender crash, timeout,
    missing result file, recipe exception) - those are all reported as
    status="error" results. May raise if the blender-forge repo itself is
    misconfigured (e.g. runner_entry.py missing).
    """
    repo_root = bconfig.find_forge_repo_root()
    runner_entry = repo_root / "runner_entry.py"

    result = empty_result()
    start = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="bforge-") as tmp:
        tmp_path = Path(tmp)
        job_path = tmp_path / "job.json"
        result_path = tmp_path / "result.json"

        job = dict(job)
        job["result_path"] = str(result_path)
        job.setdefault("tmp_dir", str(tmp_path))
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")

        cmd = [
            blender_path,
            "--background",
            "--factory-startup",
            "--python",
            str(runner_entry),
            "--",
            str(job_path),
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            stderr_tail = _tail(proc.stderr)
            if result_path.exists():
                try:
                    data = json.loads(result_path.read_text(encoding="utf-8"))
                    result.update(data)
                except (json.JSONDecodeError, OSError) as exc:
                    result["status"] = "error"
                    result["error"] = f"result file could not be parsed: {exc!r}"
                if not result.get("blender_stderr_tail"):
                    result["blender_stderr_tail"] = stderr_tail
            else:
                result["status"] = "error"
                result["blender_stderr_tail"] = stderr_tail
                result["error"] = (
                    f"blender exited with code {proc.returncode} without writing a result file.\n"
                    f"--- stdout tail ---\n{_tail(proc.stdout)}\n"
                    f"--- stderr tail ---\n{stderr_tail}"
                )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            result["status"] = "error"
            result["blender_stderr_tail"] = _tail(stderr)
            result["error"] = f"blender timed out after {timeout}s (job mode={job.get('mode')!r})"
        except FileNotFoundError as exc:
            result["status"] = "error"
            result["error"] = f"failed to launch blender at {blender_path!r}: {exc!r}"

    result["duration_sec"] = round(time.perf_counter() - start, 3)
    return result
