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

from collections import Counter
from functools import cached_property

import numpy as np
import trimesh

from . import substrate

# normals closer than this are treated as the same plane
PLANE_TOL = 1e-6
# keeps the KKT system non-singular where the soft equations underdetermine a vertex
RIDGE = 1e-9


def _vertex_normals(mesh: trimesh.Trimesh, vertex: int, tol: float) -> np.ndarray:
    """Distinct outward face-plane normals meeting at `vertex`.

    Normals within `tol` of an axis are snapped onto it: the union that feeds
    this carries float32 vertices, and an axis-aligned face whose normal is off
    by 1e-7 would otherwise be held to a hard constraint that is itself skew.
    """
    faces = mesh.vertex_faces[vertex]
    normals = mesh.face_normals[faces[faces >= 0]]
    axis = np.abs(normals).argmax(axis=1)
    aligned = np.abs(normals).max(axis=1) > 1 - tol
    normals = normals.copy()
    normals[aligned] = np.sign(normals[aligned, axis[aligned]])[:, None] * np.eye(3)[axis[aligned]]
    return np.unique(np.round(normals / PLANE_TOL), axis=0) * PLANE_TOL


def _stack(rows: list, width: int) -> tuple[np.ndarray, np.ndarray]:
    if not rows:
        return np.zeros((0, width)), np.zeros(0)
    return np.array([r for r, _ in rows]), np.array([v for _, v in rows])


