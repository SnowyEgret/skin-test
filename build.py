#!/usr/bin/env python3
"""Build the geometry headless into build/. Blender only ever loads the result."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import numpy as np
import trimesh

from skin import clearance, parameters, separation, skin_over, substrate, write_obj
from skin.offset import Faces, _owner, elements_of

BUILD_DIR = Path(__file__).parent / "build"

# manifold3d carries vertices as float32, so a union's faces sit up to ~5e-7 m
# off their true planes at metre-scale coordinates. Clearance is judged against
# that floor, not against exact arithmetic.
TOL = 1e-6  # 1 um, same grid substrate.prism() snaps to


# Transcribed from the Blender scene, snapped to 1 um. Both parts have sloped
# tops: high edges at z = 2.053892, low edges at z = 1.953892, both horizontal.
# Part 1 carries the hip — its corner face is coplanar with part 2's top.
PART_1 = (
    [(-3.069769, -3.029931, 0.0), (-3.069769, -3.029931, 1.953892),
     (-3.069769, -1.897401, 0.0), (-3.069769, -1.897401, 2.053892),
     (1.573496, -3.029931, 0.0), (1.573496, -3.029931, 2.053892),
     (1.573496, -1.897401, 0.0), (1.573496, -1.897401, 2.053892),
     (0.740966, -3.029931, 1.953892)],
    [[0, 1, 3, 2], [4, 5, 8, 1, 0], [0, 2, 6, 4], [5, 7, 8],
     [2, 3, 7, 6], [6, 7, 5, 4], [7, 3, 1, 8]],
)
PART_2 = (
    [(0.740966, -7.673195, 0.0), (0.740966, -7.673195, 1.953892),
     (0.740966, -3.029931, 0.0), (0.740966, -3.029931, 1.953892),
     (1.573496, -7.673195, 0.0), (1.573496, -7.673195, 2.053892),
     (1.573496, -3.029931, 0.0), (1.573496, -3.029931, 2.053892)],
    [[0, 1, 3, 2], [4, 5, 1, 0], [0, 2, 6, 4], [5, 7, 3, 1],
     [2, 3, 7, 6], [6, 7, 5, 4]],
)


# Part 3 fills the L's inner quadrant, so the plan becomes a full rectangle. Its
# top is NOT one plane: three corners at z = 1.456084, one at 1.156084, i.e. 300 mm
# out of plane, so it is two triangles meeting on a sloping diagonal. It also sits
# lower than parts 1 and 2, which leaves vertical step faces standing above it.
PART_3 = (
    [(-3.069769, -3.029931, 1.456084), (0.740966, -3.029931, 1.456084),
     (-3.069769, -3.029931, 0.0), (0.740966, -3.029931, 0.0),
     (0.740966, -7.673195, 1.456084), (-3.069769, -7.673195, 0.0),
     (0.740966, -7.673195, 0.0), (-3.069769, -7.673195, 1.156084)],
    [[0, 1, 3, 2], [2, 3, 6, 5], [5, 6, 4, 7], [7, 4, 1],
     [2, 5, 7, 0], [6, 3, 1, 4], [0, 7, 1]],
)


# Part 4 is a tall wall standing along the whole -Y edge, on the far side of it:
# it abuts parts 2 and 3 on the plane y = -7.673195 and overhangs +X past part 2.
# Its top slopes away from the substrate, 4.105916 at the inner edge down to
# 4.045916 at the outer; both those edges are horizontal.
#
# Transcribed from the object named "Cube", which carries a ~4.4e-8 rotation
# skew. That splits what should be one +X coordinate across a 1 um boundary
# (2.321661711 vs 2.321661472), so the value is taken from the local coordinate
# the skew perturbs, not from rounding the two world values independently.
PART_4 = (
    [(-3.069769, -7.673195, 4.105916), (2.321661, -7.673195, 4.105916),
     (-3.069769, -7.673195, 0.0), (2.321661, -7.673195, 0.0),
     (-3.069769, -8.154625, 4.045916), (2.321661, -8.154625, 4.045916),
     (-3.069769, -8.154625, 0.0), (2.321661, -8.154625, 0.0)],
    [[0, 1, 3, 2], [2, 3, 7, 6], [6, 7, 5, 4], [4, 5, 1, 0],
     [2, 6, 4, 0], [7, 3, 1, 5]],
)


# Every number this module used to hold is now authored in `skin-parameters.yaml`
# and validated against `skin-parameters.schema.json` — the five skin distances,
# `fall`, and `classify`'s two thresholds. See `skin/parameters.py` for why, and
# for how the block migrates into `student-house-parameters.yaml` under `skin:`.
#
# What stays here are the RULES, which are code and not numbers: predicates over
# the union's faces. `skins()` joins the two by name.


# Which cladding system a wall's facade takes. Not derivable — no property of a
# wall's shape implies brick — so it rides on the part as metadata and the reader
# stamps it. Here that reader is the transcription below; in the student-house it
# is one read of the IFC material. A facade in a plane a rule could have picked
# out ("the frontmost -X one") would still be the wrong thing to key on: the
# headhouse has a second -X facade that is not brick, and a facade's material is
# a design decision, not a fact about where it sits.
FACADE = "facade"
CORNICE = "cornice"  # stamped by group_cornices; the cladding stops below one
RAINSCREEN = "rainscreen"
BRICK = "brick"

CLADDING_SYSTEMS = (RAINSCREEN,)  # every system that claims facades; see check_facades


def current_substrate() -> list:
    """Four sloped-top parts; stepped in height, with a tall wall on the -Y edge.

    Every facade here is rainscreen — the sample has no street front, and indeed
    no -X-facing facade at all, so it cannot pose the brick condition. The stamp
    is applied anyway so the path that reads it is the one that runs.
    """
    parts = [substrate.polyhedron(*p) for p in (PART_1, PART_2, PART_3, PART_4)]
    for part in parts:
        part.metadata[FACADE] = RAINSCREEN
    return parts


def _upward(normals):
    """Faces that face up at all: the tops of walls, and roof surfaces.

    The test is the sign of n_z, not `abs(n_z)`. Testing the magnitude asks
    "is this face off-axis", which is a different question and wrong twice over:
    a sloped soffit reads as a top, and a flat top is missed altogether. Neither
    can happen in this substrate — every top here is sloped and every underside
    is exactly horizontal — so only `tests/test_offset.py` exercises it. In the
    student-house substrate both occur: a wall panel with a flat top is normal
    (another panel stacks on it), and sloped undersides exist.
    """
    return normals[:, 2] > TOL


def uphill(element) -> np.ndarray:
    """The unit horizontal direction an element's top rises in.

    A plane of normal `n` carries z uphill along `-(n_x, n_y)`, so the top names
    its own fall. Area-weighted over the upward faces, because a wall carrying a
    hip has more than one top and the large one should govern.

    Takes the **element** — every body of one wall — not a single part. A baked
    wall arrives as an inner leaf, an outer leaf and a cap plate; the leaves are
    flat-topped boxes and only the cap is sloped, so a per-body reading raises on
    two thirds of a wall that plainly has a high side. Summing over the element
    puts the cap's slope where it belongs, on the wall it caps.

    That works without merging anything and without hunting for "the cap above":
    a flat face contributes `(0, 0)` to the sum, so the leaf tops dilute the
    magnitude and never the direction. Measured on the headhouse parapets, each
    carrying 1.8–2.4 m² of hidden flat leaf top, every element still resolves to
    a clean outboard direction. It is also indifferent to whether the leaves are
    split at all: merge them upstream and each element becomes one part with a
    sloped top, and the same sum gives the same answer.
    """
    fall, seen = np.zeros(2), False
    for part in element:
        up = part.face_normals[:, 2] > TOL
        if not up.any():
            continue
        seen = True
        fall += (part.face_normals[up][:, :2] * part.area_faces[up][:, None]).sum(axis=0)
    if not seen:
        raise ValueError("element has no upward face, so it has no high side")
    length = float(np.linalg.norm(fall))
    if length < TOL:
        raise ValueError(
            "flat top: no high side, so exterior and interior are undefined. A "
            "stacked wall panel must take its direction from the parapet above it."
        )
    return -fall / length


def _wall_planes(bodies) -> np.ndarray:
    """`(n_x, n_y, n_z, d)` per vertical face of these bodies, duplicates dropped."""
    rows = []
    for part in bodies:
        upright = np.abs(part.face_normals[:, 2]) < TOL
        normals = part.face_normals[upright]
        offsets = (normals * part.triangles.mean(axis=1)[upright]).sum(axis=1)
        rows.append(np.column_stack([normals, offsets]))
    if not rows:
        return np.zeros((0, 4))
    return np.unique(np.round(np.vstack(rows) / TOL) * TOL, axis=0)


def _next_lift(parts, elements, members) -> list:
    """The elements resting on this one that continue it as its next lift.

    What a flat-topped panel has to ask, to find the parapet that names its
    sides. Three conditions, and it takes all three.

    - It **rests on** this element: its underside sits at this element's top,
      and the two overlap in plan.
    - It is **flush on both sides**: this element has a pair of opposed vertical
      planes — the two faces across its thickness — and the element above lies
      in both. That is what "the next lift of this wall" means, and it is the
      condition that does the work here.
    - Consequently it is not a roof: `Roof_Headhouse_CLT` bears on all four
      headhouse walls at z = 14.025 and would otherwise hand each of them the
      taper's fall, which says nothing about which side of a wall is outside.
      Its edges are set in from every wall face, so it is flush with none.

    Both sides, not one, because the caps of this substrate overlap at the
    corners rather than mitring: `CapPlate-Headhouse-W` runs over the end of
    `Parapet-Headhouse-S` and is flush with its y = 7.54 face — the building's
    outer plane, which every element at that corner shares. It is not flush with
    y = 7.12, so it is not another lift of that parapet, and requiring the pair
    says so exactly. Weighting the strays down by area instead would leave the
    answer tilted by a few degrees and dependent on how long the walls are.

    Plane-matching rather than bounds: an axis-aligned box around a wall running
    diagonally in plan says nothing useful, which is the same reason
    `substrate.classify` refuses to read one. The plan overlap below is a bounds
    test, but only as a necessary condition on two elements already known to be
    flush and in contact — it separates the lift above from a distant one in the
    same plane, and nothing turns on where its box came from.
    """
    bodies = [parts[i] for i in members]
    top = max(part.bounds[1][2] for part in bodies)
    mine = _wall_planes(bodies)
    # this element's thickness, however it runs in plan. Held as index pairs
    # into `mine` rather than as the rows themselves: matching a row back by its
    # value would turn on the rounding in `_wall_planes` having landed two
    # coplanar faces of a diagonal wall on the same lattice point, and that is
    # not something to rely on
    opposed = [
        (i, j)
        for i in range(len(mine))
        for j in range(i + 1, len(mine))
        # antiparallel, and looking away from each other rather than toward:
        # the two faces across a thickness, not the two cheeks of a notch
        if abs(mine[i, :3] @ mine[j, :3] + 1) < TOL and mine[i, 3] > -mine[j, 3]
    ]
    if not opposed:
        return []
    plan = np.array([[part.bounds[j][:2] for part in bodies] for j in (0, 1)])
    box = (plan[0].min(axis=0), plan[1].max(axis=0))

    lifts = []
    for other in elements:
        if other[0] in members:
            continue
        above = [parts[i] for i in other]
        if abs(min(part.bounds[0][2] for part in above) - top) > TOL:
            continue
        theirs = np.array([[part.bounds[j][:2] for part in above] for j in (0, 1)])
        if (theirs[1].max(axis=0) <= box[0] + TOL).any():
            continue
        if (theirs[0].min(axis=0) >= box[1] - TOL).any():
            continue
        planes = _wall_planes(above)
        if not len(planes):
            continue
        flush = np.abs(planes[:, None, :] - mine[None, :, :]).max(axis=2) < TOL
        held = flush.any(axis=0)
        if any(held[i] and held[j] for i, j in opposed):
            lifts.append(other)
    return lifts


def _projection_axis(a, b):
    """The plan axis `a` stands clear of `b` on, or None if their footprints overlap.

    Touching is allowed — a cornice is flush against the face it hangs on — so
    the test is on shared *area*, not on shared boundary.
    """
    for k in (0, 1):
        if a[1][k] <= b[0][k] + TOL or a[0][k] >= b[1][k] - TOL:
            return k
    return None


def _in_contact(a, b) -> bool:
    """True where two bounding boxes meet or overlap on all three axes."""
    return all(a[1][k] >= b[0][k] - TOL and a[0][k] <= b[1][k] + TOL for k in range(3))


def group_cornices(parts: list) -> list:
    """Join each cornice to the wall it projects from, so the two are one element.

    A cornice is a band standing proud of a wall's exterior face — a course under
    a coping, or the drip that throws a scupper's outflow clear of the facade. On
    its own it classifies as nothing useful: `Cornice-Unit8-E` reads `ROOF` at
    horizontality 0.704, and the 400 mm scupper drip reads 0.533, dead on the
    halfway mark, where `substrate.classify` refuses outright and the build
    stops. Neither is a roof. Both are the wall they hang on.

    This runs **before** `group_caps`, which classifies every element up front
    and would raise on the cornice before any grouping could help. It therefore
    cannot ask what a part's role is — and does not need to, because the relation
    is local geometry:

    **a body is a cornice of one it touches when it sits within that body's
    height, is strictly shorter than it, and lies wholly outside its plan
    footprint.**

    Each condition earns its place, and the second and third are what keep it
    from running away:

    - *within its height* separates a cornice from a cap plate, which rests on
      the top and shares only that plane. `_next_lift` claims the cap, and this
      must not claim it as well.
    - *strictly shorter* separates it from the neighbouring wall it also touches
      and also lies outside of. `Parapet-Unit8-N` butts `Parapet-Unit8-E` at the
      corner, runs the same 727 mm, and is nobody's cornice.
    - *wholly outside in plan* is what "projects from the face" means, as opposed
      to sitting in the wall or on it.
    - *projects less far than the wall is thick* is what stops the relation
      running away along the building. `Parapet-Unit8-W` meets `Headhouse-S`'s
      outer face, sits inside its height and is shorter than it, and on the first
      three conditions alone became its cornice — it stands 3.34 m proud of a
      420 mm wall. A cornice is a modest band by definition, so the wall's own
      thickness is the measure, and nothing has to be authored: the same move
      `_next_lift` makes when it asks about faces "across this element's
      thickness".

    Where several bodies qualify the tallest wins, since a cornice hangs on the
    wall rather than on whatever else happens to touch it.

    The bodies are stamped `metadata[CORNICE]` as well as regrouped, because the
    two skins want different things and only one of them can be had by grouping.
    The membrane needs nothing further: a cornice joined to a climbed parapet has
    its exposed top picked up by "every upward face of a climbed wall" and its
    face skirted by "down the exterior face of every wall carried over", which is
    exactly the scupper drip Duncan asked for — covered, with the skirt turned
    down it. At `Cornice-Unit8-E` the same rules do nothing, because its top is
    buried under the cap plate and its face is coplanar with the cap's, so the
    membrane there is unchanged. The cladding is the one that has to ask: it
    **stops below** a cornice rather than wrapping it. See `cladding_faces`.
    """
    hosts = {}
    for index, part in enumerate(parts):
        mine = part.bounds
        for other, host in enumerate(parts):
            if other == index:
                continue
            theirs = host.bounds
            if not _in_contact(mine, theirs):
                continue
            if mine[0][2] < theirs[0][2] - TOL or mine[1][2] > theirs[1][2] + TOL:
                continue  # not within its height: a lift above it, not a band on it
            if mine[1][2] - mine[0][2] >= theirs[1][2] - theirs[0][2] - TOL:
                continue  # not shorter: a neighbour of the same stature
            axis = _projection_axis(mine, theirs)
            if axis is None:
                continue  # not projecting: it sits in the wall, not proud of it
            if mine[1][axis] - mine[0][axis] >= min(
                theirs[1][k] - theirs[0][k] for k in (0, 1)
            ):
                continue  # projects further than the wall is thick: a wing, not a band
            taller = theirs[1][2] - theirs[0][2]
            if index not in hosts or taller > hosts[index][1]:
                hosts[index] = (other, taller)

    for index, (host, _) in hosts.items():
        owner = parts[host].metadata.get("object")
        if owner is None:
            continue  # ungrouped parts stand alone; there is no element to join
        parts[index].metadata["object"] = owner
        parts[index].metadata[CORNICE] = True
    return parts


def group_caps(parts: list, classify) -> list:
    """Join each cap plate to the wall it caps, so the two are one element.

    A parapet's coping is a 29 mm plate. On its own it is unmistakably a slab
    and `substrate.classify` calls it `ROOF` — but it is not a roof, it is the
    top of a wall, and the whole of `Faces.roles` exists on that observation.
    Where the bake keeps the plate inside its parapet's object the grouping is
    already right and this changes nothing. Where the plate is its **own**
    object, as in `headhouse-walls-parapets-caps-clt-insulation.obj`, it becomes
    its own element, reads `ROOF`, and the consequences run right through:
    `cladding_faces`' "every wall top" stops reaching any coping, the membrane
    covers the plate as if it were roof, and the parapet head comes out with the
    membrane *over* the metal rather than under it.

    The rule is derived, not a name match on `CapPlate-`: **a lift that
    classifies `ROOF` while the element it rests on classifies `WALL` is that
    wall's cap.** `_next_lift` already computes "rests on and continues", which
    is the same relation `rise` walks, so nothing new is measured here.

    It groups the cap and **not** the parapet below it, which is the whole point
    of testing the lift's own classification: a parapet reads `WALL` on its own
    and stays a separate element. Merging the entire stack into one element
    would read `WALL` too, and would be wrong for a different reason — the
    climb-or-flange election is per wall, so a wall merged with its parapet
    would have the membrane climb its full height instead of stopping at the
    parapet the roof actually runs into.

    Mutates `metadata["object"]`, because that is what `elements_of` groups on
    and the alternative is a second grouping channel saying the same thing.
    """
    elements = elements_of(parts)
    roles = {}
    for members in elements:
        roles[members[0]] = substrate.role_of(classify, [parts[i] for i in members])

    for members in elements:
        if roles[members[0]] != substrate.WALL:
            continue
        owner = parts[members[0]].metadata.get("object")
        if owner is None:
            continue  # ungrouped parts stand alone; there is no element to join
        for lift in _next_lift(parts, elements, members):
            if roles[lift[0]] != substrate.ROOF:
                continue
            for index in lift:
                parts[index].metadata["object"] = owner
    return parts


def rise(faces, members, seen=None) -> np.ndarray:
    """The direction an element's top rises in, from the stack where it is flat.

    `uphill` reads the slope off the element's own upward faces and raises where
    there is none. A wall built in lifts has none: the panel is a flat-topped
    box, the parapet above it is another, and only the cap plate on top is laid
    to fall. The direction is still perfectly well defined — it is the cap's —
    and this is what walks up to find it.

    Recursive, because the stack is more than two deep here: the headhouse's
    walls carry parapets that carry cap plates, and only the third element has a
    slope. Area-weighted where a panel carries more than one, for the same
    reason `uphill` weights its own faces: a wall running under two parapets
    takes the direction of the longer one, and two that disagree flatly cancel
    into a raise rather than a silent coin-toss.

    It deliberately does not merge the stack and re-read it. Unioning a wall
    with its parapet and cap gives a solid whose upward faces are the cap's, so
    the answer would be the same — but the merged solid is a different shape
    from either, and `classify` and `wall_faces` would then be reading a body
    that is not in the substrate.
    """
    bodies = [faces.parts[i] for i in members]
    try:
        return uphill(bodies)
    except ValueError as flat:
        if "flat top" not in str(flat):
            raise

    # per path, not shared across branches: a cap plate spanning two parapets of
    # one wall must be counted under each of them, and a set mutated in place
    # would silently drop the second. It is here to stop a cycle, nothing more
    seen = (set() if seen is None else seen) | {members[0]}
    up = np.zeros(2)
    for other in _next_lift(faces.parts, faces.elements, members):
        if other[0] in seen:
            continue
        # a lift whose own stack ends flat contributes nothing rather than
        # aborting this wall: a parapet over part of a panel and a plant plinth
        # over the rest is an ordinary thing, and the parapet still names the
        # sides. Only a wall with no direction anywhere above it raises, below
        try:
            direction = rise(faces, other, seen)
        except ValueError as flat:
            if "flat top" not in str(flat):
                raise
            continue
        # weighted by how much underside the lift bears on us with, the same
        # shape of measure `uphill` weights its own faces by. It matters where a
        # panel runs under two parapets: the longer one governs, and two that
        # disagree flatly cancel into a raise rather than a silent coin-toss
        area = sum(
            part.area_faces[part.face_normals[:, 2] < -TOL].sum()
            for part in (faces.parts[i] for i in other)
        )
        up += area * direction

    length = float(np.linalg.norm(up))
    if length < TOL:
        name = faces.parts[members[0]].metadata.get("object", f"part {members[0]}")
        raise ValueError(
            f"flat top: {name!r} has no high side of its own and nothing "
            f"resting on it that continues its wall planes has one either, so "
            f"its exterior and interior are undefined. A stacked wall panel "
            f"takes its direction from the parapet above it; this stack ends "
            f"without a slope."
        )
    return up / length


def _grow_coplanar(faces, seed, candidates):
    """Grow `seed` into `candidates` across coplanar shared edges."""
    near, far = faces.body.face_adjacency.T
    flush = np.abs((faces.normals[near] * faces.normals[far]).sum(axis=1) - 1) < TOL
    grown = seed.copy()
    while True:
        added = np.zeros_like(grown)
        for this, other in ((near, far), (far, near)):
            joins = flush & grown[other] & candidates[this]
            added[this[joins]] = True
        if not (added & ~grown).any():
            return grown
        grown |= added


def wall_faces(faces, fall):
    """Every wall's exterior and interior faces, read off its own top.

    A wall's top falls toward its interior, so the face under the high edge is
    the exterior — the facade — and the one under the low edge is the interior.
    A vertical face lying across the fall is an end, and is neither: that is how
    this sample's section cuts drop out without anything having to list them.

    `fall` is the authored direction cosine separating the two from an end. It is
    passed rather than read from a module constant so that every rule below can
    be bound to the parameter file's value by `skins()` — the predicates `skin/`
    calls still have the `Faces -> bool[nfaces]` signature it expects, because
    `skins()` hands them over already bound.

    Except that a facade wraps a corner. Where one wall's end is coplanar with
    and joins its neighbour's facade, it is a return of that facade rather than
    an end, and is grown into the exterior set. Part 1's +X end is exactly this:
    the same plane as part 2's +X facade, continuing it round the corner. Its -X
    end is not, and stays bare.
    """
    vertical = np.abs(faces.normals[:, 2]) < TOL
    exterior = np.zeros(len(faces.owner), dtype=bool)
    interior = np.zeros(len(faces.owner), dtype=bool)
    for members in faces.elements:
        # the element is the unit on both counts. Its role is one value shared by
        # every body -- a parapet's cap plate reports `wall` with its leaves, and
        # would read `roof` alone -- so this admits all of `members` or none, and
        # the vertical faces of leaf and cap are classified together. It filtered
        # per body until 2026-08-16, which stopped discriminating the day
        # `Faces.roles` moved to the element and left the filter saying nothing.
        if faces.roles[members[0]] != substrate.WALL:
            continue
        # and the direction likewise: the cap carries the slope, so reading the
        # bodies separately would find nothing but flat tops on the leaves
        facing = faces.normals[:, :2] @ rise(faces, members)
        mine = vertical & np.isin(faces.owner, members)
        exterior |= mine & (facing > fall)
        interior |= mine & (facing < -fall)

    ends = vertical & faces.of_role(substrate.WALL) & ~exterior & ~interior
    return _grow_coplanar(faces, exterior, ends), interior


def _rules(faces, fall):
    """The whole face classification, derived once from the substrate.

    Which face of a wall the roof runs into decides how the membrane treats that
    wall: into its *interior* face and the membrane climbs it and carries over
    the top; into its *exterior* face and the membrane stops and flanges. That
    single test replaces the hand-listed step-wall planes, the per-part index
    sets and the NOT_OUTSIDE exclusions, all of which were this rule worked out
    by hand.

    The test is per *wall*, not per face. Only the one triangle of a step wall
    that shares an edge with the roof "meets" it, but the membrane climbs the
    whole face — so the touching faces elect the wall, and the wall carries all
    of its own faces.
    """
    exterior, interior = wall_faces(faces, fall)
    roof = _upward(faces.normals) & faces.of_role(substrate.ROOF)
    meets = faces.touching(roof)
    # elected per ELEMENT, not per body: the face that touches the roof belongs
    # to the inner leaf, and the top the membrane then carries over belongs to
    # the cap — different bodies of the same wall. Electing per body would climb
    # a leaf and stop at its flat top, leaving the cap bare.
    element = faces.element_of[faces.owner]
    climbed = np.isin(element, np.unique(element[interior & meets]))
    flanged = np.isin(element, np.unique(element[exterior & meets]))
    return exterior, interior, roof, climbed, flanged


def membrane_faces(faces, fall):
    """Membrane: the roof, the interior faces it climbs, and those walls' tops.

    It carries over the top rather than stopping at it, and the cladding takes
    that same top as its coping — see `cladding_faces`. The overlap is intended.
    """
    exterior, interior, roof, climbed, flanged = _rules(faces, fall)
    return roof | (interior & climbed) | (_upward(faces.normals) & climbed)


def membrane_skirts(faces, fall):
    """Down the exterior face of every wall the membrane carried over."""
    exterior, interior, roof, climbed, flanged = _rules(faces, fall)
    # a wall with a roof on both sides is carried over from one side and met from
    # the other; meeting wins, because that face gets a flange rather than a skirt
    return exterior & climbed & ~flanged


def membrane_flanges(faces, fall):
    """Where the membrane runs into a wall's exterior face, it stops and turns out."""
    exterior, interior, roof, climbed, flanged = _rules(faces, fall)
    return exterior & flanged


