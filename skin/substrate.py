"""Substrates the skin is built over. Grow this as the geometry gets harder.

Shapes are cut from boxes with manifold3d booleans, so a new substrate costs a
couple of lines and no hand-written triangulation.
"""

from __future__ import annotations

from pathlib import Path

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


def classify(part: trimesh.Trimesh, margin: float, aspect: float) -> str:
    """WALL or ROOF, decided from the part's own geometry. Never guesses.

    `margin` and `aspect` are required, not defaulted: they are authored
    parameters (`classify` in `skin-parameters.yaml`), and a default pair here
    would be exactly the hidden default the parameter layer exists to abolish —
    the thresholds that decide whether a part raises or silently skins would then
    have two sources. `build.classifier()` binds them once.

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


def role_of(classify, bodies: list) -> str:
    """Classify one element — its bodies unioned — and name it if it is ambiguous.

    `classify` raises with the numbers but no identity, because a part is only
    geometry to it. In a bake of three dozen bodies that is not enough to act on:
    the raise has to say which object to go and look at, or the reader is left
    matching a horizontality against every part by hand. Both callers
    (`build.group_caps` and `Faces.roles`) classify an element exactly this way,
    so the union and the naming live here rather than twice over.
    """
    body = bodies[0] if len(bodies) == 1 else union(bodies)
    try:
        return classify(body)
    except AmbiguousPart as ambiguous:
        name = bodies[0].metadata.get("object") or bodies[0].metadata.get("name")
        raise AmbiguousPart(f"{name or 'unnamed part'}: {ambiguous}") from ambiguous


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


def _parse_obj(text: str):
    """`(vertices, [(name, [face loops])])` from an OBJ, indices resolved 0-based.

    Hand-written rather than handed to `trimesh.load`, which in trimesh 5.0.0
    silently merges every `o` group into one mesh named after the *first* group:
    a two-object file comes back as one geometry called `Wall_A` holding both
    bodies. A loader that mislabels parts without saying so is the exact failure
    this codebase raises about everywhere else, and object identity is load
    bearing here — `_owner` maps union faces back to parts, and `classify` runs
    per part. Parsing the three directives we need is cheaper than the check
    that would be required to trust the alternative.

    Everything else in the file — `vn`, `vt`, `usemtl`, `g`, `s` — is ignored.
    """
    vertices, groups = [], []
    for number, line in enumerate(text.splitlines(), start=1):
        fields = line.split()
        if not fields:
            continue
        tag = fields[0]
        if tag == "v":
            vertices.append([float(c) for c in fields[1:4]])
        elif tag == "o":
            groups.append((" ".join(fields[1:]), []))
        elif tag == "f":
            if not groups:
                raise ValueError(
                    f"{number}: face before any `o` group. Every part needs a name — "
                    f"export from Blender with objects preserved, not merged."
                )
            # OBJ indices are 1-based and global across the file; negative ones
            # count back from the vertices seen so far
            loop = [int(t.split("/")[0]) for t in fields[1:]]
            groups[-1][1].append([i - 1 if i > 0 else len(vertices) + i for i in loop])
    return vertices, groups


def _bodies(loops: list) -> list:
    """Split one `o` group's face loops into edge-connected components.

    **A group is not a part; a body is.** A baked wall arrives as its inner leaf,
    its outer leaf and — on a parapet — a cap plate, modelled as separate solids
    inside one Blender object and *touching*. Their shared corners are written as
    distinct vertex indices at identical coordinates, so merging the group into
    one mesh fuses those into edges with four incident faces: non-manifold, and
    rejected as an open shell though every solid in it is closed.

    Splitting is not a workaround for that, it is the correct reading. `parts` is
    a list of solids that touch, and `skin_over` unions them precisely so the
    faces where they touch vanish — a leaf boundary must dissolve exactly like
    the boundary between two separate objects. Grouping them into one part would
    also hand `classify` and `uphill` a multi-body mesh, whose oriented bounding
    box and area-weighted fall describe nothing.

    Components are found over the OBJ's own indices, before any snapping, so
    coincident-but-distinct vertices keep the bodies apart.
    """
    owner = list(range(len(loops)))

    def root(i):
        while owner[i] != i:
            owner[i] = owner[owner[i]]
            i = owner[i]
        return i

    seen = {}
    for face, loop in enumerate(loops):
        for a, b in zip(loop, loop[1:] + loop[:1]):
            edge = (min(a, b), max(a, b))
            if edge in seen:
                left, right = root(face), root(seen[edge])
                owner[left] = right
            else:
                seen[edge] = face

    grouped = {}
    for face in range(len(loops)):
        grouped.setdefault(root(face), []).append(loops[face])
    return [grouped[key] for key in sorted(grouped)]


def _collapsed(loops: list, points: np.ndarray):
    """Fuse each loop's coincident corners; drop loops left with fewer than three.

    A baked solid arrives with faces whose corners repeat — `Roof_Headhouse_
    InsulationTaper` writes a triangle as a six-sided loop with every corner
    doubled, and a zero-area sliver as a four-sided one with two. They are
    distinct OBJ indices at one position, which is what a boolean leaves behind.

    Cleaned rather than raised on, unlike a concave loop: a doubled corner has
    exactly one sensible reading, so there is nothing here for a person to
    decide. It has to happen *before* the fan test, which measures triangle
    orientation and reads a repeated corner as a zero-area inversion.

    Dropping a fully collapsed loop keeps the body closed: `[A, A, B, B]`
    contributes the edge `A-B` twice, so removing it removes both.

    Returns `(loops, number collapsed)`.
    """
    canonical, seen = {}, {}
    for index, point in enumerate(points):
        canonical[index] = seen.setdefault(tuple(point), index)

    kept, touched = [], 0
    for loop in loops:
        merged = [canonical[i] for i in loop]
        trimmed = [
            v for i, v in enumerate(merged) if v != merged[(i - 1) % len(merged)]
        ]
        if len(trimmed) != len(loop):
            touched += 1
        if len(trimmed) >= 3:
            kept.append(trimmed)
    return kept, touched


def _fan_is_valid(points: np.ndarray) -> bool:
    """Whether `polyhedron`'s fan triangulation is faithful for this loop.

    A fan from vertex 0 tiles a polygon exactly when the polygon is star-shaped
    from that vertex; otherwise triangles fall outside it and overlap. Area does
    not detect this — signed triangle areas telescope to the true polygon area
    whatever the shape — so the test is that no triangle is *inverted* relative
    to the loop's own normal.

    Transcribed parts are hand-checked, but a baked wall with a notch in it is
    an ordinary thing to arrive in an export, and a silently inverted triangle
    inside a substrate is close to undebuggable downstream.
    """
    normal = np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)  # Newell
    scale = np.linalg.norm(normal)
    if scale < 1e-18:
        return False  # degenerate: no plane, so no triangulation to be faithful to
    normal = normal / scale
    edges = points[1:] - points[0]
    signed = np.cross(edges[:-1], edges[1:]) @ normal
    return bool((signed > 0).all())


def _triangulated(points: np.ndarray) -> list:
    """Ear-clip a loop the fan cannot tile, as index triples into `points`.

    The fan is faithful only for a loop that is star-shaped from its first
    vertex, and a bake is full of loops that are not: a wall with a rebate, a
    parapet with a scupper slot cut through the middle of an edge. Rotating the
    loop to start elsewhere does not save it — a slot leaves a face that is
    star-shaped from no vertex at all — so the tiling has to be solved rather
    than picked.

    Ear clipping, in the loop's own plane, because nothing installed here will
    do it: `mapbox_earcut` and `triangle` are both absent, and trimesh's
    remaining engine routes through manifold3d, whose float32 arithmetic is the
    thing this module already shifts to the origin to work around. This runs on
    the snapped float64 coordinates.

    A corner with no area — the collinear vertex a subdivided neighbour leaves
    on a wall face — is clipped away contributing no triangle, which is the only
    faithful reading of it: it is a point on an edge, not a corner. That does
    not extend to a corner with area that the clip cannot reach, which means the
    loop is not simple; the tiled area is checked against the loop's own and
    raises if they disagree.
    """
    normal = np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)  # Newell
    scale = np.linalg.norm(normal)
    if scale < 1e-18:
        raise ValueError("the loop spans no plane, so it has no triangulation")
    normal = normal / scale

    edges = np.roll(points, -1, axis=0) - points
    along = edges[np.argmax(np.linalg.norm(edges, axis=1))]
    basis = np.column_stack(
        [along / np.linalg.norm(along), np.cross(normal, along / np.linalg.norm(along))]
    )
    flat = (points - points[0]) @ basis  # right-handed, so the loop runs CCW
    span = float(np.ptp(flat, axis=0).max())
    # an area, being 1e-9 of the loop's own bounding square: on a 15 m loop that
    # is a sliver 30 nm tall, well under the 1 um lattice the points sit on
    tiny = 1e-9 * span * span

    def wedge(u, v):
        """2D cross product. Spelled out: `np.cross` on 2-vectors is deprecated."""
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]

    def turn(a, b, c):
        return float(wedge(flat[b] - flat[a], flat[c] - flat[b]))

    def clear(a, b, c, rest):
        """No other corner of the remaining loop lies within triangle a-b-c.

        Tested per corner against all three edges, not by looking for one edge
        that has every corner outside it. The latter is quicker and wrong: a
        notch with corners beyond two different edges of the ear has none inside
        it, and the shortcut would report the ear blocked and leave a tileable
        loop with no ear to clip.

        A corner exactly on an edge counts as inside and blocks the ear. That is
        the conservative direction — the tiling stays faithful, the clip just
        takes a different ear.
        """
        if not rest:
            return True
        others = flat[rest]
        within = np.ones(len(rest), dtype=bool)
        for p, q in ((a, b), (b, c), (c, a)):
            within &= wedge(flat[q] - flat[p], others - flat[p]) > -tiny
        return not within.any()

    remaining = list(range(len(points)))
    tiled = []
    while len(remaining) > 3:
        for k, corner in enumerate(remaining):
            before = remaining[k - 1]
            after = remaining[(k + 1) % len(remaining)]
            if turn(before, corner, after) <= tiny:
                continue  # reflex, or a corner with no area to clip
            rest = [i for i in remaining if i not in (before, corner, after)]
            if not clear(before, corner, after, rest):
                continue
            tiled.append((before, corner, after))
            remaining.pop(k)
            break
        else:
            straight = [
                k
                for k, corner in enumerate(remaining)
                if abs(turn(remaining[k - 1], corner, remaining[(k + 1) % len(remaining)]))
                <= tiny
            ]
            if not straight:
                raise ValueError(
                    "ear clipping found no ear and no straight corner, so the loop "
                    "is not simple — it crosses itself or repeats a corner"
                )
            remaining.pop(straight[0])  # no area, so no triangle is lost with it
    if len(remaining) == 3:
        tiled.append(tuple(remaining))

    area = abs(wedge(flat, np.roll(flat, -1, axis=0)).sum()) / 2.0
    covered = sum(abs(turn(*t)) for t in tiled) / 2.0
    if abs(covered - area) > max(tiny, 1e-9 * area):
        raise ValueError(
            f"ear clipping tiled {covered:.6g} of the loop's {area:.6g} — the loop "
            f"is not simple, so no triangulation of it is faithful"
        )
    return tiled


def snapped(points, grid: float = 1e-6) -> np.ndarray:
    """Quantise coordinates to a grid — 1 µm by default.

    Modelled parts arrive with faces that miss each other by tens to hundreds of
    nanometres, and those near-misses become sliver faces in a union and
    near-parallel plane pairs in the offset solve. Snapping makes
    intended-coincident faces exactly coincident.

    It is not a cure-all: a coordinate sitting within a nanometre of a grid
    *boundary* can be split across it by rounding rather than joined, which is
    what `PART_4`'s transcription note in `build.py` records. Rounding cannot
    tell that case from two features genuinely 1 µm apart, so nothing here tries.
    """
    return np.round(np.asarray(points, dtype=float) / grid) * grid


def from_obj(path, metadata: dict | None = None, grid: float = 1e-6) -> list:
    """Read a multi-object OBJ as one part per `o` group.

    The import path for a substrate too large to transcribe: `build.py` carries
    four parts as `PART_N` literals, and the student-house's exterior walls,
    parapets and roof layers run to roughly eighty. Coordinates are snapped to
    `grid` on the way in, which is where transcription used to do it.

    Blender cannot be the reader — a `.blend` needs `bpy`, and geometry here is
    headless — so the handoff is one OBJ export, which trimesh loads without it.

    `metadata` is merged into every part. It is a plain dict rather than anything
    named, because `skin/` does not know what a facade is: `build.py` passes
    `{FACADE: RAINSCREEN}` the same way `current_substrate()` stamps its four.
    Each part also carries its `o` name as `metadata["name"]`, so a raise
    downstream can say which object it meant.

    Raises on a group with no faces, a face loop `polyhedron`'s fan cannot
    triangulate faithfully, and a part that is not a closed solid — the last
    because `skin_over` unions the parts, and a union of open shells produces
    nonsense rather than an error. Each names the object.
    """
    vertices, groups = _parse_obj(Path(path).read_text())
    if not groups:
        raise ValueError(f"{path}: no `o` groups, so the file names no parts")

    points = snapped(vertices, grid)
    parts = []
    for group, loops in groups:
        if not loops:
            raise ValueError(f"{path}: object {group!r} has no faces")

        solids = _bodies(loops)
        for number, body in enumerate(solids, start=1):
            name = group if len(solids) == 1 else f"{group}.{number}"
            used = sorted({index for loop in body for index in loop})
            local = {whole: part for part, whole in enumerate(used)}
            corners = points[used]
            faces, collapsed = _collapsed(
                [[local[index] for index in loop] for loop in body], corners
            )
            if not faces:
                raise ValueError(f"{path}: {name!r} has no face left after collapsing")

            # `polyhedron` fans, which is faithful only for a loop star-shaped
            # from its first vertex. A bake is full of loops that are not, so
            # the ones the fan cannot tile are ear-clipped here and handed down
            # as triangles — a 3-loop fans to itself, so `polyhedron` is unaware
            tiled = []
            for loop in faces:
                if len(loop) <= 3 or _fan_is_valid(corners[loop]):
                    tiled.append(loop)
                    continue
                try:
                    ears = _triangulated(corners[loop])
                except ValueError as bad:
                    raise ValueError(
                        f"{path}: {name!r} has a {len(loop)}-sided face that cannot "
                        f"be triangulated — {bad}. Triangulate it on export."
                    ) from bad
                tiled += [[loop[i] for i in ear] for ear in ears]

            part = polyhedron(corners, tiled)
            if not part.is_watertight:
                raise ValueError(
                    f"{path}: {name!r} is not a closed solid. `skin_over` unions the "
                    f"parts to find the outer surface, and an open shell makes that "
                    f"union meaningless rather than failing — so it is refused here."
                )
            part.metadata["name"] = name
            part.metadata["object"] = group  # the leaves of one wall share this
            part.metadata["collapsed_faces"] = collapsed  # export noise, for inspection
            part.metadata.update(metadata or {})
            parts.append(part)
    return parts


def prism(lo, hi, snap: float | None = 1e-6) -> trimesh.Trimesh:
    """Axis-aligned rectangular prism from its bounds.

    `snap` quantises the bounds to a grid (1 µm by default) — see `snapped`.
    Pass `snap=None` to keep the bounds verbatim.
    """
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    if snap:
        lo, hi = snapped(lo, snap), snapped(hi, snap)
    return _box(hi - lo, (lo + hi) / 2.0)


def union(parts: list[trimesh.Trimesh], grid: float = 1e-6) -> trimesh.Trimesh:
    """Merge parts into one substrate, **computed about the origin**.

    Faces where parts touch are interior to the result and disappear here, so
    the offset never sees them and no skin is generated between parts.

    manifold3d works in float32, whose resolution is proportional to magnitude:
    at 15 m from the origin a coordinate resolves to roughly 1 µm, and where two
    nearly-coplanar faces meet, that error is amplified by the shallow angle
    between them. Measured on the headhouse parapets, whose caps mitre at the
    corners: the union came back in **two** pieces, the second a 359 mm sliver of
    mean thickness **0.04 µm** — an order of magnitude below manifold3d's own
    accuracy floor, so provably arithmetic rather than geometry. It offset to
    20 km and crashed the OBJ writer. Unioning the same parts centred on the
    origin returns one clean body.

    The shift is snapped to `grid` so coordinates stay on the same 1 µm lattice
    `snapped` puts them on, and is undone on the way out, so callers see the
    substrate where they left it.
    """
    # a **copy**, even though there is nothing to union. `skin_over` treats what
    # comes back as a throwaway and writes plane ids into its metadata, and
    # "`parts` is never mutated and stays the substrate" has to hold for a
    # one-part substrate too — the synthetic rigs in the tests are exactly that
    if len(parts) == 1:
        return parts[0].copy()
    lo = np.min([p.bounds[0] for p in parts], axis=0)
    hi = np.max([p.bounds[1] for p in parts], axis=0)
    centre = snapped((lo + hi) / 2.0, grid)

    shifted = []
    for part in parts:
        moved = part.copy()
        moved.vertices = moved.vertices - centre
        shifted.append(moved)

    body = trimesh.boolean.union(shifted)
    body.vertices = body.vertices + centre
    return body


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