def planar_offset(mesh: trimesh.Trimesh, distance: float, tol: float = 1e-6):
    """Offset every face of `mesh` outward by `distance`.

    Solves for all vertex displacements at once. A vertex lies on all of its
    incident face planes, so displacing it by `t` with `n . t == distance` for
    each incident normal `n` puts it on all the offset planes at once. Those
    equations are hard for vertical and horizontal planes, least-squares for the
    sloped rest; horizontal edges add hard equations tying endpoint heights.
    """
    width = 3 * len(mesh.vertices)
    hard: list = []
    soft: list = []

    for vertex in range(len(mesh.vertices)):
        for normal in _vertex_normals(mesh, vertex, tol):
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
    return out


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
            bodies = [self.parts[i] for i in members]
            by_element.append(
                self.classify(bodies[0] if len(bodies) == 1 else substrate.union(bodies))
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
        groups: dict = {}
        for index, part in enumerate(self.parts):
            name = part.metadata.get("object")
            groups.setdefault(("object", name) if name else ("part", index), []).append(index)
        return list(groups.values())

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


def _hem(body, skin, verts, distance, height, wall, skinned_wall, against, project=0.0):
    """Quads standing `height` metres off the edge each `wall` face shares with a
    covered face in `against`.

    Negative `height` hangs a skirt below the wall's top edge; positive climbs an
    upstand above the edge where the covered surface runs into the wall. Either
    way the shared edge is the one the surface already ends on, so the hem
    continues it without a seam, and the far corners are mitered across every
    skinned vertical plane at that vertex — mitering across the turn-down walls
    alone would split the corner open where two walls meet.

    """
    hem: dict[int, int] = {}

    def hem_vertex(v: int) -> int:
        if v not in hem:
            faces = body.vertex_faces[v]
            faces = [f for f in faces[faces >= 0] if skinned_wall[f]]
            normals = np.unique(np.round(body.face_normals[faces] / PLANE_TOL), axis=0)
            t = np.linalg.lstsq(normals * PLANE_TOL, np.full(len(normals), distance), rcond=None)[0]
            hem[v] = len(verts)
            verts.append(body.vertices[v] + t + [0.0, 0.0, height])
        return hem[v]

    def quad(loop, outward):
        corners = np.array([verts[i] for i in loop])
        newell = np.cross(corners, np.roll(corners, -1, axis=0)).sum(axis=0)
        if newell @ outward < 0:
            loop = loop[::-1]
        return [[loop[0], loop[1], loop[2]], [loop[0], loop[2], loop[3]]]

    faces = []
    for (f, g), (a, b) in zip(body.face_adjacency, body.face_adjacency_edges):
        for near, far in ((f, g), (g, f)):
            if wall[near] and against[far]:
                faces += quad(
                    [a, b, hem_vertex(b), hem_vertex(a)], body.face_normals[near]
                )
    return faces


def _turn_out(body, verts, faces, wall, distance, out):
    """Turn every panel that stops on a `wall` plane out along the axis it faces.

    Where the surface runs into the wall it ends on a boundary edge. Each such
    edge is extruded by `out` along the dominant axis of its own panel's normal,
    so the whole termination folds outward together: the roof panels turn up, the
    panel facing -X turns -X, the skirt facing +X turns +X. Turning only the
    horizontal ones would leave the vertical panels stopping dead at the wall.

    Snapping to the dominant axis rather than using the normal verbatim keeps a
    turn off a shallow slope exactly vertical — the same priority the solver gives
    level planes. The new panel carries the old one's outward face around the
    fold, so it is wound to face the way the boundary edge did.

    Those edges form a chain around the wall, and neighbouring panels turn along
    different axes, so their outer edges are mitered where they meet rather than
    each being extruded on its own. The miter is the intersection of the two outer
    lines, which extends a pair that would otherwise leave a gap and trims a pair
    that would otherwise overlap — the same treatment `planar_offset` gives a
    corner, in the wall's plane instead of in space.
    """
    if not out or not wall.any():
        return []

    corner = body.vertices[body.faces[wall][:, 0]]
    planes = np.unique(
        np.round(
            np.column_stack(
                [
                    body.face_normals[wall],
                    (corner * body.face_normals[wall]).sum(axis=1) + distance,
                ]
            )
            / PLANE_TOL
        ),
        axis=0,
    ) * PLANE_TOL

    V = np.asarray(verts, dtype=float)
    seen: Counter = Counter()
    holder: dict[tuple, list] = {}
    for tri in faces:
        for e in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (min(e), max(e))
            seen[key] += 1
            holder[key] = tri

    def stops_on_wall(i, j):
        return any(
            abs(V[i] @ n - d) < PLANE_TOL and abs(V[j] @ n - d) < PLANE_TOL
            for n, d in zip(planes[:, :3], planes[:, 3])
        )

    segs = []
    for (i, j), count in seen.items():
        if count != 1 or not stops_on_wall(i, j):
            continue
        tri = holder[(i, j)]
        p, q, r = (V[tri[0]], V[tri[1]], V[tri[2]])
        normal = np.cross(q - p, r - p)
        normal /= np.linalg.norm(normal)

        axis = int(np.abs(normal).argmax())
        step = np.zeros(3)
        step[axis] = np.sign(normal[axis]) * out

        # the way the panel faces at this edge: in its own plane, away from the
        # third corner. The turn carries that face around, so it sets the winding.
        third = V[[v for v in tri if v not in (i, j)][0]]
        run = V[j] - V[i]
        away = (V[i] + V[j]) / 2.0 - third
        away -= (away @ run) / (run @ run) * run
        away /= np.linalg.norm(away)
        segs.append([i, j, step, away])

    if not segs:
        return []

    touching: dict[int, list] = {}
    for k, (i, j, _, _) in enumerate(segs):
        touching.setdefault(i, []).append(k)
        touching.setdefault(j, []).append(k)

    def walk(start):
        chain, cur = [], start
        while True:
            nxt = [k for k in touching[cur] if k not in taken]
            if not nxt:
                return chain
            k = nxt[0]
            taken.add(k)
            i, j = segs[k][:2]
            a, b = (i, j) if i == cur else (j, i)
            chain.append((k, a, b))
            cur = b

    taken: set = set()
    chains = [walk(v) for v, ks in touching.items() if len(ks) == 1]
    chains += [walk(segs[k][0]) for k in range(len(segs)) if k not in taken]

    def corner(k1, k2, v):
        """Where the two outer lines meet, or the plain offset if they are parallel."""
        (a1, b1, d1, _), (a2, b2, d2, _) = segs[k1], segs[k2]
        u1, u2 = V[b1] - V[a1], V[b2] - V[a2]
        if np.linalg.norm(np.cross(u1, u2)) < PLANE_TOL:
            return V[v] + d1  # same panel continuing; nothing to miter
        p1, p2 = V[v] + d1, V[v] + d2
        t = np.linalg.lstsq(np.column_stack([u1, -u2]), p2 - p1, rcond=None)[0][0]
        return p1 + t * u1

    def vertex(point):
        verts.append(point)
        return len(verts) - 1

    new = []
    for chain in chains:
        if not chain:
            continue
        outer = [vertex(V[chain[0][1]] + segs[chain[0][0]][2])]
        for (k1, _, b1), (k2, _, _) in zip(chain, chain[1:]):
            outer.append(vertex(corner(k1, k2, b1)))
        outer.append(vertex(V[chain[-1][2]] + segs[chain[-1][0]][2]))

        for n, (k, a, b) in enumerate(chain):
            loop = [a, b, outer[n + 1], outer[n]]
            pts = np.array([verts[v] for v in loop])
            if np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0) @ segs[k][3] < 0:
                loop = loop[::-1]
            new += [[loop[0], loop[1], loop[2]], [loop[0], loop[2], loop[3]]]
    return new