def facades_of(faces, system, fall):
    """The facade faces of every wall whose facade takes this cladding system.

    Geometry says which faces are facades; the part says which system clads them.
    A brick street front and a rainscreen headhouse can face the same way and sit
    in different planes, so neither a compass direction nor a named plane can
    separate them — but the material can, and it is authored anyway.
    """
    exterior, _ = wall_faces(faces, fall)
    return exterior & faces.tagged(FACADE, system)


def check_facades(faces, fall, systems=CLADDING_SYSTEMS):
    """Every facade claimed by exactly one cladding system, or raise.

    Without this a mis-stamped or unstamped part simply drops out of every skin:
    a facade silently left bare, or a whole system emitted as an empty mesh. That
    is the failure this module is being rewritten to stop making.
    """
    exterior, _ = wall_faces(faces, fall)
    claimed = np.zeros(len(faces.owner), dtype=bool)
    for system in systems:
        claimed |= facades_of(faces, system, fall)

    # double-claiming needs no check: a part carries one FACADE value, so it can
    # match at most one system. That stops being true the day a system is defined
    # by something other than the tag
    bare = exterior & ~claimed
    if bare.any():
        loose = sorted({int(o) + 1 for o in faces.owner[bare]})
        raise ValueError(
            f"{int(bare.sum())} facade faces on part(s) {loose} are claimed by no "
            f"cladding system in {systems} — check the {FACADE!r} metadata"
        )


