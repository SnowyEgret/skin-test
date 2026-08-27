"""Distance queries between the skin and its substrate."""

from __future__ import annotations

import numpy as np
import trimesh


def clearance(parts, skin: trimesh.Trimesh) -> float:
    """Smallest gap between the skin surface and the substrate surface.

    Sampled at the skin's vertices and face centroids, against every part. For a
    sound planar offset this equals the offset distance (touched at face
    centres, exceeded at corners); a smaller value means the skin has folded
    through itself where the offset outran the substrate's local feature size.

    Queried **per part**, and neither concatenated nor unioned. The skin lies
    outside the solid, so its distance to any interior face is never less than
    its distance to the outer surface and the shared faces cannot produce a
    false alarm — but concatenating leaves coincident duplicate triangles on
    every one of those shared faces, and `closest_point` trips over the ties.
    (This said "concatenated" until 2026-08-25, contradicting both the code and
    the comment three lines below it.)
    """
    if isinstance(parts, trimesh.Trimesh):
        parts = [parts]
    samples = np.vstack([skin.vertices, skin.triangles.mean(axis=1)])
    # queried per part: concatenating leaves coincident duplicate triangles on
    # every shared face, and closest_point trips over the ties they produce
    return min(float(trimesh.proximity.closest_point(p, samples)[1].min()) for p in parts)


def separation(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    """Smallest distance between two skins, sampled both ways.

    Sampled at vertices and face centroids, so it is a close upper bound rather
    than an exact minimum — an edge crossing between samples would read high.
    Good enough to confirm two skins are nowhere near colliding.
    """
    def one_way(p, q):
        samples = np.vstack([p.vertices, p.triangles.mean(axis=1)])
        return float(trimesh.proximity.closest_point(q, samples)[1].min())

    return min(one_way(a, b), one_way(b, a))


# rows of the box test evaluated at once. The comparison is n*m*3 booleans if
# taken whole, so it is taken in slices: this bounds the intermediate at roughly
# CHUNK * m * 3 bytes regardless of how big `a` is, and changes no answer. The
# live bake needs none of this; the student-house's ~80 parts do — a self-test on
# a 20 000-triangle skin would otherwise allocate ~2.4 GB per intermediate.
CHUNK = 512

# a sample nearer than this to a part's surface is *on* it, not inside it, and
# `buried` will not count it. It is the union's own accuracy floor and not a
# weld radius: a skin vertex is placed off a face of the **union**, which
# manifold3d computes in float32, so a vertex meant to lie exactly in a
# substrate plane arrives up to ~5e-7 m either side of it. Measured: the sample
# that made the verdict flap sits 6.390e-07 m from `CapPlate-Deck9-N` — which is
# to say, on it. Below this figure there is no fact of the matter about which
# side it is on, so a smaller tolerance does not read the geometry more finely,
# it just reads the float32 noise. See CLAUDE.md, *Tolerances*
SURFACE_TOL = 1e-6


def _candidate_pairs(a: trimesh.Trimesh, b: trimesh.Trimesh, tol: float):
    """Triangle index pairs whose AABBs overlap, inflated by `tol`.

    A brute-force pass compares every pair; this rejects most of them on their
    boxes first. It is still O(n*m) comparisons — the saving is that the pairs
    surviving to the exact test are few, not that fewer boxes are examined — so
    it is a constant-factor filter and not a spatial index. It is evaluated in
    row slices of `CHUNK` so the intermediate stays bounded; a real index is the
    thing to reach for if this ever dominates.

    The inflation is on the box test only, so a pair that survives it is still
    decided exactly by `_cross`.
    """
    lo_a, hi_a = a.triangles.min(axis=1) - tol, a.triangles.max(axis=1) + tol
    lo_b, hi_b = b.triangles.min(axis=1), b.triangles.max(axis=1)
    found = []
    for start in range(0, len(lo_a), CHUNK):
        stop = start + CHUNK
        overlap = (
            (lo_a[start:stop, None, :] <= hi_b[None, :, :])
            & (hi_a[start:stop, None, :] >= lo_b[None, :, :])
        ).all(axis=2)
        hit = np.argwhere(overlap)
        if len(hit):
            hit[:, 0] += start
            found.append(hit)
    return np.vstack(found) if found else np.zeros((0, 2), dtype=int)


def _unit_normals(tri):
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length > 0), length[:, 0]


