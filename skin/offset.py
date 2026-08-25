"""Planar (mitered) offset of a triangle mesh, solved as one constrained system.

Every face plane is pushed out along its outward normal by `distance` and the
faces re-extended to meet. Three planes at a corner pin it exactly, but a sloped
roof over a concave plan puts four planes at a corner, and four offset planes
are not generally concurrent: the offset is over-determined and something has to
give. The conflict is resolved in favour of

  * vertical and horizontal planes, held at exactly `distance`, and
  * edges horizontal in the substrate, held horizontal,

which leaves the sloped planes to absorb the error. They stay planar — two
horizontal edges at different heights still define a plane — but end up at a
slightly different tilt and distance than a perfect offset would give.
`metadata["slope_deviation"]` reports how far off, in metres.
"""

from __future__ import annotations

from functools import cached_property

import manifold3d
import numpy as np
import trimesh

from . import substrate

# normals closer than this are treated as the same plane
PLANE_TOL = 1e-6
# keeps the KKT system non-singular where the soft equations underdetermine a vertex
RIDGE = 1e-9
# a lap this close to level is level: the direction cosine a cap plate's own fall
# puts into a lap perpendicular to its arris, rounded off so an upstand is a
# height. Not a plane tolerance -- see `_across`
RAKE = 0.05


def _vertex_normals(mesh: trimesh.Trimesh, vertex: int, tol: float, only=None) -> np.ndarray:
    """Distinct outward face-plane normals meeting at `vertex`.

    Normals within `tol` of an axis are snapped onto it: the union that feeds
    this carries float32 vertices, and an axis-aligned face whose normal is off
    by 1e-7 would otherwise be held to a hard constraint that is itself skew.

    `only` is a face mask restricting which incident faces are read. It is used
    solely to re-read a contradictory vertex — see `_reconcile`.
    """
    faces = mesh.vertex_faces[vertex]
    faces = faces[faces >= 0]
    if only is not None:
        faces = faces[only[faces]]
    if not len(faces):
        return np.zeros((0, 3))
    normals = mesh.face_normals[faces]
    axis = np.abs(normals).argmax(axis=1)
    aligned = np.abs(normals).max(axis=1) > 1 - tol
    normals = normals.copy()
    normals[aligned] = np.sign(normals[aligned, axis[aligned]])[:, None] * np.eye(3)[axis[aligned]]
    return np.unique(np.round(normals / PLANE_TOL), axis=0) * PLANE_TOL


def _opposed(normals: np.ndarray):
    """The first pair of normals at a vertex that point opposite ways, or None.

    Two such planes cannot both be offset outward and still meet: the vertex
    would have to move `distance` one way and `distance` the other at once. The
    equations are not merely hard to satisfy, they are contradictory, and a
    least-squares solve does not report that — it splits the difference and
    spreads the error across the whole body.
    """
    # compared as unit vectors. `_vertex_normals` quantises to the PLANE_TOL
    # lattice, so a normal off-axis by more than `tol` comes back with |n| up to
    # ~8e-7 short of 1 and an exactly antiparallel pair dots to -|n|^2, which can
    # sit above -1 + PLANE_TOL. Measured over 20 000 random sloped normals:
    # 3.65% of genuine contradictions went undetected, and an undetected one is
    # never reconciled and never reported -- the solve just splits the
    # difference, which is the failure `_reconcile` exists to make structural.
    # Axis-aligned normals are snapped to exact units upstream and were fine,
    # which is why every fold found so far happened to be axis-aligned.
    unit = normals / np.linalg.norm(normals, axis=1)[:, None]
    for i in range(len(normals)):
        for j in range(i + 1, len(normals)):
            if unit[i] @ unit[j] < -1 + PLANE_TOL:
                return normals[i], normals[j]
    return None


def _reconcile(mesh, vertex, tol, normals, covered):
    """Drop the planes of uncovered faces at a contradictory vertex, or raise.

    A surface that folds back on itself has no offset at the fold: the vertex
    lies on two planes facing opposite ways. Measured on the headhouse parapets:
    where a roof layer's end face is exposed through a scupper, it is coplanar
    with the parapet's inner face it otherwise abuts, and the two survive into
    the union facing opposite ways. One point then carries both.

    The offset is solved over the whole body so that a vertex on the edge of a
    selection sits on the miter it would have had if its neighbours were skinned
    too. That is why every face contributes a plane — but it only justifies the
    planes of faces that *bound* something being built. A face no skin touches,
    whose plane contradicts its neighbours, is supplying a constraint for a
    surface nobody asked for and breaking the ones that were.

    So the rule is narrow, and deliberately applies nowhere else: at a
    contradictory vertex, and only there, re-read the planes from the covered
    faces alone. Every other vertex keeps every plane it had, so no model that
    solves today changes by so much as a bit. If the contradiction survives
    among the covered faces it is real — a skin is being asked to cover both
    sides of a fold — and it raises here rather than surfacing as a vertex
    thrown kilometres away with a clean residual.
    """
    if covered is None:
        reduced = normals
        why = "no face selection was given, so every plane is required"
    else:
        reduced = _vertex_normals(mesh, vertex, tol, only=covered)
        incident = mesh.vertex_faces[vertex]
        skinned = int(covered[incident[incident >= 0]].sum())
        why = f"{skinned} of its faces are covered by a skin"

    pair = _opposed(reduced)
    if pair is None:
        return reduced

    a, b = pair
    raise ValueError(
        f"the surface folds back on itself at vertex {vertex} "
        f"{np.round(mesh.vertices[vertex], 6).tolist()}: it lies on planes facing "
        f"{np.round(a, 3).tolist()} and {np.round(b, 3).tolist()}, which cannot both be "
        f"offset outward — the vertex would have to move both ways at once. "
        f"{why}, so this is not a stray face that can be ignored. Two surfaces "
        f"facing exactly opposite ways means the solid has no thickness there: "
        f"either a degenerate sliver, in practice a fragment a boolean left "
        f"behind, or two parts meeting exactly on one plane where an opening "
        f"exposes the far side of the contact — lap those into each other "
        f"rather than abutting them."
    )


def _stack(rows: list, width: int) -> tuple[np.ndarray, np.ndarray]:
    if not rows:
        return np.zeros((0, width)), np.zeros(0)
    return np.array([r for r, _ in rows]), np.array([v for _, v in rows])