def cladding_faces(faces, fall):
    """Cladding: every rainscreen facade, plus every wall top it wraps over.

    "Every wall top" includes the ones the membrane has already carried over, so
    a parapet coping belongs to **both** skins. That is deliberate (Duncan's
    call, 2026-08-16): it is what a parapet is built as — membrane upstand, metal
    coping over it — and it is what the rig already did on the sloped tops of
    parts 1 and 2. The two skins stack rather than collide, the cladding outboard
    by the difference of the offsets, and a test pins that ordering. Do not
    narrow either predicate to make the skins disjoint.
    """
    # ...but never a cornice. It stands proud of the facade, and the cladding
    # stops at its underside rather than wrapping it -- Duncan, 2026-08-19. The
    # face below it already ends there, so excluding the cornice's own faces is
    # the whole of it; the coping above is a separate face and is still claimed.
    return (
        facades_of(faces, RAINSCREEN, fall)
        | (_upward(faces.normals) & faces.of_role(substrate.WALL))
    ) & ~faces.tagged(CORNICE, True)


def cladding_skirts(faces, fall):
    """Down every wall's interior face."""
    exterior, interior, roof, climbed, flanged = _rules(faces, fall)
    return interior


# The face rules, keyed by skin name. Code, not numbers — this is the half of a
# skin spec that cannot go in a parameter file, and the half `skin/` never learns.
# `turn_out` is spelled `None` rather than omitted: the parameter file authors an
# `out` for every skin, so a skin with no turn-out has to say so on both sides,
# and `skins()` raises if the two disagree.
RULES = {
    "Membrane": {
        "keep": membrane_faces,
        "turn_down": membrane_skirts,
        # every panel that stops on part 4's exterior face turns out there
        "turn_out": membrane_flanges,
    },
    "Cladding": {
        "keep": cladding_faces,
        "turn_down": cladding_skirts,
        "turn_out": None,
    },
}


