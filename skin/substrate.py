"""Substrates the skin is built over. Grow this as the geometry gets harder.

Shapes are cut from boxes with manifold3d booleans, so a new substrate costs a
couple of lines and no hand-written triangulation.
"""

from __future__ import annotations

import numpy as np
import trimesh
from trimesh.transformations import translation_matrix


WALL = "wall"
ROOF = "roof"


class AmbiguousPart(ValueError):
    """A part that is neither clearly a wall nor clearly a roof."""


def horizontality(part: trimesh.Trimesh) -> float:
    """Fraction of a part's surface area that faces up or down.

    0 for a pure wall, 1 for a pure slab. Weighted by area, so the large faces
    decide it, and read from face normals rather than from bounds. Bounds cannot
    do this job: an axis-aligned box around a wall that runs diagonally in plan
    has both horizontal extents inflated until the height is the smallest of the
    three, and the wall reads as a slab.
    """
    area = part.area_faces
    return float((area * np.abs(part.face_normals[:, 2])).sum() / area.sum())


def _thinnest_side(part: trimesh.Trimesh):
    """Sorted oriented-bounding-box extents, and how vertical the thinnest is.

    Oriented, not axis-aligned, for the same reason as above — on a diagonal
    wall the OBB recovers the true thickness where the AABB reports the span.
    """
    box = part.bounding_box_oriented
    extents = np.asarray(box.primitive.extents, dtype=float)
    order = np.argsort(extents)
    axis = box.primitive.transform[:3, order[0]]
    return extents[order], abs(float(axis[2] / np.linalg.norm(axis)))


def classify(part: trimesh.Trimesh, margin: float = 0.05, aspect: float = 0.85) -> str:
    """WALL or ROOF, decided from the part's own geometry. Never guesses.

    Two independent measures must agree: `horizontality`, and whether the
    thinnest side of the oriented bounding box points up — a slab is thin
    vertically, a wall is thin horizontally. Any of

      * a part with no clear thin direction (its two smallest extents within
        `aspect` of each other, so it is block-like rather than panel-like),
      * a horizontality within `margin` of the halfway mark,
      * the two measures disagreeing,

    raises `AmbiguousPart` carrying the numbers instead of picking a side.
    Guessing is the expensive failure: a misclassified part skins silently and
    wrongly somewhere inside a large model, which is the class of bug that made
    the old student-house module so hard to debug.
    """
    extents, vertical = _thinnest_side(part)
    if extents[0] > aspect * extents[1]:
        raise AmbiguousPart(
            f"no clear thin direction: sorted extents "
            f"{np.round(extents, 4).tolist()} — block-like, neither panel nor slab"
        )

    horizontal = horizontality(part)
    if abs(horizontal - 0.5) < margin:
        raise AmbiguousPart(
            f"horizontality {horizontal:.3f} is within {margin} of the halfway mark"
        )

    by_area = ROOF if horizontal > 0.5 else WALL
    by_shape = ROOF if vertical > 0.5 else WALL
    if by_area != by_shape:
        raise AmbiguousPart(
            f"measures disagree: horizontality {horizontal:.3f} says {by_area}, "
            f"thinnest OBB side (verticality {vertical:.3f}) says {by_shape}"
        )
    return by_area


def _box(extents, center) -> trimesh.Trimesh:
    return trimesh.creation.box(extents=extents, transform=translation_matrix(center))


def cube(size: float = 2.0, center=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    """Axis-aligned cube."""
    return _box((size, size, size), center)


def polyhedron(vertices, faces) -> trimesh.Trimesh:
    """Build a part from polygon loops, in any winding.

    Loops are fan-triangulated (valid for the convex faces used here) and the
    result is oriented outward, so transcribed face lists need not be wound
    consistently.
    """
    tris = [(f[0], f[i], f[i + 1]) for f in faces for i in range(1, len(f) - 1)]
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, dtype=float), faces=tris)
    mesh.fix_normals()
    return mesh


def prism(lo, hi, snap: float | None = 1e-6) -> trimesh.Trimesh:
    """Axis-aligned rectangular prism from its bounds.

    `snap` quantises the bounds to a grid (1 µm by default). Modelled parts
    arrive with faces that miss each other by a few hundred nanometres, and
    those near-misses become sliver faces in a union and near-parallel plane
    pairs in the offset solve; snapping makes intended-coincident faces exactly
    coincident. Pass `snap=None` to keep the bounds verbatim.
    """
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    if snap:
        lo, hi = np.round(lo / snap) * snap, np.round(hi / snap) * snap
    return _box(hi - lo, (lo + hi) / 2.0)


def union(parts: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    """Merge parts into one substrate.

    Faces where parts touch are interior to the result and disappear here, so
    the offset never sees them and no skin is generated between parts.
    """
    return trimesh.boolean.union(parts)


def l_block(arm: float = 2.0, width: float = 1.0, height: float = 1.0) -> trimesh.Trimesh:
    """Extruded L: the simplest substrate with a reflex (concave) edge."""
    notch = arm - width
    return trimesh.boolean.difference(
        [
            _box((arm, arm, height), (arm / 2, arm / 2, height / 2)),
            _box((notch, notch, 3 * height), ((arm + width) / 2, (arm + width) / 2, height / 2)),
        ]
    )


def u_block(size: float = 3.0, slot: float = 1.0, height: float = 1.0) -> trimesh.Trimesh:
    """Extruded U: a concave pocket, so offsets past `slot / 2` self-intersect."""
    depth = size - (size - slot) / 2.0
    return trimesh.boolean.difference(
        [
            _box((size, size, height), (size / 2, size / 2, height / 2)),
            _box((slot, depth, 3 * height), (size / 2, size - depth / 2, height / 2)),
        ]
    )
