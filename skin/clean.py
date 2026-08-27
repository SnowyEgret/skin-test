"""Coplanar overlap dissolved from a mesh, plane by plane, with a 2D boolean.

The lap rule legitimately emits whole quads, and where one band lies wholly
inside another on the same plane the two overlap — a miter between them cannot
un-overlap them, so the double-covered area is resolved here instead, after the
fact. Mesh in, mesh out: nothing in `skin/offset.py` or `build.py`'s rules knows
this module exists, and it is named for a mesh rather than for a skin because
overlapping itself in a plane is a property of a mesh.

**Not** part of `skin_over`. The union inserts a vertex wherever two bands'
boundaries cross, so a cleaned mesh no longer satisfies "every vertex that
survived is exactly where the offset put it" — the property that makes
`_trim_below` a cut rather than a clamp. Cleaning is an explicit step over a
finished mesh, so the raw emission stays inspectable.

shapely (GEOS, double precision) does the union because it is bit-exact on every
point it preserves and it keeps collinear vertices, which `skin/export.py` keeps
on purpose so that a neighbouring facet cornering there leaves no T-junction.
`manifold3d.triangulate` gets back to triangles: it is already a hard dependency
and it takes holes.
"""

from __future__ import annotations

import collections

import manifold3d
import numpy as np
import trimesh
from shapely import STRtree
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from .offset import PLANE_TOL, _basis, _flat, _plane_rows

# How far apart two answers for one point may be and still be one point. The
# only points that need welding at all are the ones the union *computed*, where
# two planes reached the same crossing through different 2D bases and differ in
# the last bits — measured at ~1e-14 m. This is five orders above that and three
# below the 1 µm lattice every substrate coordinate is snapped to, which is the
# constraint that matters: at `PLANE_TOL` two neighbouring lattice points are
# 9.9999999925e-07 apart and would weld into one, silently destroying a 1 µm
# strip and reporting the loss as overlap.
WELD_TOL = 1e-9

# How far off the straight line through its two neighbours a ring vertex may sit
# and still be on it, for `dissolve`. A vertex the union inserted where two
# boundaries crossed lies on both to within double precision — nanometres is
# five orders above that — while the shallowest real corner in a building sits
# millimetres off. Nothing between the two is a judgement call this has to make.
STRAIGHT_TOL = 1e-9


def _groups(mesh: trimesh.Trimesh) -> list[tuple[np.ndarray, list[int]]]:
    """Faces gathered onto their planes, matched **either way up**.

    A bowtie quad's two triangles are wound opposite ways, so a group keyed on
    `(n, d)` alone puts them in different groups and misses the very overlap
    this pass exists to dissolve. Matched against the representatives already
    found rather than by equality of a rounded key, for the reason
    `offset._plane_ids` is: manifold3d leaves a union's faces up to half a
    `PLANE_TOL` cell off their true planes, so two faces of one plane land
    either side of a lattice boundary often enough to matter.

    A face with no area has no plane — its normal is not defined — and covers
    nothing, so it is dropped here rather than carried to a basis that would
    come back NaN.
    """
    rows, areas = _plane_rows(mesh), mesh.area_faces
    reps: list[np.ndarray] = []
    faces: list[list[int]] = []
    lookup: dict[tuple, int] = {}
    for f, row in enumerate(rows):
        if areas[f] <= 0:
            continue
        key = tuple(np.round(row / PLANE_TOL).astype(np.int64))
        found = lookup.get(min(key, tuple(-k for k in key)))
        if found is None:
            found = next(
                (
                    i
                    for i, rep in enumerate(reps)
                    if min(np.abs(rep - row).max(), np.abs(rep + row).max()) < PLANE_TOL
                ),
                len(reps),
            )
            if found == len(reps):
                reps.append(row)
                faces.append([])
            lookup[min(key, tuple(-k for k in key))] = found
        faces[found].append(f)
    return list(zip(reps, faces))


class _Points:
    """3D points, deduplicated within `WELD_TOL`, in insertion order.

    A point the union preserved arrives back bit-identical and is matched
    exactly; one the union computed — where two bands' boundaries crossed — can
    be reached from either of the two planes that made it, with float noise
    between the two answers, and must still weld. Cells are searched with their
    neighbours so that a pair either side of a lattice boundary is still found.
    """

    def __init__(self):
        self.points: list[np.ndarray] = []
        self.cells: dict[tuple, list[int]] = {}

    def index(self, point: np.ndarray) -> int:
        cell = np.round(point / WELD_TOL).astype(np.int64)
        for step in np.ndindex(3, 3, 3):
            for i in self.cells.get(tuple(cell + np.array(step) - 1), ()):
                if np.abs(self.points[i] - point).max() < WELD_TOL:
                    return i
        self.cells.setdefault(tuple(cell), []).append(len(self.points))
        self.points.append(point)
        return len(self.points) - 1