def planar_offset(mesh: trimesh.Trimesh, distance: float, tol: float = 1e-6, covered=None):
    """Offset every face of `mesh` outward by `distance`.

    Solves for all vertex displacements at once. A vertex lies on all of its
    incident face planes, so displacing it by `t` with `n . t == distance` for
    each incident normal `n` puts it on all the offset planes at once. Those
    equations are hard for vertical and horizontal planes, least-squares for the
    sloped rest; horizontal edges add hard equations tying endpoint heights.

    `covered` is the face mask the caller is actually building a skin over, and
    is consulted at exactly one kind of vertex: one whose planes contradict each
    other because the surface folds back on itself. See `_reconcile`. Omitting
    it makes every plane required, which is the right default for a plain
    closed-shell offset — there is no selection, so nothing is uncovered.
    """
    width = 3 * len(mesh.vertices)
    hard: list = []
    soft: list = []
    folds: list = []

    for vertex in range(len(mesh.vertices)):
        normals = _vertex_normals(mesh, vertex, tol)
        if _opposed(normals) is not None:
            normals = _reconcile(mesh, vertex, tol, normals, covered)
            folds.append(vertex)
        for normal in normals:
            row = np.zeros(width)
            row[3 * vertex : 3 * vertex + 3] = normal
            # vertical and horizontal planes are held exactly; only sloped
            # planes absorb error. Testing for axis-alignment instead would
            # demote a vertical wall running at any other plan angle to soft.
            level = abs(normal[2]) < tol or abs(normal[2]) > 1 - tol
            (hard if level else soft).append((row, distance))

    sharp = mesh.face_adjacency_angles > tol  # ignore diagonals inside a facet
    for a, b in mesh.face_adjacency_edges[sharp]:
        if abs(mesh.vertices[a][2] - mesh.vertices[b][2]) < tol:
            row = np.zeros(width)
            row[3 * a + 2], row[3 * b + 2] = 1.0, -1.0
            hard.append((row, 0.0))

    H, h = _stack(hard, width)
    S, s = _stack(soft, width)

    # Minimise ||S t - s||^2 subject to H t = h, as a KKT system. Solving it via
    # a nullspace basis instead lets near-null directions through, and the
    # least-squares step then amplifies them into millimetres of constraint
    # violation. RIDGE picks the smallest displacement where the soft equations
    # leave a vertex free (a collinear vertex mid-edge, say).
    k = np.block(
        [
            [S.T @ S + RIDGE * np.eye(width), H.T],
            [H, np.zeros((len(h), len(h)))],
        ]
    )
    t = np.linalg.lstsq(k, np.concatenate([S.T @ s, h]), rcond=None)[0][:width]

    # A vertex is placed where its offset planes intersect. If that lands further
    # away than the whole body is across, those planes are effectively parallel
    # and the intersection means nothing — the answer has left the building. This
    # is not a tolerance to tune: it says the result is not a skin of this mesh.
    #
    # In practice it is a degenerate sliver, and in practice that sliver is a
    # detached fragment a boolean left behind. Measured on the headhouse parapets:
    # a four-vertex wedge orphaned at a mitred corner, 6 mm of overshoot, offset
    # 20 mm — its vertices landed 20 km out, while the 120-face body it came from
    # offset exactly. The residual stayed at 7e-12 throughout, so nothing else here
    # notices; it first showed up as a crash in the OBJ writer.
    moved = np.linalg.norm(t.reshape(-1, 3), axis=1)
    span = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0]))
    if (moved > span).any():
        worst = int(moved.argmax())
        raise ValueError(
            f"offset is undetermined at vertex {worst} {np.round(mesh.vertices[worst], 4).tolist()}: "
            f"it moved {moved[worst]:.3g} m for a {distance} m offset, further than the body's own "
            f"{span:.3g} m diagonal, so the planes meeting there are effectively parallel. "
            f"Usually a degenerate sliver — check whether the substrate has a detached "
            f"fragment ({mesh.body_count} connected component(s) here)."
        )

    out = trimesh.Trimesh(
        vertices=mesh.vertices + t.reshape(-1, 3), faces=mesh.faces.copy(), process=False
    )
    out.metadata["offset_distance"] = distance
    out.metadata["offset_residual"] = float(np.abs(H @ t - h).max()) if H.size else 0.0
    out.metadata["slope_deviation"] = float(np.abs(S @ t - s).max()) if S.size else 0.0
    out.metadata["max_displacement"] = float(moved.max()) if moved.size else 0.0
    # the folds that were reconciled rather than raised on: geometry the solve
    # deliberately stopped constraining, so a caller can say where it did that
    out.metadata["folds"] = folds
    return out


def elements_of(parts: list) -> list:
    """Part indices grouped by `metadata["object"]` — see `Faces.elements`.

    Module level so a caller can group parts *before* there is a union to build
    `Faces` over. `build.group_caps` needs exactly that: it decides which bodies
    belong to one element, which is the question `Faces` is constructed after.
    """
    groups: dict = {}
    for index, part in enumerate(parts):
        name = part.metadata.get("object")
        groups.setdefault(("object", name) if name else ("part", index), []).append(index)
    return list(groups.values())


class Faces:
    """What a face predicate may ask about the unioned substrate.

    Predicates used to take `(normals, centres, owner)`, which is enough to test
    a face against a named plane but not enough to ask what a face *adjoins* or
    what part it belongs to. Rules that read the substrate rather than quoting
    coordinates need both, so they get the whole thing.
    """

    def __init__(self, body, parts, owner, classify=None):
        self.body = body
        self.parts = parts
        self.owner = owner
        self.normals = body.face_normals
        self.centres = body.triangles.mean(axis=1)
        self.classify = classify

    @cached_property
    def element_of(self) -> np.ndarray:
        """Element index per part — the inverse of `elements`."""
        index = np.empty(len(self.parts), dtype=int)
        for number, members in enumerate(self.elements):
            index[members] = number
        return index

    @cached_property
    def roles(self) -> list:
        """WALL or ROOF per part, read from the part's **element**.

        Classified on the element as built — its bodies unioned — for the same
        reason `uphill` sums over the element: a parapet's cap plate is a 29 mm
        slab and reads `ROOF` on its own, but it is not a roof, it is the top of
        a wall. Every leaf and cap of one element therefore reports the element's
        role, so a predicate asking `of_role(WALL)` gets the whole parapet.

        Measured on the headhouse parapets: per body, each parapet came back as
        a mix of `wall` leaves and `roof` caps; per element, all four are `wall`,
        and the roof layers stay `roof`.

        Where nothing is grouped every part is its own element, so this is the
        per-part classification unchanged — the transcribed `PART_N` case.

        `classify` is supplied by the caller rather than being
        `substrate.classify` with its thresholds defaulted: the thresholds are
        authored parameters, and a default here would be one of the hidden
        defaults the parameter layer exists to abolish. `None` is not a default
        value standing in for them — it is their absence, and it raises here, at
        the first predicate that asks what a part is.
        """
        if self.classify is None:
            raise ValueError(
                "Faces has no classifier: a predicate asked what a part is, but "
                "`classify` was not passed to Faces (usually from skin_over). Pass "
                "`partial(substrate.classify, margin=..., aspect=...)` with the "
                "authored thresholds — there is deliberately no default pair."
            )
        by_element = []
        for members in self.elements:
            by_element.append(
                substrate.role_of(self.classify, [self.parts[i] for i in members])
            )
        return [by_element[e] for e in self.element_of]

    @cached_property
    def elements(self) -> list:
        """Part indices grouped by the element each body belongs to.

        A **body** is the right unit for solidity — `from_obj` splits an object
        into its connected solids because the boolean must keep touching solids
        apart. It is the wrong unit for what a wall *is*. A baked wall arrives as
        an inner leaf, an outer leaf and a cap plate; those are not three walls
        with three directions, they are one wall, and only the cap carries its
        slope. Anything asking what a wall is *for* has to ask the element.

        `metadata["object"]` names it — the Blender object the bodies were split
        out of, stamped by `from_obj`. Where it is absent every part is its own
        element. That is the identity grouping, not a guess: a substrate that
        declares no grouping has each part standing alone, which is exactly the
        transcribed `PART_N` case.
        """
        return elements_of(self.parts)

    def of_role(self, role) -> np.ndarray:
        """Mask of faces belonging to a part of this role."""
        return np.array([r == role for r in self.roles])[self.owner]

    def tagged(self, key: str, value) -> np.ndarray:
        """Mask of faces whose part carries `metadata[key] == value`.

        The hook for facts geometry cannot know. Which cladding system a facade
        takes is the case in hand: no property of a wall's shape implies brick,
        so it is read off the part instead of derived. A substrate reader stamps
        it — in the student-house that is one read of the IFC material, not the
        classification tangle that made the old module brittle.
        """
        return np.array([p.metadata.get(key) == value for p in self.parts])[self.owner]

    def touching(self, target: np.ndarray) -> np.ndarray:
        """Mask of faces sharing an edge with any face in `target`."""
        near, far = self.body.face_adjacency.T
        out = np.zeros(len(self.owner), dtype=bool)
        out[near[target[far]]] = True
        out[far[target[near]]] = True
        return out


