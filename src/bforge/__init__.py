"""bforge - CLI for the blender-forge asset pipeline.

This package only uses the Python standard library: it shells out to a
Blender binary and never imports bpy directly (bpy is not installed in this
environment - it lives inside the Blender executable's own bundled Python).
"""

__version__ = "0.1.0"
