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
# two points closer than this are one point. Deliberately **not** `PLANE_TOL`,
# which is the 1 µm lattice every substrate coordinate is snapped to — welding at
# that radius merges neighbouring lattice points. Same value and same reasoning
# as `clean.WELD_TOL`, declared again rather than imported: `skinning/skin/clean.py` is
# the only module that needs shapely and nothing in the core may reach into it
WELD_TOL = 1e-9
# keeps the KKT system non-singular where the soft equations underdetermine a vertex
RIDGE = 1e-9
# a lap this close to level is level: the direction cosine a cap plate's own fall
# puts into a lap perpendicular to its arris, rounded off so an upstand is a
# height. Not a plane tolerance -- see `_across`
RAKE = 0.05


def _vertex_planes(mesh, vertex: int, tol: float, offsets=None, only=None, instead=None):
    """`(normals, offsets)` — the distinct planes meeting at `vertex`.

    Normals within `tol` of an axis are snapped onto it: the union that feeds
    this carries float32 vertices, and an axis-aligned face whose normal is off
    by 1e-7 would otherwise be held to a hard constraint that is itself skew.
    A face with **no area** is dropped rather than snapped — it states no plane,
    and its zero-length normal makes an unsatisfiable hard equation.

    `only` is a face mask restricting which incident faces are read. It is used
    solely to re-read a contradictory vertex — see `_reconcile`.

    `instead` is `{face: normal}`, substituting a face's normal for another. It
    carries the far half of a knife the skin covers — see `_knife_side`.

    `offsets` is how far each **face**'s plane moves, and is `None` for the
    ordinary case where the whole body moves by one distance. It is per face
    rather than per skin because a skin ending against a neighbour dressed by a
    *different* system mitres onto that system's plane, not onto its own — see
    `planar_offset`. Two incident faces are one plane here, so a group that
    disagrees is two systems claiming one plane at one point, and it raises
    rather than picking: no offset of this vertex satisfies both.
    """
    faces = mesh.vertex_faces[vertex]
    faces = faces[faces >= 0]
    if only is not None:
        faces = faces[only[faces]]
    if not len(faces):
        return np.zeros((0, 3)), np.zeros(0)
    normals = mesh.face_normals[faces]
    if instead:
        normals = normals.copy()
        for row, face in enumerate(faces):
            swap = instead.get(int(face))
            if swap is not None:
                normals[row] = swap
    # a face with no area states no plane, and `_opposed` already drops its
    # zero-length normal for that reason. It has to be dropped *here* too, or it
    # reaches the solve as a constraint row of zeros: `abs(n_z) < tol` reads a
    # zero normal as level, so it is held **hard** at `0 . t = distance` -- an
    # equation nothing satisfies. Measured on a unit cube with one degenerate
    # face appended: residual 2.3e-17 clean against 0.01 with it, which is
    # `distance` exactly and stays there however good the rest of the solve is.
    # That is the build's primary readout pinned at a value it cannot fall
    # below, and `offset_residual` is a max, so a real violation anywhere else
    # in the body is then masked by it
    live = np.linalg.norm(normals, axis=1) > PLANE_TOL
    if not live.all():
        faces, normals = faces[live], normals[live]
        if not len(faces):
            return np.zeros((0, 3)), np.zeros(0)
    axis = np.abs(normals).argmax(axis=1)
    aligned = np.abs(normals).max(axis=1) > 1 - tol
    normals = normals.copy()
    normals[aligned] = np.sign(normals[aligned, axis[aligned]])[:, None] * np.eye(3)[axis[aligned]]

    key = np.round(normals / PLANE_TOL)
    distinct, inverse = np.unique(key, axis=0, return_inverse=True)
    distinct = distinct * PLANE_TOL
    if offsets is None:
        return distinct, np.zeros(0)

    inverse = np.asarray(inverse).reshape(-1)
    per_face = np.asarray(offsets)[faces]
    out = np.empty(len(distinct))
    for group in range(len(distinct)):
        want = per_face[inverse == group]
        if want.max() - want.min() > 0.0:
            raise ValueError(
                f"two offsets on one plane at vertex {vertex} "
                f"{np.round(mesh.vertices[vertex], 6).tolist()}: normal "
                f"{np.round(distinct[group], 6).tolist()} is asked for "
                f"{sorted(set(want.tolist()))} m at once. Two cladding systems "
                f"claim the same plane there, and no offset of this vertex "
                f"satisfies both"
            )
        out[group] = want[0]
    return distinct, out