def _span(tri, dist, axis, tol):
    """Where each triangle meets the other's plane: an interval along `axis`.

    The points are the triangle's own corners that lie *on* the plane, plus the
    crossings of the edges that pass strictly through it. Returns the interval's
    ends and whether there was anything to bound.
    """
    lo = np.full(len(tri), np.inf)
    hi = np.full(len(tri), -np.inf)
    found = np.zeros(len(tri), dtype=bool)

    def take(point, when):
        nonlocal lo, hi, found
        at = np.einsum("ij,ij->i", point, axis)
        lo = np.where(when, np.minimum(lo, at), lo)
        hi = np.where(when, np.maximum(hi, at), hi)
        found |= when

    for i in range(3):
        take(tri[:, i], np.abs(dist[:, i]) <= tol)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        di, dj = dist[:, i], dist[:, j]
        through = ((di > tol) & (dj < -tol)) | ((di < -tol) & (dj > tol))
        step = np.divide(di, di - dj, out=np.zeros_like(di), where=through)
        take(tri[:, i] + (tri[:, j] - tri[:, i]) * step[:, None], through)

    return lo, hi, found


def _off_every_edge(tri, point, tol):
    """Is `point` clear of all three edge *lines* of its triangle, by `tol`?

    The interior test, done as a distance so it is in metres rather than in
    barycentric units — a sliver triangle makes those two very different things.
    A point on the triangle that fails this lies on an edge.
    """
    clear = np.ones(len(tri), dtype=bool)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        edge = tri[:, j] - tri[:, i]
        length = np.linalg.norm(edge, axis=1)
        away = np.linalg.norm(np.cross(point - tri[:, i], edge), axis=1)
        clear &= away > tol * np.where(length > 0, length, 1.0)
    return clear