def _sheets(covering: list[tuple[float, Polygon]]) -> list[float]:
    """One direction per face of a plane, with a bowtie's halves reconciled.

    Faces that **overlap** are one sheet however they are wound: a bowtie quad's
    two triangles come out facing opposite ways and overlapping, and that
    winding is an artefact of the self-crossing quad rather than two surfaces.
    Faces that merely **touch** are not. Two sheets facing opposite ways, edge to
    edge, are an ordinary condition — a knife, where a roof butts a wall on the
    wall's own plane and both sides of the contact are exposed, or simply two
    solids meeting along an edge — and merging those turns the solid inside out:
    a plane-wide vote cost the substrate union its volume (84.294 → 104.688 m³)
    and a region-wide one cost two cubes meeting along an edge theirs (2.0 →
    4.0). `unary_union` dissolves the boundary between two touching regions, so
    the sides have to be separated **before** it runs, not oriented after it.

    So the relation is positive **area** of intersection, and each connected
    component of it takes the direction of the greater area within it. A
    component that ties keeps the direction of the plane's representative.
    """
    parent = list(range(len(covering)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    polygons = [polygon for _, polygon in covering]
    tree = STRtree(polygons)
    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon):
            if j > i and polygon.intersection(polygons[j]).area > 0:
                parent[root(i)] = root(j)

    vote: dict[int, float] = {}
    for i, (way, polygon) in enumerate(covering):
        vote[root(i)] = vote.get(root(i), 0.0) + way * polygon.area
    return [1.0 if vote[root(i)] >= 0 else -1.0 for i in range(len(covering))]


def _corners(rings: list, points: list[np.ndarray]) -> set[int]:
    """Every point index some ring **turns** at.

    The rest lie straight between their neighbours on every ring that holds
    them, and carry no information about the shape of the surface: dropping one
    leaves every outline exactly where it was. A point that any ring turns at
    has to stay in *all* of them, which is why this is asked once over the whole
    mesh and not per plane — remove a vertex from one facet while its neighbour
    still corners there and the join becomes a T-junction, which is the reason
    `skin/export.py` keeps collinear vertices in the first place.
    """
    corners = set()
    for index, _, _ in rings:
        for k, here in enumerate(index):
            before, after = points[index[k - 1]], points[index[(k + 1) % len(index)]]
            span = np.linalg.norm(after - before)
            off = np.linalg.norm(np.cross(points[here] - before, after - before))
            if span < STRAIGHT_TOL or off / span > STRAIGHT_TOL:
                corners.add(here)
    return corners


def _straightened(ring, corners: set[int]):
    """One ring with its straight-through vertices dropped.

    Left alone if that would leave fewer than three, which no ring enclosing an
    area can do — a polygon has to turn at least three times — so it means the
    ring is a sliver whose vertices are all collinear to a nanometre, and
    dropping it would delete surface rather than tidy it.
    """
    index, plan, way = ring
    keep = [k for k, i in enumerate(index) if i in corners]
    if len(keep) < 3:
        return ring
    return [index[k] for k in keep], plan[keep], way


def _border(mesh: trimesh.Trimesh) -> set[tuple[int, int]]:
    """The half-edges with no face on the other side, each in its face's own
    direction.

    Direction is the whole point of reading them as half-edges rather than as
    unordered pairs: two faces sharing an edge traverse it opposite ways, so a
    face filling a hole has to run the *reverse* of the border half-edge it
    lands on. That is what orients a gusset, and it is read off the mesh rather
    than guessed from a normal.
    """
    free = trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1)
    return {(int(a), int(b)) for a, b in mesh.edges[free]}