def _vertex_normals(mesh, vertex: int, tol: float, only=None, instead=None) -> np.ndarray:
    """The distinct outward face-plane normals meeting at `vertex`."""
    return _vertex_planes(mesh, vertex, tol, only=only, instead=instead)[0]


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
    # ...and a degenerate face contributes a zero-length normal, which divides to
    # NaN and compares False against the threshold below — an *undetected*
    # contradiction, which is the very failure this comment is about. Dropped
    # instead: a face with no area states no plane.
    length = np.linalg.norm(normals, axis=1)
    normals = normals[length > PLANE_TOL]
    if len(normals) < 2:
        return None
    unit = normals / np.linalg.norm(normals, axis=1)[:, None]
    for i in range(len(normals)):
        for j in range(i + 1, len(normals)):
            if unit[i] @ unit[j] < -1 + PLANE_TOL:
                return normals[i], normals[j]
    return None


def _reconcile(mesh, vertex, tol, normals, moves, covered, offsets=None):
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
        reduced, moves = _vertex_planes(mesh, vertex, tol, offsets, only=covered)
        incident = mesh.vertex_faces[vertex]
        skinned = int(covered[incident[incident >= 0]].sum())
        why = f"{skinned} of its faces are covered by a skin"

    pair = _opposed(reduced)
    if pair is None:
        return reduced, moves

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


def _knife_side(mesh, covered, owner=None):
    """Faces whose plane must be read from the **other** side: the far half of a
    knife the skin covers.

    A knife is two faces on one plane facing opposite ways and touching, so the
    substrate has no thickness there and the two offset surfaces part by twice
    the distance. The skin is on one side of it, and which side is read below off
    what the skin covers, not off any judgement about intent. (`_knifed` answers
    a different question — which faces a *lap* may not land on — and the two
    share only `_knives`.)

    The vertex still **lies on that plane** — what is wrong is only which way it
    is offset. So the far face's normal is *replaced* by its mate's rather than
    dropped. Dropping was tried first and is wrong twice over: it leaves the
    vertex under-constrained, which broke eighteen tests when applied to a whole
    face, and it still misses the vertices where only the far face is incident,
    which is exactly where the defect lived. Substituting keeps every vertex as
    determined as it was and needs no arbitration — the mate's plane is the same
    plane.

    The far half is identified per **body**, not per face, and that is what makes
    it safe: a skin is on the far side of a knife only if it dresses nothing of
    the body that face belongs to. Reading it per face instead says the wrong
    thing whenever a skin covers *both* sides, which is the ordinary case at the
    scupper — the membrane runs over the roof taper and also laps down the
    parapet's inner face, so face-wise it looks like the parapet's side and gets
    pushed 8 mm into the parapet. Measured: 10 crossings into the substrate,
    `clearance 7.8808 → 0.2732 mm`. Per body it does not fire for the membrane at
    all, and the cladding — which dresses no part of the roof — keeps it.

    Returns `{face: normal}` for the far halves only, so a mesh with no knife
    the skin covers returns `{}` and every vertex is read exactly as before.
    """
    if covered is None or owner is None:
        return {}
    ids, reps = _plane_ids(mesh)
    dressed = set(np.asarray(owner)[covered].tolist())
    side = {}
    for face, mates in _knives(mesh, ids, reps).items():
        if covered[face] or int(owner[face]) in dressed:
            continue                    # the skin is on this side of the knife
        facing = [g for g in mates if covered[g]]
        if facing:
            side[int(face)] = mesh.face_normals[facing[0]]
    return side


def _stack(rows: list, width: int) -> tuple[np.ndarray, np.ndarray]:
    if not rows:
        return np.zeros((0, width)), np.zeros(0)
    return np.array([r for r, _ in rows]), np.array([v for _, v in rows])