def _owner(body: trimesh.Trimesh, parts: list[trimesh.Trimesh]) -> np.ndarray:
    """Index of the part each face of the union came from.

    A union face lies exactly on one part's surface, so nearest-surface wins.
    Needed because the union merges coplanar faces across parts: the perimeter
    planes carry faces from several parts at once and they are not
    interchangeable.
    """
    centres = body.triangles.mean(axis=1)
    return np.array(
        [trimesh.proximity.closest_point(p, centres)[1] for p in parts]
    ).argmin(axis=0)


def _plane_rows(body) -> np.ndarray:
    """`(n_x, n_y, n_z, d)` per face."""
    return np.column_stack(
        [body.face_normals, (body.triangles[:, 0] * body.face_normals).sum(axis=1)]
    )


def _basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two axes spanning a plane, with `u x v` along the normal, so that a ring
    wound counter-clockwise in them is a face pointing that way."""
    u = np.cross(np.eye(3)[np.argmin(np.abs(normal))], normal)
    u /= np.linalg.norm(u)
    return u, np.cross(normal, u)


def _flat(points: np.ndarray, origin, u, v) -> np.ndarray:
    """Points of a plane in the plane's own two axes."""
    return np.column_stack([(points - origin) @ u, (points - origin) @ v])


def _rings(patch: list[list[int]]) -> list[list[int]]:
    """The boundary loops of a patch of triangles, as vertex index cycles.

    An edge two of the patch's triangles share is interior to it; the rest bound
    it. A vertex with more than two boundary edges is a pinch, where the loops
    cannot be walked without guessing which way to turn, and raises rather than
    guessing.
    """
    counted: dict[tuple[int, int], int] = {}
    for tri in patch:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edge = (min(a, b), max(a, b))
            counted[edge] = counted.get(edge, 0) + 1

    adjacent: dict[int, list[int]] = {}
    for (a, b), times in counted.items():
        if times == 1:
            adjacent.setdefault(a, []).append(b)
            adjacent.setdefault(b, []).append(a)
    pinched = [v for v, at in adjacent.items() if len(at) != 2]
    if pinched:
        raise ValueError(
            f"cannot re-tile a patch whose boundary pinches at vertex "
            f"{pinched[0]}: {len(adjacent[pinched[0]])} boundary edges meet there"
        )

    loops, left = [], set(adjacent)
    while left:
        start = min(left)
        loop, previous, current = [start], start, adjacent[start][0]
        while current != start:
            loop.append(current)
            a, b = adjacent[current]
            previous, current = current, b if a == previous else a
        loops.append(loop)
        left -= set(loop)
    return loops


def _shoelace(plan: np.ndarray) -> float:
    """Signed area of a 2D loop: positive counter-clockwise."""
    after = np.roll(plan, -1, axis=0)
    return float((plan[:, 0] * after[:, 1] - after[:, 0] * plan[:, 1]).sum() / 2)


def _retiled(patch: list[list[int]], verts: np.ndarray, normal: np.ndarray):
    """One planar patch of triangles, tiled again from its own boundary loops.

    The loops are the patch's outline and the holes in it, which is what the
    offset moved correctly; only the tiling between them is wrong. The widest
    loop is the outline and the rest are holes — a hole lies inside the outline,
    so it encloses less — and `manifold3d.triangulate` reads that off the
    winding.

    The tiled area is checked against the area the loops enclose, the same
    check `substrate`'s ear clipper makes and for the same reason: an outline
    that crosses itself tiles to well-formed triangles covering the wrong
    region, and there would be nothing else to notice.
    """
    loops = _rings(patch)
    u, v = _basis(normal)
    origin = verts[loops[0][0]]
    plans = [_flat(verts[loop], origin, u, v) for loop in loops]
    signed = [_shoelace(plan) for plan in plans]
    outline = int(np.argmax(np.abs(signed)))

    rings = []
    for i, (loop, plan, area) in enumerate(zip(loops, plans, signed)):
        if (area > 0) != (i == outline):  # outline counter-clockwise, holes not
            loop, plan = loop[::-1], plan[::-1]
        rings.append((loop, plan))

    index = [i for loop, _ in rings for i in loop]
    tiled = [
        [index[a], index[b], index[c]]
        for a, b, c in manifold3d.triangulate([plan for _, plan in rings], allow_convex=False)
    ]
    covered = sum(
        float(np.linalg.norm(np.cross(verts[b] - verts[a], verts[c] - verts[a])) / 2)
        for a, b, c in tiled
    )
    enclosed = abs(signed[outline]) - sum(
        abs(a) for i, a in enumerate(signed) if i != outline
    )
    # compared as a fraction of the patch's own area, not against a length:
    # this is a sum of triangle areas set against a shoelace, so what noise
    # there is scales with the patch, while a crossed outline is out by whole
    # slivers — the one this rule exists for is 200 655 mm2 against 28 m2
    if abs(covered - enclosed) > 1e-9 * max(enclosed, covered):
        raise ValueError(
            f"re-tiling a patch on plane {np.round(normal, 6).tolist()} covered "
            f"{covered:.9f} m2 where its outline encloses {enclosed:.9f} m2 — "
            f"the offset outline crosses itself"
        )
    return tiled


def _plane_ids(body):
    """One id per face, sharing an id where the faces share a plane, and the
    representative plane row per id.

    **Not** a rounded bucket. manifold3d leaves a union's faces up to ~5e-7 m off
    their true planes, which is half a `PLANE_TOL` lattice cell, so two faces of
    one plane fall either side of a boundary often enough to matter: the
    headhouse taper's top does exactly that in the shipping bake, its two halves
    7.8e-7 apart. Everything downstream that asks "is this the same plane" —
    which lap runs chain together, which faces a run-on may carry onto, which
    pairs are knives — would then silently answer no on a real surface, and a
    run-on that silently does not happen is the pinhole this rule exists to
    close. So each face is matched against the representatives already found,
    within the same tolerance used everywhere else.
    """
    held = body.metadata.get("plane_ids")
    if held is not None:
        return held
    rows = _plane_rows(body)
    reps: list[np.ndarray] = []
    ids = np.empty(len(rows), dtype=int)
    lookup: dict[tuple, int] = {}
    for f, row in enumerate(rows):
        key = tuple(np.round(row / PLANE_TOL).astype(np.int64))
        if key in lookup:
            ids[f] = lookup[key]
            continue
        found = next(
            (i for i, rep in enumerate(reps) if np.abs(rep - row).max() < PLANE_TOL),
            None,
        )
        if found is None:
            found = len(reps)
            reps.append(row)
        lookup[key] = ids[f] = found
    body.metadata["plane_ids"] = ids, np.array(reps) if reps else np.zeros((0, 4))
    return body.metadata["plane_ids"]


def _knives(body, ids, reps):
    """Faces lying on one plane, facing exactly opposite ways, **and touching**.

    The substrate has no thickness between such a pair, so a vertex they share
    has no offset: it would have to move `distance` both ways at once.
    `_reconcile` reports this where it survives into the solve; here it is a fact
    to route around while there is still a choice.

    Sharing a vertex is the whole of "touching", because that is where the
    contradiction lives — `_reconcile` is a per-vertex rule. Without it this is
    the same trap `_turn_out` and `_next_lift` each fell into: a shared plane is
    not a shared face. Two walls 2.6 m apart can present the same plane facing
    opposite ways, and pairing them would silently refuse a lap onto one because
    the skin happened to cover the other.
    """
    opposite = {}
    for i, rep in enumerate(reps):
        match = next(
            (j for j, other in enumerate(reps) if np.abs(other + rep).max() < PLANE_TOL),
            None,
        )
        if match is not None:
            opposite[i] = match

    at: dict[int, set] = {}
    for f, plane in enumerate(ids):
        for v in body.faces[f]:
            at.setdefault((int(v), int(plane)), set()).add(f)

    pairs: dict[int, set] = {}
    for f, plane in enumerate(ids):
        facing = opposite.get(int(plane))
        if facing is None:
            continue
        for v in body.faces[f]:
            for g in at.get((int(v), facing), ()):
                pairs.setdefault(f, set()).add(g)
                pairs.setdefault(g, set()).add(f)
    return pairs