def classifier(params: dict):
    """`part -> WALL|ROOF`, with the authored thresholds bound.

    `substrate.classify` no longer defaults them, so this is the only place they
    are supplied. Every spec carries the same one — a classification is a fact
    about the substrate, not about a skin — but it rides in the spec anyway so
    that a spec is *exactly* `skin_over`'s argument list and nothing is assembled
    at the call site.
    """
    return partial(substrate.classify, **params["classify"])


def skins(params: dict | None = None) -> tuple[dict, ...]:
    """The skin specs: the authored numbers joined to `RULES` by name.

    One spec per skin, holding exactly what `skin_over` takes plus `name` and
    `display`. The predicates come out already bound to the authored `fall`, and
    the classifier to the authored thresholds, so what `skin/` receives still has
    the `Faces -> bool[nfaces]` and `part -> role` signatures it expects — the
    parameter layer stops at this function and no geometry code sees a knob.

    `params` defaults to reading `skin-parameters.yaml`, the same way the
    student-house's loaders default their paths. It is an *argument* rather than
    a module-level constant baked at import so that a what-if is a different file
    passed in at the call, which is the whole point of a full diffable copy.

    On migration this is where `topo["skin"]` arrives.

    The name join is a loud seam, in both directions. A skin authored with no
    rule set cannot be built, and a rule set no skin authors would otherwise sit
    there looking maintained while emitting nothing — the silent-omission failure
    `check_facades` exists to stop, one layer up.
    """
    params = parameters.resolve(params)
    fall = params["fall"]
    classify = classifier(params)

    authored = [spec["name"] for spec in params["skins"]]
    if len(set(authored)) != len(authored):
        raise parameters.ParameterError(
            f"parameter skins: duplicate name(s) in {authored} — a name is the join "
            f"to RULES, so it has to identify exactly one skin"
        )
    stray = [name for name in authored if name not in RULES]
    if stray:
        raise parameters.ParameterError(
            f"parameter skins: {stray} name no rule set in RULES ({sorted(RULES)}) — "
            f"a skin's numbers cannot be built without its face rules"
        )
    unbuilt = [name for name in RULES if name not in authored]
    if unbuilt:
        raise parameters.ParameterError(
            f"parameter skins: rule set(s) {unbuilt} are defined in RULES but named by "
            f"no skin in the parameter file, so they would emit nothing"
        )

    specs = []
    for spec in params["skins"]:
        rules = RULES[spec["name"]]
        if (rules["turn_out"] is None) != (float(spec["out"]) == 0.0):
            raise parameters.ParameterError(
                f"parameter skins.{spec['name']}.out={spec['out']} disagrees with its "
                f"rule set, whose turn_out is {rules['turn_out']} — a skin either stops "
                f"against something and turns out, or does neither"
            )
        specs.append(
            {
                "name": spec["name"],
                "distance": spec["distance"],
                "drop": spec["drop"],
                "out": spec["out"],
                "base": spec["base"],
                "display": spec["display"],
                "keep": partial(rules["keep"], fall=fall),
                "turn_down": partial(rules["turn_down"], fall=fall),
                "turn_out": None
                if rules["turn_out"] is None
                else partial(rules["turn_out"], fall=fall),
                "classify": classify,
            }
        )
    return tuple(specs)


