"""Blender-side viewer: loads build/ into the scene. No geometry is authored here.

Every object it creates is tagged `skin_generated`, and `clear()` removes only
tagged objects. That is the whole safety property: nothing here can delete or
overwrite an object it did not itself import, so lights, cameras, hand-made
objects and — on the student-house side — live Bonsai IFC parts carrying
semantic data are never at risk.

Manifest entries carry a `role`. `skin` is generated output. `substrate` is a
throwaway copy of geometry that already exists elsewhere, emitted only when
`build(emit_substrate=True)` asked for it, and skipped by default here: where
the substrate is live geometry, importing it would put a second, dead copy of
every part beside the original.

    exec(open("/home/duncan/skin-test/blender/display.py").read())
    reload()                      # skins only
    reload(substrate=True)        # and the transcribed substrate, to check it
"""

import json
from pathlib import Path

import bpy

BUILD_DIR = Path("/home/duncan/skin-test/build")
TAG = "skin_generated"


def clear():
    """Remove objects this module imported. Never anything else."""
    for obj in [o for o in bpy.data.objects if TAG in o]:
        bpy.data.objects.remove(obj, do_unlink=True)


def _import_obj(path):
    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "obj_import"):  # Blender 4.x
        # forward=Y / up=Z disables OBJ's Y-up conversion: files are already Z-up
        bpy.ops.wm.obj_import(filepath=str(path), forward_axis="Y", up_axis="Z")
    else:  # Blender 3.x
        bpy.ops.import_scene.obj(filepath=str(path), axis_forward="Y", axis_up="Z")
    return [o for o in bpy.data.objects if o not in before]


def reload(substrate=False):
    """Clear previously imported objects and re-import the current build.

    Skins only unless `substrate=True`. See the module docstring for why the
    substrate is opt-in.
    """
    clear()
    manifest = json.loads((BUILD_DIR / "manifest.json").read_text())

    loaded, skipped = [], []
    for entry in manifest:
        role = entry.get("role", "skin")
        if role == "substrate" and not substrate:
            skipped.append(entry["name"])
            continue
        for obj in _import_obj(BUILD_DIR / entry["file"]):
            obj.name = entry["name"]
            obj[TAG] = True
            obj.display_type = "WIRE" if entry["display"] == "wire" else "TEXTURED"
            loaded.append(obj)

    print(f"loaded {len(loaded)}: {[o.name for o in loaded]}")
    if skipped:
        print(f"skipped {len(skipped)} substrate copies: {skipped}")
    return loaded


if __name__ == "__main__":
    reload()