def planar_offset(mesh: trimesh.Trimesh, distance: float, tol: float = 1e-6, covered=None,
                   owner=None, offsets=None):
    """Offset every face of `mesh` outward by `distance`.

    Solves for all vertex displacements at once. A vertex lies on all of its
    incident face planes, so displacing it by `t` with `n . t == distance` for
    each incident normal `n` puts it on all the offset planes at once. Those
    equations are hard for vertical and horizontal planes, least-squares for the
    sloped rest; horizontal edges add hard equations tying endpoint heights —
    except across an edge whose two ends must rise by different amounts, which
    is a tear rather than an edge and is reported in `metadata["torn"]`.

    `covered` is the face mask the caller is actually building a skin over, and
    is consulted at exactly one kind of vertex: one whose planes contradict each
    other because the surface folds back on itself. See `_reconcile`. Omitting
    it makes every plane required, which is the right default for a plain
    closed-shell offset — there is no selection, so nothing is uncovered.

    `owner` maps each face to the body it came from. It and `covered` are read
    **together** by `_knife_side`, to decide which side of a knife this skin is
    on. Supply both or neither: with either missing that correction does not
    run and a knifed vertex is offset the way it was before the rule existed.
    Omitting both is the right default for the same reason as above — an offset
    of a whole solid is on no far side of anything — but it is a real difference
    in the geometry, so it is said here rather than left to be found. The tests
    that offset a bare solid pass neither.

    `offsets` is a per-face distance overriding `distance`, and is `None` for
    every ordinary offset. It exists for two conditions, both of them a skin
    stopping against something it does not cover. A skin ending against a facade
    the **neighbouring cladding system** dresses: the invariant above says a
    vertex on the edge of a selection sits on the miter it would have had if its
    neighbours were skinned too, and where a neighbour genuinely is skinned, at a
    different allowance, the honest miter is onto *that* plane rather than onto a
    copy of this skin's own. And a skin dying against a **cornice or the cheeks
    of an opening**, where the authored `reveal` is the joint it stops at rather
    than the cavity it stands off the wall by.

    The second of those is why this no longer says *"every face a skin covers
    still moves by one `distance`"*, which was true until 2026-08-27. A reveal
    lining **covers** its cheek and stands `reveal` off it, because a rainscreen
    returning into an opening closes its cavity down to a sheet. That is still
    not per-face freedom in a cladding mesh — the freedom is per **plane**, it is
    derived rather than authored per face, and `metadata["offset_distance"]`
    still reports the skin's own. See `build.skin_offsets` for both rules and for
    why they are applied per plane.
    """
    width = 3 * len(mesh.vertices)
    hard: list = []
    soft: list = []
    folds: list = []

    # At a knife, a vertex takes the **covered side's** plane. Where two bodies
    # meet exactly on one plane with both sides exposed the substrate has no
    # thickness, the two offset surfaces part by twice the distance, and a skin
    # is on one side of it. `_knife_side` reads which side off what the skin
    # dresses; the far face's normal is then *substituted* by its mate's.
    #
    # Substituted, not dropped, and at **every vertex of the far face** rather
    # than only where the two faces touch. Both of those are deliberate and both
    # were arrived at by measuring the alternatives:
    #
    #   * dropping the plane leaves the vertex under-constrained -- 18 tests
    #     broke -- where substituting keeps it exactly as determined as it was,
    #     because it is the same plane and only the direction is in question;
    #   * restricting to the vertices the knifed face shares with its covered
    #     mate is narrow enough to pass, and it fixes nothing that mattered. The
    #     scupper's knife runs down an 8.6 mm sliver: v67 carries both faces and
    #     was already reconciled, while **v66** one edge below carries only the
    #     roof taper's end, shares no vertex with the mate, and is the vertex
    #     that dragged the cladding 85 mm inboard. That is Duncan's "cause 2".
    #
    # The consequence of the wider reach, stated rather than discovered later: a
    # far-half triangle has its plane read from the covered side at all three of
    # its corners, including corners well away from the contact and corners that
    # carry covered faces of their own. That is intended -- the plane belongs to
    # a body this skin dresses no part of, so wherever it constrains a vertex it
    # should be read from the side the skin is on -- but it is a wider rule than
    # "at the knife", and `_knife_side`'s per-body gate is what keeps it safe.
    side = _knife_side(mesh, covered, owner)

    # how far each vertex's own level planes require it to rise, read **after**
    # reconciliation. It is what the level-edge equations below are checked
    # against: a plane `n . t = move` with `|n_z| = 1` fixes `t_z` outright
    rises: list[set] = [set() for _ in range(len(mesh.vertices))]
    # a fold the skin does not reach at all: `_reconcile` read its planes from
    # the covered faces and there were none, so it is not a point of this skin
    adrift: set[int] = set()

    for vertex in range(len(mesh.vertices)):
        normals, moves = _vertex_planes(mesh, vertex, tol, offsets, instead=side)
        if _opposed(normals) is not None:
            normals, moves = _reconcile(
                mesh, vertex, tol, normals, moves, covered, offsets
            )
            folds.append(vertex)
            if not len(normals):
                adrift.add(vertex)
        if offsets is None:
            moves = np.full(len(normals), distance)
        for normal, move in zip(normals, moves):
            row = np.zeros(width)
            row[3 * vertex : 3 * vertex + 3] = normal
            # vertical and horizontal planes are held exactly; only sloped
            # planes absorb error. Testing for axis-alignment instead would
            # demote a vertical wall running at any other plan angle to soft.
            level = abs(normal[2]) < tol or abs(normal[2]) > 1 - tol
            (hard if level else soft).append((row, move))
            if abs(normal[2]) > 1 - tol:
                rises[vertex].add(round(float(np.sign(normal[2]) * move), 12))

    # An edge horizontal in the substrate is held horizontal in the skin —
    # **unless its two ends are required to rise by different amounts**, in
    # which case the skin does not have that edge at all and holding it welds
    # two surfaces that have parted.
    #
    # These equations chain: three vertices on two horizontal edges are tied to
    # one height, which is right, because each edge on its own must stay level.
    # The chain is what makes the test necessary. Where an upward face and a
    # downward face lie on **one level with no thickness between them** the two
    # offset surfaces separate by twice the distance, and a run of horizontal
    # edges leading from one sheet to the other then demands `+distance` and
    # `-distance` of a single connected set of heights. Nothing satisfies that,
    # and a least-squares solve does not say so: it splits the difference and
    # spreads the error over the whole body. Measured on the whole-building bake
    # at z = 6.75, where a lift's exposed top ring meets the lift above it
    # oversailing — 5.15 mm of it on the membrane, 66.5 on the cladding, 96.6 on
    # the masonry, all reported by `offset_residual` and none of it a surface
    # anyone placed.
    #
    # Refusing the equation is refusing a claim that was never true, so nothing
    # else has to move: each end is still held by its own level plane, and it is
    # only the edge between them that is not level any more — which is what a
    # tear is. The test is on the **rise**, not on the fold, and that is what
    # keeps it this narrow: two tops at one level, or two soffits, agree and
    # stay tied however folded the surface around them is. It fires on nothing
    # in the four substrates that solved before it existed, which are
    # bit-identical with it in place.
    #
    # A level face's plane says how far the sheet it belongs to rises, and an
    # edge bounding that face inherits it. That is the same question asked of an
    # edge rather than of its ends, and it is what reaches the case below
    face_rise = np.full(len(mesh.faces), np.nan)
    upright = np.abs(mesh.face_normals[:, 2]) > 1 - tol
    for face in np.flatnonzero(upright):
        move = distance if offsets is None else float(offsets[face])
        face_rise[face] = np.sign(mesh.face_normals[face, 2]) * move

    sharp = mesh.face_adjacency_angles > tol  # ignore diagonals inside a facet
    level = np.abs(
        mesh.vertices[mesh.face_adjacency_edges[sharp][:, 0], 2]
        - mesh.vertices[mesh.face_adjacency_edges[sharp][:, 1], 2]
    ) < tol
    edges = mesh.face_adjacency_edges[sharp][level]
    pairs = mesh.face_adjacency[sharp][level]
    sheet = [
        {r for r in face_rise[pair] if not np.isnan(r)} for pair in pairs
    ]
    # a vertex the skin does not place, with horizontal edges of two different
    # sheets meeting at it, is the two sheets' only join. It is a join the skin
    # does not have — see the rule above; this is the same weld reaching across
    # a point rather than along an edge. All three earlier bakes carry an adrift
    # fold with level edges on it, and every one of those has a single sheet on
    # it — a soffit — so the join is not posed and the edges still tie.
    #
    # Every level edge at such a vertex goes, not only the ones that name a
    # sheet. An edge between two *sloped* faces names none — `face_rise` is nan
    # off a level face — and would otherwise chain the two sheets through the
    # very point this exists to separate. No substrate here poses that edge, but
    # excluding it was an accident of how the sheets are read rather than a
    # decision about what a branch is. Found on review, 2026-08-28
    branch = {
        int(v)
        for v in adrift
        if len({r for edge, rs in zip(edges, sheet) if v in edge for r in rs}) > 1
    }

    torn: list = []
    for (a, b), rs in zip(edges, sheet):
        a, b = int(a), int(b)
        if rises[a] and rises[b] and rises[a].isdisjoint(rises[b]):
            torn.append((a, b))
            continue
        if a in branch or b in branch:
            torn.append((a, b))
            continue
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
    # ...and the horizontal edges it stopped holding horizontal, reported for
    # the same reason and never left to the metadata alone: a constraint the
    # solve dropped must not be silent. See the torn-edge rule above
    out.metadata["torn"] = torn
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
    # cached against a fingerprint of the geometry, not on the mesh alone. The
    # cache rides in `metadata`, and `Trimesh.copy()` copies metadata — so a
    # bare `if "plane_ids" in metadata` hands a moved or edited body the
    # representatives of where it used to be, and plane identity drives lap
    # chaining, knives and the tiling. A run that silently fails to chain is a
    # lap that silently does not happen, which is what this function exists to
    # stop (found on review, 2026-08-25)
    # the faces are in the stamp, not just their count: plane ids derive from
    # `face_normals`, which depend on winding, so an operation that flips or
    # reorders faces without touching the vertex array would otherwise leave the
    # cache looking valid with every id wrong
    stamp = (body.vertices.tobytes(), body.faces.tobytes())
    held = body.metadata.get("plane_ids")
    if held is not None and held[0] == stamp:
        return held[1]
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
    found_planes = ids, np.array(reps) if reps else np.zeros((0, 4))
    body.metadata["plane_ids"] = stamp, found_planes
    return found_planes


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
    # a degenerate triangle in the union -- manifold3d's float32 output can leave
    # one with a repeated corner -- has no vertex outside the arris, and there is
    # then no direction to read. Refused by name rather than by `IndexError`
    # thrown from inside `_lap`, which is how every other refusal here reads
    beyond = [v for v in body.faces[far] if v not in (a, b)]
    if not beyond:
        raise ValueError(
            f"face {far} is degenerate — its corners are {body.faces[far].tolist()}, "
            f"which leaves no vertex off the arris ({a}, {b}) to read a lap "
            f"direction from. The substrate has a repeated vertex in it"
        )
    third = beyond[0]
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