def _trim_below(verts, faces, base):
    """Cut the surface at the horizontal plane z = `base`, keeping what is above.

    A skin ending against an *unskinned* neighbour sits on the miter it would
    have had if that neighbour were skinned too, so cladding whose facades miter
    with the substrate's unskinned underside runs `distance` below the base
    plane. That is correct as offset geometry and wrong as building: cladding
    stops at the ground. `base` is the datum it stops at.

    A cut, not a projection or a clamp. Both of those would move vertices off
    their offset planes — a clamp flattens the bottom of a sloped panel onto the
    datum and quietly breaks the exactness the solve just bought. Re-cutting the
    straddling triangles instead leaves every remaining plane where it was and
    adds an edge lying exactly on z = `base`.

    Crossings are cached per substrate edge so the two triangles sharing one get
    the same vertex, not two that agree to within a rounding: the seam between
    them would otherwise crack open.

    Which side a vertex is on is decided against `base` **exactly**, with no
    tolerance band. A band is the obvious thing to reach for and is wrong here:
    `crossing` interpolates to exactly `z == base`, so a vertex inside the band
    but below the plane would be called "above" while the interpolation, solving
    for a plane it is already past, runs the parameter negative and puts the cut
    vertex *outside* the edge it was cutting. A near-horizontal panel a fraction
    of a micron under the datum came out 333 mm wide that way. The tolerance
    belongs on the positions instead, where the duplicate drop below applies it.
    """
    cuts: dict[tuple[int, int], int] = {}

    def crossing(i: int, j: int) -> int:
        key = (i, j) if i < j else (j, i)
        if key not in cuts:
            p, q = np.asarray(verts[key[0]]), np.asarray(verts[key[1]])
            point = p + (base - p[2]) / (q[2] - p[2]) * (q - p)
            point[2] = base  # exactly on the datum, not a rounding away from it
            cuts[key] = len(verts)
            verts.append(point)
        return cuts[key]

    kept = []
    for face in faces:
        above = [verts[i][2] >= base for i in face]
        if all(above):
            kept.append(face)
            continue
        if not any(above):
            continue

        loop: list[int] = []
        for n, i in enumerate(face):
            j = face[(n + 1) % len(face)]
            if above[n]:
                loop.append(i)
            if above[n] != above[(n + 1) % len(face)]:
                loop.append(crossing(i, j))

        # a corner sitting on the datum makes its own crossing a duplicate; drop
        # those before fanning, or the cut sheds zero-area triangles
        loop = [
            v
            for n, v in enumerate(loop)
            if np.linalg.norm(np.asarray(verts[v]) - verts[loop[n - 1]]) > PLANE_TOL
        ]
        # a triangle cut by a plane is convex, so a fan from any corner is safe
        kept += [[loop[0], loop[n], loop[n + 1]] for n in range(1, len(loop) - 1)]

    if not kept:
        raise ValueError(
            f"trimming at base={base} leaves nothing: every face of this skin is "
            f"below it. `base` is a height in the model, not a depth below the "
            f"skin — check the datum authored in skins.<name>.base"
        )
    return kept


def skin_over(
    parts: list[trimesh.Trimesh],
    distance: float,
    keep=None,
    turn_down=None,
    drop: float = 0.0,
    turn_out=None,
    out: float = 0.0,
    base: float | None = None,
    classify=None,
) -> trimesh.Trimesh:
    """Offset an assembly of parts as a single body.

    The parts are unioned only to find the outer surface — faces where parts
    touch are interior to that union, so no skin is generated between them. The
    union is a local intermediate and is discarded; `parts` is left untouched
    and stays the substrate geometry.

    `keep(Faces)` optionally selects a subset of the union's
    faces, returning an open surface rather than a closed shell. The offset is
    still solved over the whole body first, so vertices on the edge of the
    selection sit on the same miter they would have if the neighbouring faces
    were skinned too — the surface stops there rather than being offset in
    isolation.

    `turn_down` selects walls the surface should hang down, `drop` metres below
    the substrate's top edge, continuing the surface past where `keep` ends it.
    `turn_out` selects walls the surface stops against rather than covers. Every
    panel that ends on such a wall is turned `out` metres along the axis it faces,
    so the termination folds outward as one piece instead of ending on a bare edge.

    `base` cuts the finished surface at that height and keeps what is above it,
    for a skin that stops at a datum rather than at its own miter — the cladding
    at ground level. `None` is no trim, and is not the same as `0.0`: a height of
    zero is a height, where a `drop` or an `out` of zero is a feature switched
    off. It is applied last, after the hems and the turn-outs, so it means "no
    part of this skin goes below `base`" rather than "the offset stops there".

    `classify(part) -> role` is handed to `Faces` for the predicates to read. It
    is the caller's, thresholds already bound, because those thresholds are
    authored parameters — see `Faces.roles`. Only predicates that ask about roles
    need it, so a plain closed-shell offset can leave it out.
    """
    body = substrate.union(parts)   # about the origin; see substrate.union
    skin = planar_offset(body, distance)
    if keep is None:
        return skin

    surface = Faces(body, parts, _owner(body, parts), classify)
    kept = keep(surface)

    verts = list(skin.vertices)
    faces = [f.tolist() for f in skin.faces[kept]]

    none = np.zeros(len(kept), dtype=bool)
    stop = none if turn_out is None else turn_out(surface)

    if turn_down is not None:
        height = np.abs(body.face_normals[:, 2])
        down = turn_down(surface)
        faces += _hem(
            body,
            skin,
            verts,
            distance,
            -drop,
            down,
            # every skinned vertical plane miters the hem, walls it stops on included
            skinned_wall=(kept | down | stop) & (height < PLANE_TOL),
            against=kept & (height > PLANE_TOL),
        )

    # last, so that hems terminating on the wall turn out along with the panels
    faces += _turn_out(body, verts, faces, stop, distance, out)

    if base is not None:
        faces = _trim_below(verts, faces, base)

    surface = trimesh.Trimesh(vertices=np.array(verts), faces=faces)
    surface.metadata.update(skin.metadata)
    return surface