def _knifed(body, kept):
    """Faces the skin may never lap onto: coplanar with, opposed to, and touching
    a face it covers.

    The shared vertex has no offset -- it would have to move `distance` both ways
    at once -- so a lap placed there is placed wrong, and covering both sides
    turns a fold `_reconcile` would quietly drop into one it has to raise on. A
    covered face outranks a lap onto its knife-mate, because `keep` is what the
    skin *is* and a lap is only its continuation.

    This is a property of the face, not of how the lap arrived at it, so both the
    seam-adjacent receivers and the faces a continuation may fold onto are
    filtered through it. Filtering only the receivers left the scupper's fold
    turning onto the roof taper's end at `x = 8.5` -- the very knife the fold at
    that plane has always been -- and put two 205 mm panels across the mouth of
    the slot.
    """
    ids, reps = _plane_ids(body)
    knife = _knives(body, ids, reps)
    blocked = np.zeros(len(kept), dtype=bool)
    for face, mates in knife.items():
        if any(kept[other] for other in mates):
            blocked[face] = True
    return blocked


def _receivers(body, kept, allowed):
    """The faces a lap actually turns onto: `allowed`, uncovered, and adjacent to
    what the skin covers.

    A predicate says which faces a skin *may* lap onto; this is which ones it
    reaches. The distinction matters twice over. It keeps the solve honest --
    `covered` is what the skin puts a surface on, and claiming a whole facade
    because one edge of it is lapped would hand `_reconcile` planes no skin ever
    uses. And it is what makes a lap a *local* continuation rather than a second
    face selection.

    **A knife is refused.** Where a candidate is coplanar with and opposed to
    something the skin already claims, the shared vertex has no offset at all,
    and covering both sides turns a fold `_reconcile` would quietly drop into
    one it has to raise on. So it is settled here, where there is still a choice
    to make: the lap turns onto the face at the **concave** arris and stops at
    the convex one. An internal corner is where the surface has to be
    continuous; at an external corner the two offset surfaces have already
    parted by twice the distance and there is nothing left to join.

    The scupper poses both. Its drip is exactly as wide as its slot, so the
    drip's end faces are coplanar with, and face the other way from, the slot's
    cheeks: the cheeks are the internal corner and the membrane wraps them, the
    drip's 100 x 70 mm ends are the external one and it stops there. And the
    roof taper's end stands 8.6 mm proud of the sill on the very plane the
    parapet's inner face occupies, which is the same contact the fold at
    `x = 8.5` has always been.

    Where a pair is convex on both sides, or concave on both, nothing is dropped
    and the contradiction goes to `_reconcile` to be raised rather than guessed
    at.
    """
    ids, reps = _plane_ids(body)
    knife = _knives(body, ids, reps)
    allowed = allowed & ~_knifed(body, kept)
    concave: dict[int, bool] = {}
    for (near, far), convex in zip(
        np.vstack([body.face_adjacency, body.face_adjacency[:, ::-1]]),
        np.concatenate([body.face_adjacency_convex] * 2),
    ):
        near, far = int(near), int(far)
        if not (kept[near] and allowed[far] and not kept[far]):
            continue
        # a knife shares an edge and reads as a 0-degree fold; it is not a seam
        # the surface can turn across, so it says nothing about this candidate
        if near in knife.get(far, ()):
            continue
        concave[far] = concave.get(far, False) or not bool(convex)

    claimed = kept.copy()
    for far in concave:
        claimed[far] = True

    refused = set()
    for far in concave:
        for other in knife.get(far, ()):
            if not claimed[other]:
                continue
            if kept[other]:
                refused.add(far)  # `_knifed` already dropped these; belt and braces
            elif concave[other] != concave[far] and not concave[far]:
                refused.add(far)

    receivers = np.zeros(len(kept), dtype=bool)
    for far in concave:
        if far not in refused:
            receivers[far] = True
    return receivers


def _across(body, a, b, far) -> np.ndarray:
    """The unit direction the skin continues in when it crosses onto face `far`.

    In `far`'s plane, perpendicular to the arris `a`-`b` it just crossed, and
    pointing into `far`. That is the whole of the direction rule, and it covers
    every continuation this module used to spell out separately: a skirt goes
    **down** because the wall face is below the coping's arris, an upstand goes
    **up** because the wall face is above the roof's, a collar runs **sideways**
    because the face it turns onto lies to the side.

    There is no axis to snap to. The receiving face carries the direction, so a
    turn off a shallow slope comes out exactly vertical by construction rather
    than by being rounded there -- which is what `_turn_out` needed its dominant
    axis for, because it extruded along the *departing* panel's normal instead.

    Read off `far`'s own third vertex, which lies on the interior side because
    `a`-`b` is one of that triangle's edges. A centroid would not do: it says
    nothing where a face straddles the seam, and says the wrong thing where the
    face is long and the seam near one end.
    """
    e = body.vertices[b] - body.vertices[a]
    e = e / np.linalg.norm(e)
    third = [v for v in body.faces[far] if v not in (a, b)][0]
    t = body.vertices[third] - body.vertices[a]
    t -= (t @ e) * e
    t = t / np.linalg.norm(t)

    # A lap springing off a *sloped* arris -- a cap plate laid to fall, run into
    # by a wall -- comes out perpendicular to that arris and so tilted by the
    # fall, and an upstand tilted 2 degrees is not what a 205 mm upstand means:
    # like a drip, it is a height, measured vertically. So a lap already within
    # `RAKE` of level is made exactly level, which is the same priority
    # `planar_offset` gives level planes and the reason `drop` could be a plain
    # `[0, 0, -drop]` before this.
    #
    # Only within `RAKE`. The threshold was 45 degrees at first, and that
    # rounded a lap raking 40 degrees *down* onto the horizontal -- whereupon
    # `reach` read the flattened `t_z` and billed it the 205 mm upstand instead
    # of the 62 mm drip. A lap that genuinely rakes keeps the direction it has
    # and is priced by it. Nothing is snapped to an *axis*: a wall at any plan
    # angle laps along its own direction.
    if abs(t[2]) > 1.0 - RAKE:
        return np.array([0.0, 0.0, np.sign(t[2])])
    if abs(t[2]) < RAKE:
        flat = np.array([t[0], t[1], 0.0])
        return flat / np.linalg.norm(flat)
    return t


def _key(point) -> tuple:
    """A point's identity on the 1 um lattice, for joining laps end to end."""
    return tuple(np.round(np.asarray(point) / PLANE_TOL).astype(np.int64))


def _inside(tri, point, normal) -> bool:
    """Is `point` inside this coplanar triangle? Boundary contact counts.

    Boundary contact is the whole point: a lap reaching the end of the face it
    laps onto touches the next face exactly on their shared arris, and a test
    that wanted the interior would never see it.
    """
    axes = [k for k in range(3) if k != int(np.abs(normal).argmax())]
    t, q = tri[:, axes], np.asarray(point)[axes]
    side = []
    for i in range(3):
        u, v = t[i], t[(i + 1) % 3]
        run = v - u
        length = float(np.linalg.norm(run))
        if length == 0.0:
            return False
        side.append(float(run[0] * (q - u)[1] - run[1] * (q - u)[0]) / length)
    side = np.array(side)
    return bool((side > -PLANE_TOL).all() or (side < PLANE_TOL).all())