def _lap(body, verts, distance, covered, lappable, onto, skinned_wall, drop, out,
         offsets=None, rounds=3):
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
    there, and there are four answers:

    * *the same plane carries on* -- an in-line butt, where a parapet runs into a
      wall presenting the very same face. The lap runs on, which is the whole of
      the fix for the pinhole at `Parapet-Unit8-N`'s east end where three open
      edges used to converge on one vertex.
    * *another face meets it at an arris* -- the lap folds round the corner onto
      that face. This carries the upstand at that junction onto `Headhouse-N`'s
      north face, and turns the rig's exterior-wall skirt out onto part 4.
    * *the boundary of the face it is lapping onto turns* -- the band turns with
      it and runs on along that boundary, staying on the face it already laps.
      This is the skirt turning down each side of the scupper. It keeps the
      price and the datum of the band it continues rather than being re-priced
      by the direction it now runs in, and it is placed only where the arris
      lies ahead of the skin's own edge along that direction -- where the skin
      already stands proud of the arris that way there is no gap to close. Once
      turned it runs to the **end of the arris**, past the corner where the
      receiving face itself stops: at the scupper the parapet's inner face is
      buried by the roof taper 8.6 mm above the sill, and the band follows the
      covered cheek down to it.
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
    # Every `distance` a lap reasons with is about one **named face** -- the plane
    # a band lands on, or a plane a drip miters onto -- so each reads the per-face
    # offset rather than the skin's own scalar. It stopped being the same number
    # on 2026-08-26, when `build.facade_offsets` began moving a neighbouring
    # system's facade by somebody else's allowance, and again on 2026-08-27, when
    # `build.reveal_faces` began holding a lined cheek at `reveal`: 12 vertices of
    # the live bake carry both a cheek this skin covers at 18 mm and a face it
    # laps onto at 85 mm, and `drip_at` miters across exactly those.
    moves = (
        np.full(len(body.faces), float(distance))
        if offsets is None
        else np.asarray(offsets, dtype=float)
    )
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
            # one row per distinct plane, each asked for **that plane's** offset.
            # Taking the first face of each group is safe rather than arbitrary:
            # two faces of one plane at one vertex carrying different offsets is
            # what `_vertex_planes` raises on, and it has already run over every
            # vertex of this body by the time a lap is placed.
            normals, first = np.unique(
                np.round(body.face_normals[at] / PLANE_TOL), axis=0, return_index=True
            )
            t = np.linalg.lstsq(
                normals * PLANE_TOL, moves[np.asarray(at)][first], rcond=None
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

    def turned(v: int, t, want: float, drip: bool) -> np.ndarray:
        """The outer line of a band that turned, at substrate vertex `v`.

        A turn keeps the band it continues, so it keeps that band's datum: the
        outer line lies `want` past the **substrate** arris for a band measured
        on the substrate, and `want` past the **skin's own edge** for one that
        is not. In every other direction it stays on the skin's own edge, which
        is what keeps the band a strip of the width it already had rather than
        a flap skewed by the offset it turned out of.

        Measuring the gap along `t` is also what strikes out the plane the band
        steps away from. The skin's edge lies `distance` off the covered face
        the band turns off, and that face's normal points along `t` -- so
        offsetting out along it and then stepping back along it are the same
        displacement counted twice. Subtracting the gap cancels exactly that
        component, whatever produced it, and leaves the 30 mm drip 115 mm wide
        at the scupper: 85 across the reveal it laps out of, plus its own 30.
        For a drip the gap is a height and `drip_at` is what miters it, which
        is why this is the turned band's construction and not the drip's.
        """
        gap = float((body.vertices[v] - V[v]) @ t) if drip else 0.0
        return V[v] + (gap + want) * t

    def seg(pa, pb, qa, qb, t, far, want, drip, turn=False, va=None, vb=None):
        return {
            "pa": np.asarray(pa, float), "pb": np.asarray(pb, float),
            "qa": np.asarray(qa, float), "qb": np.asarray(qb, float),
            # the substrate vertices the seam sits on, where it sits on any. An
            # end that has one can be asked what the substrate offers past it;
            # an end that does not -- the far end of a run-on, the rim end of a
            # fold -- is out over the offset and has nothing left to ask
            "va": va, "vb": vb,
            # what this band cost and where it was measured from, carried so a
            # band that turns can keep them rather than be re-priced by the
            # direction it turns in. `want` is what the band was actually placed
            # at, not what its direction is worth, so a band the receiving face
            # shortened turns at the width it really has. `turn` says this band
            # is itself one that turned, which is what may run to the end of the
            # arris it turned onto
            "want": float(want), "drip": bool(drip), "turn": bool(turn),
            "t": t, "far": int(far), "plane": int(ids[far]),
            "out": body.face_normals[far],
        }

    segs = []
    # arrises this skin declined to lap along because the direction they leave in
    # is switched off for it. They are not dead: a band already running into one
    # of them turns and carries on along it, at its own price -- see `carry_on`
    deferred: dict[int, list] = {}
    # arrises where the skin's own surface ends but there is no face to lap onto
    # at all -- the covered face runs on past the corner where the receiving one
    # stops. Kept by vertex rather than by plane, because the face on the far
    # side is by definition not the receiving one and its plane says nothing
    beyond: dict[int, list] = {}
    for (f, g), (a, b) in zip(body.face_adjacency, body.face_adjacency_edges):
        for near, far in ((f, g), (g, f)):
            if not (covered[near] and not covered[far]):
                continue
            a, b, far = int(a), int(b), int(far)
            if not lappable[far]:
                for v in (a, b):
                    beyond.setdefault(v, []).append((a, b))
                continue
            t = _across(body, a, b, far)
            want = reach(t)
            if want == 0.0:
                deferred.setdefault(int(ids[far]), []).append((a, b, t, far))
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
            drip = t[2] < -PLANE_TOL
            root = drip_at if drip else (lambda v: V[v])
            step = t * want
            segs.append(
                seg(V[a], V[b], root(a) + step, root(b) + step, t, far,
                    want=want, drip=drip, va=a, vb=b)
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
        """Run the lap past its tip, fold it round the corner, turn it along the
        face it is on, or leave it.

        The four answers Duncan's rule allows, asked in that order. Each needs
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
            # `rtol=0.0`: numpy's default 1e-5 would make this ~1.1e-5 on unit
            # direction vectors, eleven times the tolerance the call names
            if other is one or not np.allclose(
                other["t"], one["t"], rtol=0.0, atol=PLANE_TOL
            ):
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
            level = planes[far, 3] + moves[far]
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

            def at_arris(end, into=into, facing=facing, stand=stand, off=moves[far]):
                base = end - facing * off
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
            segs.append(seg(side, rim, side + step, rim + step, into, far,
                            want=reach(into), drip=into[2] < -PLANE_TOL, va=tip))
            return True

        # ...and where the boundary of the face it is lapping onto turns at the
        # tip, the band turns with it and runs on along that boundary, staying
        # on the face it already laps. It reaches an arris this skin declined to
        # lap along -- `deferred` -- because the direction that arris leaves in
        # is switched off for it; a band that is already running does not stop
        # there. It keeps its own price and its own datum rather than being
        # re-priced by the direction it now runs in (Duncan, 2026-08-25, having
        # been offered the alternative of authoring the cladding an `out` and
        # refused it: that turns the skirt at the scupper into an upstand set
        # out from the skin's edge, and reverts the drip's rim to a miter he
        # had just approved away).
        #
        # This is the fourth answer at a free end, and it is deliberately last:
        # the substrate carrying on, and the substrate turning a corner, are
        # both answers about where the band **goes**, where this one is about a
        # band that has nowhere to go and follows the face it is on instead.
        for a, b, t, far in deferred.get(one["plane"], ()):
            if tip not in (a, b):
                continue
            w = b if a == tip else a
            seam = {_key(V[tip]), _key(V[w])}
            if any(
                other["plane"] == one["plane"]
                and {_key(other["pa"]), _key(other["pb"])} == seam
                for other in segs
            ):
                continue  # already turned along that arris, from its other end
            # A turn only closes a gap that is open. The band runs from the
            # skin's own edge to `want` past the substrate arris, so it exists
            # only where the arris lies **ahead** of that edge along `t`; where
            # the skin already stands proud of the arris that way, the outer
            # line falls behind the edge it springs from and there is no band.
            # That is what tells the scupper from a wall running into a parapet:
            # at the scupper the covered cheek faces back along the turn and the
            # band spans 115 mm, while at `Headhouse-E`'s foot the covered
            # facade faces along it, the skin is already 85 mm out that way, and
            # the width comes out negative. Both wall ends were placed as bands
            # 30 mm off the substrate by the attempt this replaces.
            #
            # It is a test on the **datum**, so it bites on a band measured on
            # the substrate and only there: one measured from the skin's own
            # edge has no gap to close, its width is `want` whatever the arris
            # does, and this reduces to `want > 0`. Every turn on all three
            # substrates today is a drip -- the cladding's, and the membrane
            # defers nothing to turn onto -- so what a turning upstand ought to
            # be refused at is undecided rather than decided this way. Found by
            # `/code-review high` 2026-08-26, which built the case: a cladding
            # of `drop: 0.0, out: 0.03` turns at `v42` and `v116`, the two
            # vertices this gate exists to refuse, each passing at `+0.03`.
            #
            # Asked at **both** ends: the two ends of one arris need not stand
            # the same distance off it, since each is mitered onto whatever else
            # meets it, and a quad positive at one end and negative at the other
            # is a band turned inside out along its own length.
            ends = [turned(v, t, one["want"], one["drip"]) for v in (tip, w)]
            if min(float((q - V[v]) @ t) for q, v in zip(ends, (tip, w))) < PLANE_TOL:
                continue
            # ...and the lap past the arris still has to land on the receiving
            # face. Asked at the tip alone, which is a **weaker** guard than the
            # one a lap that starts gets, and knowingly so: a turned band
            # follows the boundary of the face it laps onto, so its far end sits
            # on that boundary and `_room` there answers "the face corners here"
            # with the same 0 it would use for "the face runs out here". The
            # code cannot tell those apart, so the far end is not guarded at
            # all, and a receiving face that genuinely stops short at the far
            # end of a turn would take a band hanging over nothing. No substrate
            # here does. Measured at the scupper: the far end reads no room,
            # because the roof falls away under it -- 1.29 mm over the 30 mm
            # lap, which is the case this is written to allow. Raised by
            # `/code-review high` 2026-08-26 and left as a named limit rather
            # than repaired with a threshold.
            if _room(body, body.vertices[tip], t, coplanar[one["plane"]],
                     body.face_normals[far], one["want"]) < one["want"] - PLANE_TOL:
                continue
            segs.append(seg(
                V[tip], V[w], ends[0], ends[1],
                t, far, want=one["want"], drip=one["drip"], turn=True,
                va=tip, vb=w,
            ))
            return True

        # ...and a band that has already turned runs to the end of the arris it
        # turned onto, past the corner where the **receiving** face stops. At
        # the scupper that corner is the knife: the parapet's inner face is
        # buried by the roof taper's end below `z = 14.5036`, so the plane has
        # no face there, while the cheek the band is flashing carries on down to
        # the sill 8.6 mm lower. The band follows the covered face, because it
        # is that face's flashing -- Duncan, 2026-08-26, reading the built bake:
        # *"E84, 86 should be 5 mm lower, even with E70, 71"*, which is the
        # turn-down's bottom edge brought level with the lining's own.
        #
        # Only a band that has itself turned: the three answers above are what a
        # band that has not turned gets, and this one would otherwise reach for
        # an arris at the free end of every drip in the model.
        #
        # `_room` is **not** asked. It cannot be: the receiving face is by
        # definition absent past its own corner, so it would refuse every
        # continuation this exists for. What stands in for it is that the seam
        # must lie on the band's own offset plane at both ends, which is the
        # test the fold already makes -- had `_knife_side` put these vertices on
        # the other side of the knife, they would be 170 mm away and nothing is
        # placed.
        if one["turn"]:
            level = planes[one["far"], 3] + moves[one["far"]]
            facing = body.face_normals[one["far"]]
            for a, b in beyond.get(tip, ()):
                w = b if a == tip else a
                seam = {_key(V[tip]), _key(V[w])}
                if any(
                    other["plane"] == one["plane"]
                    and {_key(other["pa"]), _key(other["pb"])} == seam
                    for other in segs
                ):
                    continue
                run = V[w] - V[tip]
                if np.linalg.norm(run) < WELD_TOL:
                    continue
                # a seam is crossways to the band; an arris running along the
                # lap direction is the band's own outer edge, not its next seam
                if abs(float(run @ one["t"])) > PLANE_TOL:
                    continue
                if max(abs(V[v] @ facing - level) for v in (tip, w)) > PLANE_TOL:
                    continue
                ends = [turned(v, one["t"], one["want"], one["drip"])
                        for v in (tip, w)]
                if min(
                    float((q - V[v]) @ one["t"]) for q, v in zip(ends, (tip, w))
                ) < PLANE_TOL:
                    continue
                segs.append(seg(
                    V[tip], V[w], ends[0], ends[1],
                    one["t"], one["far"], want=one["want"], drip=one["drip"],
                    turn=True, va=tip, vb=w,
                ))
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
        # a seam the solve collapsed to a point has no direction to miter along.
        # Left to the normalisations below it divides by zero, and the NaN goes
        # through `NaN < PLANE_TOL` (False) into `lstsq`, which returns a NaN rim
        # vertex that is written to the mesh without anything raising. A
        # reconciled fold is exactly where vertices are least constrained, so
        # this is reachable in principle; take the tip and place no miter
        if min(np.linalg.norm(u1), np.linalg.norm(u2)) < WELD_TOL:
            return p1
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
    `normal` must be a **unit** vector; the plane is `normal . x == d`. Nothing
    else about it is particular — it need not be level or axis-aligned — but the
    projection and the side test both assume unit length.

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
            # `normal` is a **unit** vector -- see the docstring. This is a
            # projection onto the plane only then; scaled, it over- or
            # undershoots and `past`'s threshold is scaled with it
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
        # those before fanning, or the cut sheds zero-area triangles. The radius
        # is `WELD_TOL`, not `PLANE_TOL`: the latter *is* the 1 µm lattice every
        # substrate coordinate is snapped to, so a crossing landing one lattice
        # cell from a real corner would silently delete that corner from the
        # loop. Same reasoning `skinning/skin/clean.py` spells out for its own weld
        loop = [
            v
            for n, v in enumerate(loop)
            if np.linalg.norm(np.asarray(verts[v]) - verts[loop[n - 1]]) > WELD_TOL
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
    offsets=None,
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

    `offsets(Faces) -> float[nfaces]` is the per-face distance the solve uses in
    place of `distance`, and `None` — the ordinary case — means the whole body
    moves by `distance`. It is a predicate rather than an array for the same
    reason `keep` is: the union is built here, so only something evaluated over
    these `Faces` is indexed the same way. Its one caller says why a skin ever
    wants two: see `build.facade_offsets`.

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

    # evaluated **once**, because the solve and the laps have to reason with the
    # same numbers: a band lands on the offset plane of the face it laps onto,
    # and that plane is where this array put it
    per_face = None if offsets is None else offsets(surface)

    # everything this skin puts a surface on. Only a fold consults it
    skin = planar_offset(
        body,
        distance,
        covered=kept | receivers,
        owner=surface.owner,
        offsets=per_face,
    )

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
            offsets=per_face,
        )

    if base is not None:
        faces = _trim_below(verts, faces, base)

    surface = trimesh.Trimesh(vertices=np.array(verts), faces=faces)
    surface.metadata.update(skin.metadata)
    return surface
