"""Skins over a substrate: offset an assembly of solid parts outward into open surfaces.

Three things live here and the boundary between them is the point of the package:

* `skinning.skin` — the geometry. Offsets a body, laps, cleans and measures, and
  knows nothing about buildings. It is trimesh and numpy and runs headless.
* `skinning.rules` — every derivation. What a wall is, which faces each skin
  covers, and the join from the authored numbers to those predicates by name.
* `skinning.pipeline` — the seam. `run(parts, params)` takes plain data, reads no
  file, writes no file and prints nothing.

A host repo imports `rules` and `pipeline`, hands them its own parts and its own
parameter dict, and supplies its own reporting. `build.py` at the root of this
repo is one such caller — the test rig, with a transcribed substrate and an OBJ
writer — and it is deliberately outside the package, because none of it migrates.

**Nothing is re-exported here on purpose.** `import skinning` costs an empty
module; `from skinning import pipeline` is what pulls trimesh and manifold3d in.
That is the same containment `skinning/skin/__init__.py` gives shapely by
declining to re-export `clean`, applied one level up: a caller that wants the
geometry should have to say so.
"""
