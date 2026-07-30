"""forge - the bpy-side asset library.

This package runs ONLY inside Blender's own bundled Python (it imports bpy
and bmesh). It is never installed as a pip/uv dependency; runner_entry.py
reaches it by inserting this repo's src/ directory onto sys.path before
importing anything from here. Stdlib + bpy/bmesh only - no third-party
dependencies (see implementation plan §6.1).
"""

__version__ = "0.1.0"