def _leaves(tri, here, direction, normal) -> float:
    """How far along `direction` from `here` this coplanar triangle reaches.

    The largest parameter at which the ray is still inside it: the ray is
    intersected with each edge in the triangle's own plane and the furthest
    crossing wins. Zero if it leaves immediately.
    """
    axes = [k for k in range(3) if k != int(np.abs(normal).argmax())]
    p, d, t = np.asarray(here)[axes], np.asarray(direction)[axes], tri[:, axes]
    far = 0.0
    for i in range(3):
        a, e = t[i], t[(i + 1) % 3] - t[i]
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-15:
            continue
        gap = a - p
        along = (gap[0] * e[1] - gap[1] * e[0]) / den
        across = (gap[0] * d[1] - gap[1] * d[0]) / den
        if -PLANE_TOL <= across <= 1 + PLANE_TOL and along > far:
            far = float(along)
    return far


def _room(body, here, direction, on_plane, normal, want) -> float:
    """How far a lap can run from `here` before it leaves the surface it is on.

    A lap places a whole quad — there is no cutting in `_lap` — so a band wider
    than the face it lands on does not overhang, it is refused or shortened to
    fit. This is what decides which.

    It marches: find the coplanar triangles holding the point just past `here`,
    take the furthest exit any of them offers, look for coplanar neighbours
    holding the point just past *that*, and carry on. Marching rather than
    testing the far end alone, because the union triangulates a face and one lap
    commonly crosses several triangles of it — the drip down a 34 mm cap plate
    runs straight on over the parapet's coplanar face below and must be allowed
    its full 62 mm.

    **Every triangle holding the probe, not the first one found.** A lap starts
    on an arris, so the probe sits on a shared edge or a shared corner every
    time, and two or three coplanar triangles hold it while only some of them
    carry the ray onward. Reading the first in index order made the answer depend
    on how the union happened to triangulate the face: the cornice's two ends are
    one detail mirrored, and the march ran the full 205 mm off the north one and
    stopped dead at the south one, where a triangle cornering on the probe came
    first and reported no room at all.
    """
    reached = 0.0
    for _ in range(len(on_plane) + 1):
        step = here + direction * (reached + PLANE_TOL * 8)
        onward = [
            _leaves(body.triangles[f], here, direction, normal)
            for f in on_plane
            if _inside(body.triangles[f], step, normal)
        ]
        if not onward:
            return reached
        moved = max(onward)
        if moved <= reached + PLANE_TOL:
            return reached  # the surface is held here but carries the ray no further
        reached = moved
        if reached >= want:
            return want
    return min(reached, want)