def _cross(ta, tb, tol):
    """Which of these triangle pairs pass through each other — Möller's method.

    Two non-parallel planes meet in a line, and each triangle meets that line in
    an interval. They cross exactly when the two intervals overlap in **positive
    length**, and that "positive" is the whole reason this replaced a test on
    the six edges (2026-08-25, on review).

    An edge test has to decide what to do at a triangle's boundary, and both
    answers are wrong: excluding it misses every crossing that passes through a
    shared edge of the other mesh — two boxes overlapping in a quadrant read
    **zero**, and axis-aligned geometry on a 1 µm lattice produces exactly that
    — while including it reads a **graze** as a crossing, so a surface resting
    along another's boundary edge reads 6. The interval overlap has no such
    choice to make: a graze is an overlap of zero length and a crossing through
    a shared edge is an overlap of positive length. There is no tolerance
    dialled between them.

    Coplanar pairs are **not** crossings. Two coplanar sheets lie on each other
    rather than pass through each other — the knife condition `clean._sheets`
    exists for, and the flush contact both skins make where they cap one wall.

    Neither is a shared segment on its own: see the second half below.
    """
    na, _ = _unit_normals(ta)
    nb, _ = _unit_normals(tb)

    # signed distances of each triangle's corners to the other's plane
    da = np.einsum("ijk,ik->ij", tb - ta[:, :1], na)   # tb's corners to ta's plane
    db = np.einsum("ijk,ik->ij", ta - tb[:, :1], nb)   # ta's corners to tb's plane

    # a triangle wholly to one side of the other's plane cannot reach it
    apart = (
        (da > tol).all(axis=1) | (da < -tol).all(axis=1)
        | (db > tol).all(axis=1) | (db < -tol).all(axis=1)
    )
    # coplanar, decided by **distance** and never by the angle between the two
    # normals. A sliver's normal is noisy in a way its vertices are not: the
    # clean pass leaves a 0.13 x 275 mm triangle in the membrane whose normal is
    # 1.4e-11 off its plane's, which any angle threshold tight enough to be
    # meaningful reads as two planes meeting in a line — and then two coplanar
    # overlapping triangles come back as a crossing. Measured: three bogus
    # self-crossings on the live bake, which is CLAUDE.md's warning about
    # tightening a tolerance arriving for the second time.
    apart |= (np.abs(da) <= tol).all(axis=1) | (np.abs(db) <= tol).all(axis=1)

    axis = np.cross(na, nb)
    length = np.linalg.norm(axis, axis=1)
    apart |= length < 1e-12         # exactly parallel; the divide below needs it
    axis = np.divide(axis, np.where(length > 0, length, 1.0)[:, None])

    # a point on the two planes' shared line, solved rather than borrowed from a
    # triangle corner. `_span`'s anchor is only within `tol` of the *other*
    # plane, and its distance from the true line grows as `tol / sin θ` — so at
    # a shallow crossing the midpoint below would be reconstructed from a point
    # nowhere near the segment. Solving ties the accuracy to the planes instead
    # of to the angle between them (found on review, 2026-08-25)
    basis = np.stack([na, nb, axis], axis=1)
    rhs = np.stack([
        np.einsum("ij,ij->i", na, ta[:, 0]),
        np.einsum("ij,ij->i", nb, tb[:, 0]),
        np.zeros(len(ta)),
    ], axis=1)
    usable = ~apart
    online = np.zeros((len(ta), 3))
    if usable.any():
        # rhs as (n, 3, 1): numpy reads a stacked (n, 3) as one matrix, not as n
        # column vectors
        online[usable] = np.linalg.solve(basis[usable], rhs[usable][:, :, None])[:, :, 0]

    lo_a, hi_a, on_a = _span(ta, db, axis, tol)
    lo_b, hi_b, on_b = _span(tb, da, axis, tol)
    start, end = np.maximum(lo_a, lo_b), np.minimum(hi_a, hi_b)
    shared = ~apart & on_a & on_b & (end - start > tol)

    # ...and sharing a segment is not yet passing through one. Two triangles
    # meeting along a common edge share its whole length and penetrate nowhere:
    # a box resting on a box, and a lap landing flush on the face it laps onto.
    # So the shared segment has to run through the interior of **both** — its
    # midpoint clear of all six edges. The midpoint is a sound test because a
    # chord of a triangle is either one of its edges or passes through its
    # inside, with nothing in between to be ambiguous about.
    #
    # `both`, not `either`: a surface resting along another's boundary edge has
    # a segment interior to one of them, and reading that as a crossing is the
    # false positive this verdict exists to avoid. The price is that a crossing
    # whose intersection curve runs along mesh edges the whole way is missed —
    # which needs the curve to follow edges of *both* meshes at once, where the
    # old edge test failed on the far commoner case of one.
    # only the rows that got this far have finite ends; the rest carry the
    # +-inf `_span` starts from, and arithmetic on those warns for nothing
    ends = np.where(shared[:, None], np.stack([start, end], axis=1), 0.0)
    half = ends.sum(axis=1) / 2.0
    middle = online + axis * (half - np.einsum("ij,ij->i", online, axis))[:, None]
    return shared & _off_every_edge(ta, middle, tol) & _off_every_edge(tb, middle, tol)