def _skin_from(spec, parts, distance=None):
    """Build one skin from its spec — every `skin_over` argument, none defaulted."""
    return skin_over(
        parts,
        spec["distance"] if distance is None else distance,
        keep=spec["keep"],
        turn_down=spec["turn_down"],
        drop=spec["drop"],
        turn_out=spec["turn_out"],
        out=spec["out"],
        base=spec["base"],
        classify=spec["classify"],
    )


def separation_check(parts=None, params=None):
    """Both skins plus the smallest distance between them."""
    parts = current_substrate() if parts is None else parts
    group_cornices(parts)
    group_caps(parts, classifier(parameters.resolve(params)))
    built = [_skin_from(spec, parts) for spec in skins(params)]
    return separation(*built), built


def build(
    parts: list | None = None,
    emit_substrate: bool = False,
    params: dict | None = None,
) -> list[dict]:
    """Build the skins and write them to `build/`.

    `params` defaults to the committed `skin-parameters.yaml`; pass a loaded
    what-if copy to build a variant. See `skins()`.

    The module **reads** the substrate and never writes it. `emit_substrate`
    additionally dumps the parts as OBJ so they can be looked at in Blender; it
    is off by default and must stay off anywhere the substrate is live geometry.
    In the student-house the parts are Bonsai IFC objects carrying semantic data:
    re-emitting them would import a second, semantically dead copy of every part
    alongside the original, leaving two sources of truth in the scene. This rig
    transcribes its substrate from the scene rather than owning it, so a copy
    here is throwaway — but it still duplicates whatever was modelled, which is
    why `Cube` has to be hidden to see `Substrate_4`.
    """
    source = str(parameters.DEFAULT_PATH) if params is None else "(supplied)"
    params = parameters.resolve(params)
    specs = skins(params)
    print(f"  params     {source}")
    parts = current_substrate() if parts is None else parts
    # before anything reads a role: a separately-authored cap plate is not a
    # roof, it is the top of the wall it caps, and a cornice is not a slab, it is
    # the band standing proud of one. Cornices first, because `group_caps`
    # classifies every element up front and a lone cornice is exactly what
    # `classify` refuses. Both are idempotent, so a substrate that already groups
    # them is untouched
    group_cornices(parts)
    group_caps(parts, classifier(params))
    body = substrate.union(parts)
    check_facades(
        Faces(body, parts, _owner(body, parts), classifier(params)), params["fall"]
    )

    named = []
    if emit_substrate:
        # a bake names its own parts, and eighteen anonymous boxes in the
        # outliner are no use for checking a transcription. The prefix stays
        # either way, because the stale-copy sweep below globs on it
        named += [
            (
                f"Substrate_{part.metadata.get('name', i + 1)}",
                part,
                "solid",
                "substrate",
            )
            for i, part in enumerate(parts)
        ]

    built = {}
    for spec in specs:
        distance = spec["distance"]
        skin = _skin_from(spec, parts)
        built[spec["name"]] = skin
        named.append((spec["name"], skin, spec["display"], "skin"))

        gap = clearance(parts, skin)
        slope = skin.metadata["slope_deviation"]
        border = len(trimesh.grouping.group_rows(skin.edges_sorted, require_count=1))
        print(
            f"{spec['name']:<10} offset {distance * 1000:.0f} mm"
            f" | skirt {spec['drop'] * 1000:.0f} mm"
            f" | residual {skin.metadata['offset_residual']:.2e}"
            f" | clearance {gap * 1000:.4f} mm"
            f" | {'closed shell' if skin.is_watertight else f'open, {border} border edges'}"
        )
        if slope > TOL:
            print(f"           sloped planes absorb up to {slope * 1000:.3f} mm")
        # a fold is geometry the solve stopped constraining because no skin
        # covered it. Reported rather than left to the metadata: it is the one
        # place the offset is deliberately not solved, and silence about that is
        # exactly what the runaway guard was written to stop
        folds = skin.metadata.get("folds") or []
        if folds:
            print(
                f"           {len(folds)} fold(s) left unconstrained, at vertex"
                f" {', '.join(str(v) for v in folds)} — surfaces facing opposite"
                f" ways that this skin does not cover"
            )
        # anything closer than the slope planes were allowed to move is a real fold
        if gap < distance - slope - TOL:
            print(
                f"           WARNING: {(distance - gap) * 1000:.3f} mm inside the"
                f" requested offset — self-intersecting"
            )

    if len(built) == 2:
        a, b = built.values()
        print(f"           skin separation {separation(a, b) * 1000:.3f} mm")

    manifest = []
    BUILD_DIR.mkdir(exist_ok=True)
    # stale substrate copies from an earlier emit_substrate=True run would
    # otherwise sit in build/ and keep being re-imported
    for old in BUILD_DIR.glob("Substrate_*.obj"):
        if not any(name == old.stem for name, _, _, _ in named):
            old.unlink()
    for name, mesh, display, role in named:
        path = write_obj(mesh, BUILD_DIR / f"{name}.obj", name)
        manifest.append(
            {
                "name": name,
                "file": path.name,
                "role": role,
                "display": display,
                "bounds": mesh.bounds.tolist(),
            }
        )
        print(f"  {role:<9} {name:<12} {path}")

    if not emit_substrate:
        print(f"  substrate  {len(parts)} parts read, none written")

    (BUILD_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    # this rig transcribes its substrate, so a copy of it is throwaway and worth
    # seeing next to the skins. Do not pass this where the substrate is live.
    #
    # An OBJ path builds that bake instead of the transcribed rig. It is an
    # argument rather than a parameter-file entry because it names the substrate,
    # not a tunable number, and `skin-parameters.yaml` is the numbers.
    import sys

    if len(sys.argv) > 1:
        build(
            parts=substrate.from_obj(sys.argv[1], metadata={FACADE: RAINSCREEN}),
            emit_substrate=True,
        )
    else:
        build(emit_substrate=True)