def _lap(body, verts, distance, covered, lappable, onto, skinned_wall, drop, out, rounds=3):
    """Continue the skin onto every substrate face it runs into.

    Where a covered face meets a face this skin does not cover, the skin does
    not stop on the arris: it turns and laps across the face beyond. `_across`
    gives the direction, and which of the two authored distances applies follows
    from that direction rather than from any face selection. That one rule is
    the skirt, the flange and the collar together, which this module used to
    hold as two functions elected by two predicates.

    A lap that **hangs below** its arris is a drip, and is measured on the
    substrate -- from the arris itself, mitered onto the offset planes of every
    skinned vertical face meeting at that vertex. A lap that **rises or runs
    sideways** is an upstand, and is measured from the skin's own edge. Both
    conventions predate this function and both are deliberate: a drip is set out
    from the edge of the coping it drips off, an upstand from the finished
    surface it rises out of. They are the one thing that did not unify, and they
    are why two distances are still authored.

    **A lap does not stop where the face it laps onto stops** (Duncan,
    2026-08-20). At the free end of a run it asks what the substrate presents
    there, and there are exactly three answers:

    * *the same plane carries on* -- an in-line butt, where a parapet runs into a
      wall presenting the very same face. The lap runs on, which is the whole of
      the fix for the pinhole at `Parapet-Unit8-N`'s east end where three open
      edges used to converge on one vertex.
    * *another face meets it at an arris* -- the lap folds round the corner onto
      that face. This carries the upstand at that junction onto `Headhouse-N`'s
      north face, and turns the rig's exterior-wall skirt out onto part 4.
    * *nothing* -- the lap ends. Duncan's stop condition, exactly.

    Laps are **chained and mitered within each receiving plane**, so a run that
    changes direction along one face closes at the turn: the miter is the
    intersection of the two outer lines, extending a pair that would gap and
    trimming a pair that would overlap. Across planes there is nothing to miter
    -- two outer lines on different faces do not meet, and asking for their
    intersection gets a least-squares answer from out in space, which threw a
    400 mm triangle across the scupper's mouth the one time it was tried. Two
    drips at a wall corner need no miter anyway: `drip_at` already solves their
    shared arris vertex on both planes at once.
    """
    mitered: dict[int, np.ndarray] = {}

    def drip_at(v: int) -> np.ndarray:
        """The arris vertex, mitered onto every skinned vertical plane at it.

        Raises where there is no such plane. `np.linalg.lstsq` on a zero-row
        system returns `[0, 0, 0]` rather than complaining, which would root the
        drip on the **substrate** instead of `distance` out from it -- geometry
        buried in the solid, with a clean residual and nothing to report it. The
        two shipped `lap` predicates cannot reach this, since both admit only
        vertical faces and a drip's receiver is one of them; a predicate that
        admits a sloped receiver can, and should be told so rather than skinned
        wrongly.
        """
        if v not in mitered:
            at = body.vertex_faces[v]
            at = [f for f in at[at >= 0] if skinned_wall[f]]
            if not at:
                raise ValueError(
                    f"no skinned vertical face at vertex {v} "
                    f"{body.vertices[v].tolist()} to miter a drip onto. A drip is "
                    f"measured on the substrate, from the arris mitered onto the "
                    f"offset planes of the vertical faces meeting there, and this "
                    f"vertex has none — the skin is lapping downward onto a face "
                    f"that is not vertical. Either narrow this skin's `lap` "
                    f"predicate to vertical faces, or give it `drop: 0.0`"
                )
            normals = np.unique(np.round(body.face_normals[at] / PLANE_TOL), axis=0)
            t = np.linalg.lstsq(
                normals * PLANE_TOL, np.full(len(normals), distance), rcond=None
            )[0]
            mitered[v] = body.vertices[v] + t
        return mitered[v]

    V = np.asarray(verts, dtype=float)
    planes = _plane_rows(body)
    # plane identity is `_plane_ids`, not a rounded key: a run that failed to
    # chain because its two halves landed either side of a lattice boundary would
    # silently not run on, which is the whole failure this rule fixes
    ids, _ = _plane_ids(body)
    coplanar: dict[int, list] = {}
    for f, plane in enumerate(ids):
        coplanar.setdefault(int(plane), []).append(f)

    def reach(t):
        """A drip hangs `drop`; anything that rises or runs sideways goes `out`."""
        return drop if t[2] < -PLANE_TOL else out

    def seg(pa, pb, qa, qb, t, far, va=None, vb=None):
        return {
            "pa": np.asarray(pa, float), "pb": np.asarray(pb, float),
            "qa": np.asarray(qa, float), "qb": np.asarray(qb, float),
            # the substrate vertices the seam sits on, where it sits on any. An
            # end that has one can be asked what the substrate offers past it;
            # an end that does not -- the far end of a run-on, the rim end of a
            # fold -- is out over the offset and has nothing left to ask
            "va": va, "vb": vb,
            "t": t, "far": int(far), "plane": int(ids[far]),
            "out": body.face_normals[far],
        }

    segs = []
    for (f, g), (a, b) in zip(body.face_adjacency, body.face_adjacency_edges):
        for near, far in ((f, g), (g, f)):
            if not (covered[near] and lappable[far] and not covered[far]):
                continue
            a, b, far = int(a), int(b), int(far)
            t = _across(body, a, b, far)
            want = reach(t)
            if want == 0.0:
                continue  # that direction is switched off for this skin
            # shortened to what the receiving face actually offers, measured
            # from both ends of the seam so the band stays a band. Without this
            # a 205 mm upstand onto a 34 mm cap-plate reveal ran 120 mm above
            # the wall and through the cladding's coping
            want = min(
                want,
                *(
                    _room(body, body.vertices[v], t, coplanar[int(ids[far])],
                          body.face_normals[far], want)
                    for v in (a, b)
                ),
            )
            if want < PLANE_TOL:
                continue
            root = drip_at if t[2] < -PLANE_TOL else (lambda v: V[v])
            step = t * want
            segs.append(
                seg(V[a], V[b], root(a) + step, root(b) + step, t, far, va=a, vb=b)
            )

    if not segs:
        return []

    def at_a(one, where):
        return _key(one["pa"]) == where

    def inner(one, where):
        return one["pa"] if at_a(one, where) else one["pb"]

    def outer(one, where):
        return one["qa"] if at_a(one, where) else one["qb"]

    def sits_on(one, where):
        return one["va"] if at_a(one, where) else one["vb"]

    def runs():
        """Runs of laps meeting end to end, grouped by the face they lap onto."""
        by_plane: dict[tuple, list] = {}
        for k, one in enumerate(segs):
            by_plane.setdefault(one["plane"], []).append(k)
        found = []
        for members in by_plane.values():
            touching: dict[tuple, list] = {}
            for k in members:
                touching.setdefault(_key(segs[k]["pa"]), []).append(k)
                touching.setdefault(_key(segs[k]["pb"]), []).append(k)
            taken: set = set()

            def walk(start, touching=touching, taken=taken):
                chain, cur = [], start
                while True:
                    nxt = [k for k in touching.get(cur, ()) if k not in taken]
                    if not nxt:
                        return chain
                    k = nxt[0]
                    taken.add(k)
                    one, two = _key(segs[k]["pa"]), _key(segs[k]["pb"])
                    chain.append((k, cur, two if one == cur else one))
                    cur = chain[-1][2]

            found += [walk(v) for v, ks in touching.items() if len(ks) == 1]
            found += [walk(_key(segs[k]["pa"])) for k in members if k not in taken]
        return [run for run in found if run]

    convexity = {}
    for (f, g), convex in zip(body.face_adjacency, body.face_adjacency_convex):
        convexity[(int(f), int(g))] = bool(convex)
        convexity[(int(g), int(f))] = bool(convex)

    def arris_at(v, plane):
        """Faces meeting this plane at an arris through substrate vertex `v`."""
        at = body.vertex_faces[v]
        at = {int(f) for f in at[at >= 0]}
        found = []
        for near in at:
            if int(ids[near]) != plane:
                continue
            for far in at:
                if (near, far) not in convexity:
                    continue
                if not onto[far] or covered[far] or int(ids[far]) == plane:
                    continue
                found.append((near, far, convexity[(near, far)]))
        return found

    def carry_on(k, back, here):
        """Run the lap past its tip, fold it round the corner, or leave it.

        The three answers Duncan's rule allows, asked in that order. Both need
        to know where the tip stands on the substrate, so an end that is out
        over the offset -- the far end of a run-on, the rim end of a fold --
        simply stops, which is what bounds the recursion.
        """
        one = segs[k]
        tip = sits_on(one, here)
        if tip is None:
            return False
        # the seam's own direction, taken from its two ends as *points*. Taking
        # it from their substrate vertices instead blocks the second end of any
        # segment whose first end has already run on: running on clears that
        # end's vertex, and the far end is exactly what this needs to know the
        # direction. A symmetric substrate then came out lapped on one side.
        along = inner(one, here) - inner(one, back)
        span = float(np.linalg.norm(along))
        if span < PLANE_TOL:
            return False
        along = along / span
        # a run is only free at its end if nothing else turns the same way
        # there. Two drips meeting at a building corner are one band turning
        # through 90 degrees -- `drip_at` already solved their shared arris on
        # both planes -- and treating either as free would fold it onto the
        # other and leave a hole where the drip used to be. An upstand meeting a
        # drip at the same vertex is a different matter: they turn opposite ways
        # and the corner between them is genuinely open, which is the whole of
        # the north junction.
        for other in segs:
            if other is one or not np.allclose(other["t"], one["t"], atol=PLANE_TOL):
                continue
            if here in (_key(other["pa"]), _key(other["pb"])):
                return False
        stand = body.vertices[tip]
        # A run-on runs **sideways**, along the surface, so it is an upstand's
        # `out` and never a drip's `drop`. `reach` prices a *lap* direction --
        # the way the band leaves its arris -- and asking it about the direction
        # of the run is a category error: it read a seam raking down a sloped
        # coping as a drip and billed the run-on 62 mm at one end of that coping
        # and 205 mm at the other, purely because the two ends face opposite ways
        # along the fall.
        #
        # A skin whose `out` is zero has nowhere to run on -- but it may still
        # **fold**, which is priced by `reach(into)` and is `drop` for a fold
        # that turns downward. So this gates the run-on alone and not the whole
        # of `carry_on`: an early return here would have denied the cladding,
        # whose `out` is 0.0 and whose `drop` is not, every corner it turns.
        want = out

        # how far the plane actually carries on past the tip, marched rather
        # than sampled. Testing the tip and the far end alone -- the first
        # version -- ran the lap straight over a void between two coplanar
        # bodies and left it hanging in the gap. A run-on is not cut to fit
        # either, because it lengthens a quad rather than adding one, so it runs
        # its whole length or not at all. The scupper is why the length matters:
        # the parapet's inner face meets the cheek 8.6 mm above the sill, and a
        # 62 mm drip run on down from there goes straight into the parapet.
        probe = stand + along * PLANE_TOL * 8
        whole = want > 0.0 and _room(
            body, stand, along, coplanar[one["plane"]], one["out"], want
        ) >= want - PLANE_TOL
        for far in coplanar[one["plane"]] if whole else ():
            if far == one["far"] or not _inside(body.triangles[far], probe, one["out"]):
                continue
            # the same plane carries on: lengthen this lap rather than starting
            # another, so the two share an edge instead of butting along one
            move = along * want
            side = "a" if at_a(one, here) else "b"
            one["p" + side] = one["p" + side] + move
            one["q" + side] = one["q" + side] + move
            one["v" + side] = None
            return True

        # nothing coplanar, so look for a face meeting this one at the arris the
        # tip stands on, and fold the lap round onto it
        for near, far, convex in arris_at(tip, one["plane"]):
            n = body.face_normals[near]
            # crossing an arris, the surface turns away from the face it leaves
            # at a convex edge and toward it at a concave one. That sign is the
            # whole of the direction: a centroid cannot supply it, because the
            # receiving plane very often has surface on both sides of the arris
            # -- part 4's face runs the full width of the rig, past both sides
            # of the wall whose skirt turns onto it.
            into = (-n if convex else n)
            into = into - (into @ body.face_normals[far]) * body.face_normals[far]
            if np.linalg.norm(into) < PLANE_TOL:
                continue
            into = into / np.linalg.norm(into)
            if reach(into) == 0.0:
                continue
            step = into * reach(into)
            side, rim = inner(one, here), outer(one, here)
            if _key(side) == _key(rim):
                continue
            # the fold only works where the edge it springs from already lies on
            # the receiving face's own offset plane, which is what a mitered
            # arris gives it. Where it does not -- a drip whose outer point was
            # mitered across other planes than this one -- the band would float
            # off the face by the offset, so leave it rather than place it wrong
            facing = body.face_normals[far]
            level = planes[far, 3] + distance
            if max(abs(side @ facing - level), abs(rim @ facing - level)) > PLANE_TOL:
                continue
            # ...and it has to land on the face from **both** ends of that edge.
            # Checking one end said "all of it lands on the face" while testing a
            # single point of it, so a fold onto a face shallower than its seam
            # is long hung over the end of it. Marched on the substrate, so the
            # ends come back off the offset plane first -- and then back onto the
            # arris, which is the second offset. The seam lies on the offset of
            # the face the lap is *leaving* as well, so it sits `distance` off the
            # arris along `into`: past it at a concave corner, which is harmless,
            # and short of it at a convex one, where the march then starts out
            # over the void beyond the corner and reports no room at all. That is
            # what stopped the Unit8 coping's upstand wrapping the building corner
            # onto `Headhouse-N`. `tip` is on the arris, so it supplies the slide.
            on_plane = coplanar[int(ids[far])]

            def at_arris(end, into=into, facing=facing, stand=stand):
                base = end - facing * distance
                return base + ((stand - base) @ into) * into

            if any(
                _room(body, at_arris(end), into, on_plane, facing,
                      reach(into)) < reach(into) - PLANE_TOL
                for end in (side, rim)
            ):
                continue
            seam = {_key(side), _key(rim)}
            if any(
                other["plane"] == int(ids[far])
                and {_key(other["pa"]), _key(other["pb"])} == seam
                for other in segs
            ):
                continue  # already lapped onto that face along this arris
            segs.append(seg(side, rim, side + step, rim + step, into, far, va=tip))
            return True
        return False

    # One continuation at a time, re-reading the runs after each. A run-on moves
    # the seam it lengthens, so every key taken from `runs()` before it -- the
    # *other* end of that same run included -- is stale the moment it fires. Held
    # over a whole pass, that made a symmetric substrate come out asymmetric: a
    # low wall butting a tall one at both ends ran on at one end and read the
    # opposite end's vertex as its own, which the `tip == root` guard then
    # blocked for good. `rounds` bounds the whole loop rather than the passes,
    # since an end that has already been carried on no longer sits on a substrate
    # vertex and cannot be carried on again.
    tried: set = set()
    while True:
        pending = [
            (k, back, here)
            for run in runs()
            for k, back, here in (
                (run[0][0], run[0][2], run[0][1]),
                (run[-1][0], run[-1][1], run[-1][2]),
            )
            if (k, here) not in tried
        ]
        if not pending:
            break
        # `tried` grows by one every pass and nothing is ever removed from it,
        # so this terminates on its own. `rounds` is the safety net, and it
        # **raises** rather than stopping quietly -- running out of it would drop
        # laps with no sign that anything was missing, which is the
        # silent-omission failure this module is written against. It was a fixed
        # count of the *initial* segments before, and `carry_on` appends: 27
        # segments became 33 on the shipping bake and the bound was read once,
        # at 27.
        #
        # A band costs up to **four** entries, not two: it has two ends, and a
        # run-on moves the end it lengthens, so that end is asked again under its
        # new key and refused at once because the run-on cleared its substrate
        # vertex. Against a bound of `rounds` per band the rig already measures
        # 2.00, which left a substrate whose laps run on at both ends tripping a
        # raise that blames the geometry for a correct model. The ceiling is 2
        # per end; `rounds` is headroom above it.
        if len(tried) >= rounds * 2 * max(len(segs), 1):
            raise ValueError(
                f"the lap is still finding somewhere to continue after "
                f"{len(tried)} attempts over {len(segs)} bands. Either the "
                f"substrate has a run of faces this rule walks forever, or "
                f"`rounds` is too low for it — it is a safety net, not a budget "
                f"to spend, so raise it only after checking the geometry"
            )
        k, back, here = pending[0]
        tried.add((k, here))
        carry_on(k, back, here)

    index: dict[tuple, int] = {_key(v): i for i, v in enumerate(verts)}

    def vertex(point):
        where = _key(point)
        if where not in index:
            index[where] = len(verts)
            verts.append(np.asarray(point, float))
        return index[where]

    def corner(k1, k2, where):
        """Where the two outer lines meet, or one tip if they do not turn."""
        p1, p2 = outer(segs[k1], where), outer(segs[k2], where)
        u1 = segs[k1]["pb"] - segs[k1]["pa"]
        u2 = segs[k2]["pb"] - segs[k2]["pa"]
        # on unit vectors: the cross product of two raw seam directions scales
        # with their lengths, so a pair of 3 mm seams read parallel below 6 deg
        # and a pair of 1 mm ones at any angle at all, and the miter was skipped
        if np.linalg.norm(np.cross(u1 / np.linalg.norm(u1), u2 / np.linalg.norm(u2))) < PLANE_TOL:
            return p1  # the same lap continuing; nothing to miter
        if np.linalg.norm(p1 - p2) < PLANE_TOL:
            return p1  # already agreed -- two drips sharing one mitered arris
        s = np.linalg.lstsq(np.column_stack([u1, -u2]), p2 - p1, rcond=None)[0][0]
        return p1 + s * u1

    faces = []
    for run in runs():
        rim = [vertex(outer(segs[run[0][0]], run[0][1]))]
        for (k1, _, mid), (k2, _, _) in zip(run, run[1:]):
            rim.append(vertex(corner(k1, k2, mid)))
        rim.append(vertex(outer(segs[run[-1][0]], run[-1][2])))

        for n, (k, a, b) in enumerate(run):
            one = segs[k]
            loop = [vertex(inner(one, a)), vertex(inner(one, b)), rim[n + 1], rim[n]]
            if len(set(loop)) < 4:
                continue  # a lap with no width or no length; nothing to emit
            pts = np.array([verts[i] for i in loop])
            if np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0) @ one["out"] < 0:
                loop = loop[::-1]
            faces += [[loop[0], loop[1], loop[2]], [loop[0], loop[2], loop[3]]]
    return faces


