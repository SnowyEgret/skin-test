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

    out = trimesh.Trimesh(
        vertices=mesh.vertices + t.reshape(-1, 3), faces=mesh.faces.copy(), process=False
    )
    out.metadata["offset_distance"] = distance
    out.metadata["offset_residual"] = float(np.abs(H @ t - h).max()) if H.size else 0.0
    out.metadata["slope_deviation"] = float(np.abs(S @ t - s).max()) if S.size else 0.0
    return out


class Faces:
    """What a face predicate may ask about the unioned substrate.

    Predicates used to take `(normals, centres, owner)`, which is enough to test
    a face against a named plane but not enough to ask what a face *adjoins* or
    what part it belongs to. Rules that read the substrate rather than quoting
    coordinates need both, so they get the whole thing.
    """

    def __init__(self, body, parts, owner):
        self.body = body
        self.parts = parts
        self.owner = owner
        self.normals = body.face_normals
        self.centres = body.triangles.mean(axis=1)

    @cached_property
    def roles(self) -> list:
        """WALL or ROOF per part, from geometry. Raises on a part it cannot read."""
        return [substrate.classify(p) for p in self.parts]

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


def skin_over(
    parts: list[trimesh.Trimesh],
    distance: float,
    keep=None,
    turn_down=None,
    drop: float = 0.0,
    turn_out=None,
    out: float = 0.0,
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
    """
    body = parts[0] if len(parts) == 1 else trimesh.boolean.union(parts)
    skin = planar_offset(body, distance)
    if keep is None:
        return skin

    surface = Faces(body, parts, _owner(body, parts))
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

    surface = trimesh.Trimesh(vertices=np.array(verts), faces=faces)
    surface.metadata.update(skin.metadata)
    return surface