def intersects(a: trimesh.Trimesh, b: trimesh.Trimesh, tol: float = 1e-9) -> int:
    """How many triangle pairs of `a` and `b` pass through each other.

    The verdict `clearance` could not give. It answers *"does this surface pass
    through that one"* and nothing else, which is why it survives a
    re-triangulation: a crossing is a crossing however the two sheets happen to
    be tiled, where `clearance` samples centroids and moves its own answer when
    the samples move. Chosen over `clearance` as the build's verdict by Duncan,
    2026-08-25 — see NOTES, *"The clearance verdict"*.

    The count is **triangle pairs**, not crossing points: a pair either crosses
    or it does not, which is exact, where counting points means deciding when
    two of them are the same one. Only zero-or-not is a verdict; the magnitude
    says roughly how much surface is involved and nothing finer.

    `a is b` tests a surface against **itself**, skipping only pairs that share
    an **edge** — two corners. Triangles sharing a single *corner* are kept, and
    that is not a nicety: a lap folding back through the panel it springs from
    shares exactly the arris vertex with it, and skipping those made this blind
    to 553 of the live membrane's 1157 candidate pairs (found on review,
    2026-08-25). A pair merely touching at that shared corner overlaps in zero
    length and is not a crossing, so nothing has to be special-cased.
    """
    same = a is b
    pairs = _candidate_pairs(a, b, tol)
    if same:
        pairs = pairs[pairs[:, 0] < pairs[:, 1]]
    if not len(pairs):
        return 0

    ta, tb = a.triangles[pairs[:, 0]], b.triangles[pairs[:, 1]]
    if same:
        # `rtol=0` matters: numpy's default is 1e-5, which at this model's ~15 m
        # coordinates is a 0.15 mm tolerance rather than the 1 nm asked for
        corners = (
            np.isclose(ta[:, :, None, :], tb[:, None, :, :], rtol=0.0, atol=tol)
            .all(axis=3)
            .any(axis=2)
            .sum(axis=1)
        )
        keep = corners < 2          # sharing an edge, not merely a corner
        ta, tb = ta[keep], tb[keep]
        if not len(ta):
            return 0

    return int(np.count_nonzero(_cross(ta, tb, tol)))


def buried(parts, skin: trimesh.Trimesh) -> int:
    """How many of the skin's samples lie **inside** a substrate part.

    The signed half of the verdict, and the half `intersects` cannot give: a
    skin wholly swallowed by a part crosses nothing. `clearance` cannot give it
    either — `closest_point` returns an unsigned distance, so a buried sample
    reads as a small positive gap, which is why this pair replaced it.

    Sampled at vertices **and face centroids**, the same samples `clearance`
    takes, so a panel driven through a part with neither end inside it is still
    caught. A sample inside two overlapping parts is counted **once**: the
    substrate's own layers interpenetrate, and counting per part would inflate
    the number for a reason that says nothing about the skin.

    **Buried means strictly inside, and a sample sitting *on* a part's surface
    does not count.** `trimesh`'s `contains` cannot tell the two apart: it casts
    a ray in a random direction, and a point on the boundary resolves whichever
    way the ray happens to leave. That made the verdict flap — 3 and 4 in
    alternate runs over one fixed cladding mesh, with nothing about the geometry
    changing between them — and a verdict that moves without the geometry moving
    is exactly the defect `clearance` was demoted for. It is not a rare case
    either: `build.facade_offsets`' "the outer system owns the corner" branch
    offsets a facade by **zero**, which puts the skin's vertices in a substrate
    face deliberately. So containment is confirmed against the distance to the
    surface, which is signless but exact, and anything within `SURFACE_TOL` of a
    part is on it. Found on review, 2026-08-26.
    """
    if isinstance(parts, trimesh.Trimesh):
        parts = [parts]
    samples = np.vstack([skin.vertices, skin.triangles.mean(axis=1)])
    inside = np.zeros(len(samples), dtype=bool)
    for part in parts:
        within = np.flatnonzero(part.contains(samples))
        if not len(within):
            continue
        off = trimesh.proximity.closest_point(part, samples[within])[1]
        inside[within[off > SURFACE_TOL]] = True
    return int(np.count_nonzero(inside))