def _cut(verts, faces, normal, d):
    """Cut `faces` at the plane `normal . p = d`, keeping `normal . p <= d`.

    The one cutting primitive. Its only caller so far is `base`, the horizontal
    datum a skin stops at, but nothing about it is particular to a level plane.
    A cut, not a projection or a clamp: both of those would move vertices off
    their offset planes, and re-cutting the straddling triangles instead leaves
    every remaining plane where it was.

    Crossings are cached per edge, so the two triangles sharing one get the same
    vertex rather than two that agree to within a rounding — the seam between
    them would otherwise crack open. The cache is per call, which is why a
    caller with several planes to cut at cuts **all** the faces at one plane
    before moving to the next.

    Which side a vertex is on is decided **exactly**, with no tolerance band. A
    band is the obvious thing to reach for and is wrong here: the crossing
    interpolates to exactly the plane, so a vertex inside the band but past it
    would be called "inside" while the interpolation, solving for a plane it is
    already past, runs the parameter negative and puts the cut vertex *outside*
    the edge it was cutting. A near-horizontal panel a fraction of a micron
    under the datum came out 333 mm wide that way. The tolerance belongs on the
    positions instead, where the duplicate drop below applies it.

    Returns the surviving faces and, for each, the index of the face it came
    from, so a caller carrying anything per-face can carry it through the cut.
    """
    normal = np.asarray(normal, dtype=float)

    cuts: dict[tuple[int, int], int] = {}

    def past(i) -> float:
        return float(normal @ verts[i]) - d

    def crossing(i: int, j: int) -> int:
        key = (i, j) if i < j else (j, i)
        if key not in cuts:
            p, q = np.asarray(verts[key[0]]), np.asarray(verts[key[1]])
            hp, hq = normal @ p - d, normal @ q - d
            point = p + hp / (hp - hq) * (q - p)
            point -= (normal @ point - d) * normal  # exactly on it, not a rounding away
            cuts[key] = len(verts)
            verts.append(point)
        return cuts[key]

    kept, source = [], []
    for f, face in enumerate(faces):
        inside = [past(i) <= 0 for i in face]
        if all(inside):
            kept.append(face)
            source.append(f)
            continue
        if not any(inside):
            continue

        loop: list[int] = []
        for n, i in enumerate(face):
            j = face[(n + 1) % len(face)]
            if inside[n]:
                loop.append(i)
            if inside[n] != inside[(n + 1) % len(face)]:
                loop.append(crossing(i, j))

        # a corner sitting on the plane makes its own crossing a duplicate; drop
        # those before fanning, or the cut sheds zero-area triangles
        loop = [
            v
            for n, v in enumerate(loop)
            if np.linalg.norm(np.asarray(verts[v]) - verts[loop[n - 1]]) > PLANE_TOL
        ]
        # a triangle cut by a plane is convex, so a fan from any corner is safe
        kept += [[loop[0], loop[n], loop[n + 1]] for n in range(1, len(loop) - 1)]
        source += [f] * max(0, len(loop) - 2)
    return kept, source