def _loops(half: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """The border split into its connected pieces, each a set of half-edges.

    Connected rather than walked: where a surface is torn at a fold the tear
    pinches to a point, and the membrane's is exactly that — two triangles
    meeting at one vertex of degree four. A walk would have to guess which way
    to turn there, so nothing walks; `polygonize` reads the piece as the planar
    graph it is.
    """
    adjacent = collections.defaultdict(set)
    for a, b in half:
        adjacent[a].add(b)
        adjacent[b].add(a)
    seen, pieces = set(), []
    for start in adjacent:
        if start in seen:
            continue
        seen.add(start)
        stack, part = [start], {start}
        while stack:
            here = stack.pop()
            for there in adjacent[here]:
                if there not in seen:
                    seen.add(there)
                    part.add(there)
                    stack.append(there)
        pieces.append({(a, b) for a, b in half if a in part})
    return pieces


def _gussets(mesh: trimesh.Trimesh, width: float) -> tuple[list[list[int]], int]:
    """Triangles closing every border loop that is flat and no wider than `width`.

    A **gusset** is the one face here that is not the offset of anything: it
    bridges a tear the offset could not span. Where the substrate has no
    thickness — a roof knifing into a wall on the wall's own plane — the two
    offset surfaces part by twice the distance and the skin opens along the
    contact, which is `offset._reconcile` declining to move one vertex two ways
    at once. The tear is bounded by vertices the offset already placed, so
    closing it invents no point; only the surface between them is new.

    Two conditions on the loop, and they do different jobs:

    - **flat**, to `PLANE_TOL`. A loop that does not lie in a plane has no
      surface to be filled with, only a choice of surfaces, and choosing is not
      a cleanup's business. Measured, this is not a close call: the membrane's
      tear is flat to 1.5e-15 m, and every legitimate free edge in either skin
      on any of the three substrates stands at least 94 mm off its own best-fit
      plane, because a skin's perimeter wraps a building.
    - **narrow**, to the caller's `width`. This is an **authored** bound, which
      a cleanup is allowed and a derivation is not. It is deliberately not
      derived as twice the offset: the membrane's tear is 16 mm across in plan
      but 18.016 mm along its own plane, because the roof it opens on falls, so
      twice the distance would not catch the very tear it was reasoned from.

    The width is the spread across the loop's minor principal axis — a slot's
    own thinness. An exact minimal width would be rotating calipers; with 18 mm
    to measure against a 248 mm next-smallest there is nothing here for the
    difference to change.

    And one condition on the region rather than on the loop, which is derived
    and does the load-bearing safety work: **a region the mesh already covers is
    not a tear**. Without it the worst case is silent and severe — the perimeter
    of any flat sheet narrower than `width` is a flat narrow loop, so a 20 mm
    cover flashing would have its own outline "closed" and come out doubled,
    two coincident surfaces reported as a tidy-up. A tear is by construction
    where the surface is *missing*, so nothing coplanar with it is there; the
    membrane's is coplanar with nothing at all. This is what lets the authored
    bound stay a bound on size rather than a guess about what a loop means.
    """
    half = _border(mesh)
    faces, closed = [], 0
    for piece in _loops(half):
        loop = sorted({v for edge in piece for v in edge})
        points = mesh.vertices[loop]
        centre = points.mean(axis=0)
        # the plane the loop lies in, if it lies in one: the least-spread
        # direction is its normal, and the next-least is the way it is thin
        axes = np.linalg.svd(points - centre)[2]
        spread = (points - centre) @ axes.T
        if np.abs(spread[:, 2]).max() > PLANE_TOL or np.ptp(spread[:, 1]) > width:
            continue

        u, v = _basis(axes[2])
        plan = _flat(points, centre, u, v)
        held = {tuple(q): i for q, i in zip(plan, loop)}
        at = dict(zip(loop, plan))

        # what the mesh already covers in this plane, matched either way up for
        # the reason `_groups` is. A tear is where the surface is missing, so a
        # region that is already surface is not one
        row = np.append(axes[2], axes[2] @ centre)
        rows = _plane_rows(mesh)
        coplanar = (
            Polygon(_flat(corners, centre, u, v))
            for corners, other in zip(mesh.triangles, rows)
            if min(np.abs(other - row).max(), np.abs(other + row).max()) < PLANE_TOL
        )
        covered = unary_union([face for face in coplanar if face.is_valid and face.area > 0])
        for region in polygonize(LineString([at[a], at[b]]) for a, b in piece):
            if region.intersection(covered).area > 0:
                continue
            region = orient(region, 1.0)  # exteriors CCW, holes CW: what triangulate reads
            rings = [region.exterior, *region.interiors]
            index = [held[tuple(q)] for ring in rings for q in ring.coords[:-1]]
            # a face filling this region shares every border edge with the face
            # already on it, so it must traverse that edge the other way. If the
            # oriented ring runs *with* a half-edge, the fill is wound against it
            outline = [held[tuple(q)] for q in region.exterior.coords[:-1]]
            along = any(
                (outline[k], outline[(k + 1) % len(outline)]) in half
                for k in range(len(outline))
            )
            for tri in manifold3d.triangulate(
                [np.array(ring.coords[:-1]) for ring in rings], allow_convex=False
            ):
                corner = [index[i] for i in tri]
                faces.append(corner[::-1] if along else corner)
            closed += 1
    return faces, closed


def clean(
    mesh: trimesh.Trimesh, dissolve: bool = False, close: float = 0.0
) -> trimesh.Trimesh:
    """`mesh` with each of its planes unioned in 2D and re-triangulated.

    Faces that overlap within a plane are resolved into one covering, so the
    area is the area actually covered rather than the sum of the triangles.
    Faces on different planes are untouched by each other: this says nothing
    about two planes intersecting.

    Closing a hole is a separate mechanism, and is `close` — a **third**
    operation, off at zero, taking the widest tear that may be gusseted. See
    `_gussets`: nothing about a hole falls out of a coplanar union, because a
    tear at a fold is coplanar with nothing.

    Which faces are one sheet, and which are two sheets back to back, is
    `_sheets`; the two ways up are unioned apart and re-triangulated together,
    in one call per plane, so that sheets meeting along a line share the
    vertices they meet at instead of leaving a seam of non-manifold edges.

    `dissolve` is a **second, opted-in operation**, off by default: it drops
    every vertex that lies straight between its neighbours on every ring that
    holds it and that no ring turns at. That is a tidy-up rather than a
    derivation — it is allowed an authored bound where a rule is not — and it
    is separate because the outlines it thins are correct either way.

    The three run in that order — union, dissolve, close — because each reads
    the outline the one before it left. In particular a gusset is fitted to the
    border of the *finished* surface: the union retraces the boundary a bowtie
    left, and a border edge that is an artefact is not a tear.
    """
    points, plans = _Points(), []
    for rep, group in _groups(mesh):
        normal, (u, v) = rep[:3], _basis(rep[:3])
        origin = normal * rep[3]

        held, covering = {}, []
        for face in group:
            corners = mesh.vertices[mesh.faces[face]]
            plan = _flat(corners, origin, u, v)
            held.update(zip(map(tuple, plan), corners))
            polygon = Polygon(plan)
            if not polygon.is_valid or polygon.area <= 0:
                continue
            covering.append((np.sign(mesh.face_normals[face] @ normal), polygon))

        # each way up is unioned on its own, so that two sheets meeting edge
        # to edge stay two sheets — `unary_union` would dissolve the boundary
        # between them and leave one region facing one way
        rings, sheets = [], _sheets(covering)
        for way in (1.0, -1.0):
            side = [poly for (_, poly), s in zip(covering, sheets) if s == way]
            if not side:
                continue
            union = unary_union(side)
            for region in getattr(union, "geoms", [union]):
                if not isinstance(region, Polygon) or region.is_empty:
                    continue  # a union may also return the lines two faces touch along
                region = orient(region, 1.0)  # exteriors CCW, holes CW: what triangulate reads
                for ring in [region.exterior, *region.interiors]:
                    plan = np.array(ring.coords[:-1])
                    # a point the union preserved comes back bit-identical, so
                    # it maps to the vertex it came from rather than to an
                    # unprojection of itself
                    one = [
                        points.index(held.get(tuple(q), origin + q[0] * u + q[1] * v))
                        for q in plan
                    ]
                    # ...and two consecutive coordinates of one ring can weld to
                    # that same point: GEOS reached one crossing twice, from
                    # each of the two boundaries meeting there, and the two
                    # answers differ in the last bits. The zero-length edge
                    # between them changes no outline, but it makes each of the
                    # pair look **straight through** to `_corners` -- its ring
                    # neighbour is itself, so the cross product is exactly zero
                    # -- and `dissolve` then drops both, cutting the corner off.
                    # Measured on the live bake: one L-shaped ring of the
                    # cladding came back as a diagonal and the skin gained
                    # 0.910 m2 of surface the offset never placed, on a pass
                    # whose whole claim is that it changes no outline
                    kept = [k for k in range(len(one)) if one[k] != one[k - 1]]
                    if len(kept) < 3:
                        # ...and where the dedup leaves fewer than three, the
                        # duplicates go back. Fewer than three distinct points
                        # enclose no area, so the ring is a spur and there is
                        # nothing on it to straighten: `_straightened` refuses
                        # to leave fewer than three, so it survives whole either
                        # way. What the restore costs is a **vote**. `_corners`
                        # is asked once over the whole mesh, and with
                        # `one[k - 1] == one[k]` it reads `points[here] -
                        # before` as zero, so this ring registers no corner at
                        # the point it doubles back from — where the deduped
                        # ring would come back with `span == 0` and register
                        # one, which is the conservative answer. The cost of
                        # getting that wrong is a T-junction, and it is the one
                        # this pass exists to avoid: a point the spur turns at
                        # that is straight through on every other ring holding
                        # it would be dissolved out from under a ring that keeps
                        # it.
                        # Measured 2026-08-27, because this does fire — once,
                        # on the live bake's membrane, an `[a, b, a]` spur
                        # between (8.072, 5.293, 14.619) and (8.072, 5.177,
                        # 14.503). Run both ways the output is identical: 145
                        # -> 113 triangles, 59 -> 35 border edges, 15 -> 0
                        # T-junctions and the same area to 1e-6 mm2, because `a`
                        # takes its corner vote from another ring anyway. (That
                        # is `clean(dissolve=True)` alone; `build.py` reads
                        # 145 -> 115 on the same skin because it also asks for
                        # `close` and the tear takes two gussets.) So it
                        # is left as it is. If a substrate ever poses one that
                        # does not, drop the ring rather than restoring it — it
                        # encloses nothing, and dropping it removes the false
                        # vote without deleting surface
                        kept = list(range(len(one)))
                    rings.append(([one[k] for k in kept], plan[kept], way))
        plans.append(rings)

    thinned = 0
    if dissolve:
        # asked once over every ring of every plane, because a vertex may be
        # straight through on one facet and a corner on the one next to it
        corners = _corners([r for rings in plans for r in rings], points.points)
        before = {i for rings in plans for index, _, _ in rings for i in index}
        plans = [[_straightened(r, corners) for r in rings] for rings in plans]
        after = {i for rings in plans for index, _, _ in rings for i in index}
        thinned = len(before - after)

    faces = []
    for rings in plans:
        if not rings:
            continue
        # every ring of the plane goes into one `triangulate` call, both ways up
        # together, so that two sheets meeting along a line share the vertices
        # they meet at. A triangle never spans the two: the sides are disjoint in
        # area, so each lies inside exactly one of them
        index = [i for one, _, _ in rings for i in one]
        at = [way for one, _, way in rings for _ in one]
        for tri in manifold3d.triangulate([plan for _, plan, _ in rings], allow_convex=False):
            corner = [index[i] for i in tri]
            faces.append(corner if at[tri[0]] > 0 else corner[::-1])

    out = trimesh.Trimesh(
        vertices=np.array(points.points).reshape(-1, 3),
        faces=np.array(faces, dtype=np.int64).reshape(-1, 3),
        process=False,
    )
    out.update_faces(out.nondegenerate_faces())
    out.remove_unreferenced_vertices()

    # measured before any gusset is added, so that `overlap_removed` stays what
    # the union dissolved rather than that less what a gusset put back
    dissolved = float(mesh.area - out.area)
    gussets, closed = _gussets(out, close) if close > 0 else ([], 0)
    if gussets:
        # the gussets use vertices the mesh already has, so only the faces grow
        out = trimesh.Trimesh(
            vertices=out.vertices,
            faces=np.vstack([out.faces, np.array(gussets, dtype=np.int64)]),
            process=False,
        )
    # what made the mesh is worth carrying — the offset's distance, its residual
    # — but nothing keyed on an index is: `offset._plane_ids` holds an id per
    # face and `folds` a list of vertex indices, and both were rebuilt here.
    # Dropped rather than remapped, so a reader gets nothing instead of the
    # wrong vertex; `build.py` prints folds off the raw skin
    out.metadata.update(
        {k: v for k, v in mesh.metadata.items() if k not in ("plane_ids", "folds")}
    )
    out.metadata["overlap_removed"] = dissolved
    out.metadata["vertices_dissolved"] = thinned
    out.metadata["tears_closed"] = closed
    out.metadata["gusset_area"] = float(
        sum(out.area_faces[len(out.faces) - len(gussets):])
    )
    return out