def _trim_below(verts, faces, base):
    """Cut the surface at the horizontal plane z = `base`, keeping what is above.

    A skin ending against an *unskinned* neighbour sits on the miter it would
    have had if that neighbour were skinned too, so cladding whose facades miter
    with the substrate's unskinned underside runs `distance` below the base
    plane. That is correct as offset geometry and wrong as building: cladding
    stops at the ground. `base` is the datum it stops at.

    The cut itself is `_cut`, which this expresses as the half-space
    `-z <= -base`. What is particular to a datum is only that missing it
    entirely is a mistake worth naming: a `base` above the whole skin leaves
    nothing at all.
    """
    kept, _ = _cut(verts, faces, np.array([0.0, 0.0, -1.0]), -base)
    if not kept:
        raise ValueError(
            f"trimming at base={base} leaves nothing: every face of this skin is "
            f"below it. `base` is a height in the model, not a depth below the "
            f"skin — check the datum authored in skins.<name>.base"
        )
    return kept


def _tiling(body, skin, kept) -> list[list[int]]:
    """The kept faces, with any patch the offset turned inside out tiled again.

    `planar_offset` moves vertices and keeps the union's triangulation, and
    manifold3d tiles a face with a hole cut in it by fanning across the hole. A
    vertex that starts closer to one of those diagonals than `distance` crosses
    it when it moves, and its triangle comes out **inside out** — covering a
    sliver on the far side of the diagonal, which is surface the offset never
    placed. On the live bake that sliver fills in the bottom right of the notch
    the cladding leaves round the scupper cornice: `Cornice-Headhouse-E`'s
    corner sits 4.7 mm from the diagonal of the parapet facade it is cut in, and
    the 85 mm offset takes it clean across.

    The outline is offset correctly and so are the holes; only the tiling
    between them is wrong, and an inversion does not move a boundary edge. So
    the patch is tiled again from its own loops. Detection is exact and wants no
    threshold: the body's own normal says which way each face is meant to face.

    Applies to a patch that inverted and nowhere else — every other patch is
    passed through in its original order, triangle for triangle — so nothing
    that tiles correctly today changes by a bit.
    """
    index = np.flatnonzero(kept)
    faces = [skin.faces[i].tolist() for i in index]
    corners = skin.vertices[skin.faces[index]]
    turned = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    inverted = np.einsum("ij,ij->i", turned, body.face_normals[index]) < 0
    if not inverted.any():
        return faces

    # patches are coplanar faces joined edge to edge. Sharing a plane is not
    # enough: two walls in line share one, and tiling across the gap between
    # them would invent surface. `_plane_ids` keys on `(n, d)`, so the two sides
    # of a knife are already separate ids and cannot be joined here
    ids, _ = _plane_ids(body)
    parent = list(range(len(faces)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    along: dict[tuple[int, int], int] = {}
    for k, tri in enumerate(faces):
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edge = (min(a, b), max(a, b))
            other = along.get(edge)
            if other is not None and ids[index[other]] == ids[index[k]]:
                parent[root(k)] = root(other)
            along[edge] = k

    members: dict[int, list[int]] = {}
    for k in range(len(faces)):
        members.setdefault(root(k), []).append(k)

    tiled = []
    for k, tri in enumerate(faces):
        patch = members[root(k)]
        if not any(inverted[m] for m in patch):
            tiled.append(tri)
        elif k == patch[0]:  # the whole patch, at the first of its faces
            tiled += _retiled(
                [faces[m] for m in patch],
                skin.vertices,
                body.face_normals[index[patch[0]]],
            )
    return tiled


def skin_over(
    parts: list[trimesh.Trimesh],
    distance: float,
    keep=None,
    lap=None,
    drop: float = 0.0,
    out: float = 0.0,
    base: float | None = None,
    classify=None,
) -> trimesh.Trimesh:
    """Offset an assembly of parts as a single body.

    The parts are unioned only to find the outer surface -- faces where parts
    touch are interior to that union, so no skin is generated between them. The
    union is a local intermediate and is discarded; `parts` is left untouched
    and stays the substrate geometry.

    `keep(Faces)` selects the faces the skin covers, returning an open surface
    rather than a closed shell. The offset is still solved over the whole body
    first, so vertices on the edge of the selection sit on the same miter they
    would have if the neighbouring faces were skinned too — the surface stops
    there rather than being offset in isolation.

    `lap(Faces)` selects the faces the skin may **continue onto** where it runs
    into them. It is not a second face selection: a lap is a band `drop` or
    `out` metres wide springing off the arris where the covered surface ends,
    and only the faces actually reached get one. `_lap` derives which of the two
    distances applies from the direction it turns in, so a skirt hanging off a
    coping, an upstand rising against a wall and a collar running sideways round
    a corner are all one rule with no election between them.

    `base` cuts the finished surface at that height and keeps what is above it,
    for a skin that stops at a datum rather than at its own miter — the cladding
    at ground level. `None` is no trim, and is not the same as `0.0`: a height of
    zero is a height, where a `drop` or an `out` of zero is a feature switched
    off. It is applied last, after the laps, so it means "no part of this skin
    goes below `base`" rather than "the offset stops there".

    `classify(part) -> role` is handed to `Faces` for the predicates to read. It
    is the caller's, thresholds already bound, because those thresholds are
    authored parameters — see `Faces.roles`. Only predicates that ask about roles
    need it, so a plain closed-shell offset can leave it out.
    """
    body = substrate.union(parts)   # about the origin; see substrate.union
    if keep is None:
        return planar_offset(body, distance)

    surface = Faces(body, parts, _owner(body, parts), classify)
    kept = keep(surface)
    allowed = (
        np.zeros(len(kept), dtype=bool) if lap is None else lap(surface)
    )
    receivers = _receivers(body, kept, allowed)

    # everything this skin puts a surface on. Only a fold consults it
    skin = planar_offset(body, distance, covered=kept | receivers)

    verts = list(skin.vertices)
    faces = _tiling(body, skin, kept)

    if receivers.any():
        height = np.abs(body.face_normals[:, 2])
        faces += _lap(
            body,
            verts,
            distance,
            covered=kept,
            lappable=receivers,
            # a lap turning a corner lands on a face that need not itself adjoin
            # anything covered -- at the north junction it turns onto a wall the
            # roof never reaches -- so what it may spread onto is the whole of
            # what the skin is allowed to lap onto, not just what it reached.
            # Knives are the one exception, and they are the same exception
            # `_receivers` makes: there is no offset for the vertex at all
            onto=allowed & ~kept & ~_knifed(body, kept),
            # every skinned vertical plane miters a drip, the ones it laps onto
            # included -- otherwise the corner where two walls meet splits open
            skinned_wall=(kept | receivers) & (height < PLANE_TOL),
            drop=drop,
            out=out,
        )

    if base is not None:
        faces = _trim_below(verts, faces, base)

    surface = trimesh.Trimesh(vertices=np.array(verts), faces=faces)
    surface.metadata.update(skin.metadata)
    return surface
