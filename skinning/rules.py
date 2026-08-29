#!/usr/bin/env python3
"""The face rules: what a wall is, what a membrane covers, where a skin stops.

`skinning.skin` offsets a substrate and knows nothing about buildings. This
module is the other half — the predicates over the union's faces, the grouping
that runs before any role is read, and the join from the authored numbers to
those predicates by name. It is where every derivation lives, and it sits beside
`skinning.skin` rather than inside it: the invariant is that the geometry never
learns what a wall or a membrane is, and keeping these out of it is what holds
that.

It is separate from `build.py` because `build.py` is this rig — the transcribed
`PART_N` substrate, the OBJ emission, the printed report — and none of that
migrates or is even in the package. These rules do. On migration the
student-house imports this module and `skinning.pipeline` beside it, passes its
own parts and `topo["skin"]`, and leaves `build.py` behind; see
`skinning/skin/parameters.py` for the parameter half of the same seam.

`skins()` takes a params **dict**, the way the student-house's `skin_pipeline.run`
takes a `topo` dict. It is the one function here with a **default**, and the
default reads `skin-parameters.yaml`: `skins()` with no argument resolves against
the committed file. That is deliberate for this rig — see the function's own
docstring — and it is the one thing in this module a host repo has to be careful
of, because `rules.skins()` there would silently return skin-test's numbers
instead of `topo["skin"]` and nothing would raise. Pass the dict. `pipeline.py`
always does, and refuses anything else.
"""

from __future__ import annotations

from functools import partial
from itertools import combinations

import numpy as np

from .skin import parameters, substrate
from .skin.offset import _plane_ids, elements_of

# manifold3d carries vertices as float32, so a union's faces sit up to ~5e-7 m
# off their true planes at metre-scale coordinates. Clearance is judged against
# that floor, not against exact arithmetic.
TOL = 1e-6  # 1 um, same grid substrate.prism() snaps to


# Every number these rules used to hold is now authored in `skin-parameters.yaml`
# and validated against `skin-parameters.schema.json` — the five skin distances,
# `fall`, and `classify`'s two thresholds. See `skinning/skin/parameters.py` for why, and
# for how the block migrates into `student-house-parameters.yaml` under `skin:`.
#
# What stays here are the RULES, which are code and not numbers: predicates over
# the union's faces. `skins()` joins the two by name.


# Which cladding system a wall's facade takes. Not derivable — no property of a
# wall's shape implies brick — so it rides on the part as metadata and the reader
# stamps it. Here that reader is `build.current_substrate`, or `substrate.from_obj`
# for a bake; in the student-house it is one read of the IFC material. A facade
# in a plane a rule could have picked out ("the frontmost -X one") would still
# be the wrong thing to key on: the headhouse has a second -X facade that is not
# brick, and a facade's material is a design decision, not a fact about where it
# sits.
FACADE = "facade"
CORNICE = "cornice"  # stamped by group_cornices; the cladding stops below one
# ...and stamped on the wall a cornice *finishes*: a cornice flush with its
# host's top is that wall's own cladding zone, where one partway up the face is
# a local interruption of one. Derived, and deliberately not a material: it says
# a facade is clad on its own account, not what it is clad in. Which masonry —
# brick on the street front, block on the firewall — stays authored on the part
# like every other cladding system. See `group_cornices` and `masonry_faces`
TOP_CORNICE = "top_cornice"
RAINSCREEN = "rainscreen"
BRICK = "brick"
# A wall the substrate cannot yet say the outside of, and which therefore takes
# no skin at all. Authored, like `FACADE`, and for the stronger version of the
# same reason: where a material is a design decision no shape implies, this is a
# fact about a *neighbouring* building that is not in the model. The
# student-house's internal join walls are the case in hand — Duncan, 2026-08-28:
# *"must be left uncovered until a full student-house site model is surveyed."*
#
# It is deliberately not a `FACADE` value. A facade value says what clads a
# facade; this says the wall has no facade to clad — `wall_faces` cannot give it
# an exterior or an interior, and `rise` cannot even be asked, because such a
# wall is commonly a stack of its own with no cap and no slope anywhere in it.
# That raise is the geometry saying it does not know, and this is the answer to
# it. Do not turn the raise itself into a silent skip: a wall someone forgot to
# cap looks identical from inside the geometry, and would then lose its cladding
# without a word.
UNSURVEYED = "unsurveyed"

CLADDING_SYSTEMS = (RAINSCREEN,)  # every system that claims facades; see check_facades

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
    # deduplicated on a rounded key but returned **unrounded**. `_next_lift`
    # matches these rows against each other within `TOL`, and rounding both
    # sides onto the same lattice first turns that tolerance into exact equality
    # of a rounded key — the thing CLAUDE.md's Tolerances section forbids and
    # `_plane_ids` was rewritten to stop doing. A wall running diagonally in plan
    # has a `d` that lands nowhere near the lattice, so two triangles of one face
    # can straddle a boundary; `flush` would then find no shared plane and `rise`
    # would raise `flat top` on a wall that plainly has a lift above it.
    rows = np.vstack(rows)
    _, first = np.unique(np.round(rows / TOL, 0), axis=0, return_index=True)
    return rows[np.sort(first)]


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


def _plan_overlap(parts, members, other) -> float:
    """The plan area two groups of bodies share — how much of one backs the other.

    A tie-break, and only ever that: both sides of every comparison it settles
    have already passed a test of the geometry proper. Bounds are enough for
    that, and are what the caller has; a diagonal wall's box overstates it, but
    both candidates are overstated the same way and the answer is a comparison.
    """
    boxes = []
    for group in (members, other):
        plan = np.array([[parts[i].bounds[j][:2] for i in group] for j in (0, 1)])
        boxes.append((plan[0].min(axis=0), plan[1].max(axis=0)))
    span = np.minimum(boxes[0][1], boxes[1][1]) - np.maximum(boxes[0][0], boxes[1][0])
    return float(np.prod(np.maximum(span, 0.0)))


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

    Where several bodies qualify, the one **backing most of the cornice's run**
    wins, and height breaks a tie in that. A band runs along the face it hangs
    on and past the returns at each end, so at a building corner it touches
    three walls and stands proud of all three: `Cornice-Deck9-N` runs 12.4 m
    across a 11.6 m parapet and over the 380 and 420 mm ends of the two walls
    returning at its ends. All three are the same 1856 mm tall, so height alone
    could not tell them apart and took whichever came first in the file — the
    380 mm return — and the union of that wall with a band four times its own
    length classified `ROOF` at horizontality 0.235 and stopped the build.
    Overlap says what "hangs on" means: 11.6 m of the run is backed by the wall
    the cornice belongs to and 380 mm by the one it merely crosses at the end.
    It is measured across the run — the plan axis the band is *not* projecting
    on — because along the projection axis every candidate is flush by
    construction. Every cornice on every other substrate here has exactly one
    candidate, so nothing but this corner is moved by the change.

    Two stamps come out of this as well as the regrouping. The cornice itself
    gets `metadata[CORNICE]`, because the two skins want different things and
    only one of them can be had by grouping. Its **host** gets
    `metadata[TOP_CORNICE]` when the cornice is flush with its top, which is
    what tells a masonry facade from a scupper's drip — see the constant, and
    `masonry_faces`.
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
            outward = np.zeros(3)
            outward[axis] = 1.0 if mine[0][axis] > theirs[0][axis] else -1.0
            if mine[1][axis] - mine[0][axis] >= min(
                theirs[1][k] - theirs[0][k] for k in (0, 1)
            ):
                continue  # projects further than the wall is thick: a wing, not a band
            # how much of the band this body actually backs, measured across the
            # run. At a corner the returns back only their own thickness
            run = 1 - axis
            backed = min(mine[1][run], theirs[1][run]) - max(mine[0][run], theirs[0][run])
            rank = (backed, theirs[1][2] - theirs[0][2])
            if index not in hosts or rank > hosts[index][1]:
                hosts[index] = (other, rank, outward)

    for index, (host, _, outward) in hosts.items():
        # the stamps come first and unconditionally. Being a cornice, and
        # finishing a wall, are facts about the geometry; whether there is an
        # element to join is a fact about how the substrate was authored.
        # `substrate.polyhedron` stamps no `"object"` at all, so gating them on
        # one silently switched both off for every transcribed substrate and
        # every synthetic fixture -- `cladding_faces` would have wrapped a
        # cornice instead of stopping below it. Found on review, 2026-08-26
        parts[index].metadata[CORNICE] = True
        # ...and the host is stamped when the cornice **finishes** it: a band
        # flush with the wall's top makes the whole face below one cladding
        # zone, which is what a masonry facade under a coping course is. A
        # cornice partway up a face is the other kind -- the drip that throws a
        # scupper's outflow clear -- and interrupts a cladding zone rather than
        # ending one. Measured on the live bake: `Cornice-Unit8-E` tops at
        # 13.0766 on a parapet topping at 13.0766, and the scupper's
        # `Cornice-Headhouse-E` tops at 14.495 on one topping at 14.718. The
        # cornice's run separates them too -- full width against 600 of
        # 4270 mm -- but height is the test because it carries the reason
        # the stamp is the direction the cornice stands proud in, not just the
        # fact of one. A masonry facade is the face the band overhangs, and a
        # wall's other exterior faces -- the returns a corner grows in -- are the
        # neighbouring elevation, clad in whatever clads that elevation
        if abs(parts[index].bounds[1][2] - parts[host].bounds[1][2]) <= TOL:
            already = parts[host].metadata.get(TOP_CORNICE)
            if already is not None and tuple(already) != tuple(outward):
                # a freestanding wall corniced on both faces is two masonry
                # elevations, and one direction cannot name them both. Assigning
                # in a loop would have kept whichever came last, silently
                # leaving the other face rainscreen (found on review 2026-08-26)
                raise ValueError(
                    f"{parts[host].metadata.get('name', host + 1)} is finished by "
                    f"cornices projecting {tuple(already)} and {tuple(outward)} — "
                    f"two masonry elevations on one wall, which is two skins and "
                    f"not one direction"
                )
            parts[host].metadata[TOP_CORNICE] = tuple(outward)

        owner = parts[host].metadata.get("object")
        if owner is None:
            continue  # ungrouped parts stand alone; there is no element to join
        parts[index].metadata["object"] = owner
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

    # a plate at a building corner rests on the wall it runs along *and* on the
    # return it crosses at its end, and continues both: `CapPlate-Deck9-S2` lies
    # in a rebate at the head of `Parapet-Deck9-W`, flush with both faces of it,
    # 380 mm of a 4510 mm run. So the claims are collected and the plate goes to
    # the wall that **backs most of it in plan** -- 1.025 m2 against 0.094 --
    # rather than to whichever element came last in the file, which is what an
    # assignment inside the loop amounted to. Contested on exactly one plate of
    # the three substrates here; everywhere else there is a single claimant and
    # the answer is unchanged
    claims = {}
    for members in elements:
        if roles[members[0]] != substrate.WALL:
            continue
        owner = parts[members[0]].metadata.get("object")
        if owner is None:
            continue  # ungrouped parts stand alone; there is no element to join
        for lift in _next_lift(parts, elements, members):
            if roles[lift[0]] != substrate.ROOF:
                continue
            backed = _plan_overlap(parts, members, lift)
            if lift[0] not in claims or backed > claims[lift[0]][1]:
                claims[lift[0]] = (lift, backed, owner)
    for lift, _, owner in claims.values():
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
        # weighted by how much underside the lift bears on **us** with, the same
        # shape of measure `uphill` weights its own faces by. It matters where a
        # panel runs under two parapets: the longer one governs, and two that
        # disagree flatly cancel into a raise rather than a silent coin-toss
        #
        # ...and that is `_plan_overlap`, not the lift's own underside area,
        # which is what this weighted by until 2026-08-28. The difference is a
        # lift that mostly bears on somebody else: at a building corner a wall
        # runs under its own parapet *and* under the two returns at its ends,
        # and a return is a whole elevation long. `L7-alleyback-W` bears
        # 2.865 m2 on `Parapet-Deck9-W`, which is its actual next lift, and
        # 0.137 m2 on `Parapet-Deck9-N` — but the north parapet's underside is
        # 10.397 m2 against the west's 4.406, so the returns outvoted the lift
        # and `rise` came back (0.604, -0.797): a diagonal that is no wall's
        # direction. Read per overlap it is (1.0, 0.008), the alley elevation.
        #
        # What that cost is a facade: the four `*-alleyback-W` panels inherit
        # the diagonal up their stack, so `facing` on their y = 7.54 end read
        # -0.797 and it classified **interior** rather than as the end it is.
        # An end is grown into the neighbouring elevation and clad; an interior
        # is not, so the cladding left a four-storey slot down the whole south
        # end of that wall. Duncan, 2026-08-28: *"a four storey vertical slot
        # which shouldn't be there... the southern ends of the alleyback-W
        # panels are not being covered."*
        up += _plan_overlap(faces.parts, members, other) * direction

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
    be bound to the parameter file's value by `skins()` — the predicates `skinning/skin/`
    calls still have the `Faces -> bool[nfaces]` signature it expects, because
    `skins()` hands them over already bound.

    Except that a facade wraps a corner. Where one wall's end is coplanar with
    and joins its neighbour's facade, it is a return of that facade rather than
    an end, and is grown into the exterior set. Part 1's +X end is exactly this:
    the same plane as part 2's +X facade, continuing it round the corner. Its -X
    end is not, and stays bare.

    **And an interior wraps a corner the same way.** Four parapets round a deck
    are one enclosure, and the wall that turns the corner presents its return on
    the neighbour's interior plane, joined to it — `Parapet-Deck9-W` at both ends
    of the deck. That is the inside of the enclosure continuing, and the membrane
    lining it has to cover the corner as well as the runs. It reached those
    returns until 2026-08-27 only because `_opening` was reading two of them as a
    7.1 m scupper, which is not a fact about the enclosure at all; said here, it
    is the same sentence as the facade's, and the exterior keeps precedence where
    an end somehow joins both.
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
        # ...and an unsurveyed wall is neither, because nothing is known to be
        # on either side of it. It contributes no seed, so its own faces stay
        # bare **and so do the ends its neighbours present on its plane**: the
        # growth below is what carries a facade round a corner, and with nothing
        # to grow from, a return coplanar with an unsurveyed wall is an end and
        # stays one. That is the whole of Duncan's "and their adjacent panel
        # ends on that plane", derived rather than listed. `rise` is not asked
        # either, which is the point — see `UNSURVEYED`
        # asked of **every** body, where `roles` above is safe to read off the
        # first: a role is computed per element and shared, but this tag rides
        # on the part, and `elements_of` orders members by part index rather
        # than by anything meaningful. A wall whose outer leaf is stamped and
        # whose inner leaf is not would otherwise be classified in full
        if any(faces.parts[i].metadata.get(UNSURVEYED) for i in members):
            continue
        # and the direction likewise: the cap carries the slope, so reading the
        # bodies separately would find nothing but flat tops on the leaves
        facing = faces.normals[:, :2] @ rise(faces, members)
        mine = vertical & np.isin(faces.owner, members)
        exterior |= mine & (facing > fall)
        interior |= mine & (facing < -fall)

    # ...and an unsurveyed wall is not somewhere a facade may grow *to* either.
    # Skipping it above only stops it seeding; a neighbour whose own facade is
    # coplanar with it and joined to it — the elevation running on into the
    # party wall — would otherwise carry the growth straight across, and the
    # panel would be clad after all. The whole-building bake does not pose it,
    # its join plane carrying nothing but ends, but "left uncovered" is not a
    # claim about which neighbours happen to be coplanar
    ends = (
        vertical
        & faces.of_role(substrate.WALL)
        & ~exterior
        & ~interior
        & ~faces.tagged(UNSURVEYED, True)
    )
    outside = _grow_coplanar(faces, exterior, ends)
    return outside, _grow_coplanar(faces, interior, ends & ~outside)


def _under_cover(faces, mask) -> np.ndarray:
    """Faces with substrate over them — the ones that cannot see the sky.

    A roof is a roof because it is the outside. The same slab can be both: the
    student-house's `Roof_Deck9_CLT` is the deck 9 roof where the insulation and
    the membrane sit on it, and the **headhouse floor** where it runs on under
    the headhouse and the insulation is cut away around it. One part, one role,
    two surfaces — so no test on the part can separate them and it has to be
    asked of the face. Duncan, 2026-08-26, on seven membrane faces inside the
    headhouse: *"The selected faces in Membrane should not be covered. They are
    on the inside of the headhouse walls."*

    Asked by casting straight up from the face and seeing whether the substrate
    is hit. That is what "outside" means, and there is nothing to author but the
    reading of a hit: one that rises less than `TOL` is the face catching its own
    ray, or a neighbour in its own plane clipped at the shared edge, and anything
    genuinely standing over a face is millimetres up at the very least. Filtering
    on the hit rather than nudging the origin is the difference between a rule
    and a fudge — a 1 µm nudge read **32** sloped faces as covered by themselves,
    a 10 µm one read none of them, and neither figure says anything about the
    building. The one that survives says a hit at zero height is not a hit.

    Read at the face **centroid**, which is exact here rather than a sample: the
    union splits a face wherever anything stands on it, so the deck's top comes
    through already cut along the headhouse's walls, one face inside and another
    outside. A roof only *partly* overhung — by a bridge landing on neither side
    of it — would come through whole and be read by its middle. No substrate
    here poses that.

    Measured: 2 faces of the deck 9 bake, both `Roof_Deck9_CLT` at z = 11.195
    inside the headhouse, and **none at all** on either of the other two.
    """
    which = np.flatnonzero(mask)
    covered = np.zeros(len(mask), dtype=bool)
    if not len(which):
        return covered
    origins = faces.centres[which]
    where, ray, _ = faces.body.ray.intersects_location(
        origins, np.tile((0.0, 0.0, 1.0), (len(which), 1)), multiple_hits=True
    )
    over = where[:, 2] - origins[ray][:, 2] > TOL
    covered[which[np.unique(ray[over])]] = True
    return covered


def _rules(faces, fall):
    """The whole face classification, derived once from the substrate.

    Which face of a wall the roof runs into decides how the membrane treats that
    wall: into its *interior* face and the membrane climbs it and carries over
    the top; into its *exterior* face and the membrane stops there. That single
    test replaces the hand-listed step-wall planes, the per-part index sets and
    the NOT_OUTSIDE exclusions, all of which were this rule worked out by hand.

    The test is per *wall*, not per face. Only the one triangle of a step wall
    that shares an edge with the roof "meets" it, but the membrane climbs the
    whole face — so the touching faces elect the wall, and the wall carries all
    of its own faces.

    **A roof runs into a wall through a ledge as well as through a face.** Where
    a parapet is thicker below the roof than above it, the roof build-up butts
    into the thick part and what it meets at its own level is the *top* of that
    thickening — an upward face of the wall, coplanar with the finished roof
    surface and continuous with it. `Parapet-Deck9-S` is 420 mm thick to
    z = 11.5344 and 248 mm above it, so the taper's top at 11.5344 shares an edge
    with a 172 mm ledge and touches no vertical face of the parapet at all: on
    `interior & meets` alone not one of the four deck 9 parapets was climbed, the
    membrane stopped at the roof's edge and their copings went bare. Duncan,
    2026-08-26: *"Horizontal ledges like F11 in Substrate_Parapet-Deck9-S should
    be covered with membrane. Membrane then continues up the parapet wall and
    covers the cap plates like on the headhouse."* Both halves of that are this
    one election — the ledge is picked up by "every upward face of a climbed
    wall" and the coping by the same rule, the cap plate being one body of the
    element. It elects nothing new on either headhouse bake, where the roof
    build-up sits on the walls and meets the parapets face to face.

    A wall a roof merely **bears on** is not elected by this: what is tested is
    the roof's *upward* face, and a deck resting on a wall top touches it with
    its underside. The two are at different levels and share no edge.

    There is no `flanged` any more. It named the walls a roof runs into on the
    *outside*, and existed to hand those faces a turn-out and to keep them from
    also getting a skirt. Both of those are now `_lap`'s, read off the substrate,
    so the election that remains is only "does the membrane **cover** this wall"
    — and the answer to that is `climbed` alone. Where the membrane stops on a
    wall it does not cover, the lap turns it up without being told.
    """
    exterior, interior = wall_faces(faces, fall)
    upward = _upward(faces.normals)
    # ...and only where it is the outside. See `_under_cover`: one slab is the
    # roof where the sky is over it and a floor where the building is
    roof = upward & faces.of_role(substrate.ROOF)
    roof &= ~_under_cover(faces, roof)
    meets = faces.touching(roof)
    # elected per ELEMENT, not per body: the face that touches the roof belongs
    # to the inner leaf, and the top the membrane then carries over belongs to
    # the cap — different bodies of the same wall. Electing per body would climb
    # a leaf and stop at its flat top, leaving the cap bare.
    element = faces.element_of[faces.owner]
    # the ledge test here is the **wider** of the two, and it is left so rather
    # than fixed. `cladding_faces` reads the same sentence with a second half —
    # the wall carries on above it — because a coping beside an *ungrouped*
    # cornice shares an edge with that cornice's top, a lone cornice classifies
    # `ROOF`, and on the first half alone the coping reads as a ledge. That
    # applies here too: such a wall is elected `climbed` off its own coping, and
    # `membrane_faces` then claims its interior face, its tops and its cheeks
    # although no roof runs into it anywhere. Measured 2026-08-27 by running
    # both: the elected element set is identical on all five substrates (rig 2,
    # deck bakes 8 and 4, headhouse 4, live bake 8), and the divergent face set
    # `tops & ~under & meets` is **empty** on every one of them — no wall top a
    # roof face touches is the top of its own element anywhere here. So
    # it is a latent divergence between two readings of one sentence, not a live
    # defect — add `& under` here, computed as `cladding_faces` computes it, on
    # the first substrate that puts an exposed cornice top beside the coping of
    # a wall no roof reaches. Do not narrow `cladding_faces` to match this
    # instead: there the second half is load-bearing today
    ledge = upward & faces.of_role(substrate.WALL)
    climbed = np.isin(element, np.unique(element[(interior | ledge) & meets]))
    return exterior, interior, roof, climbed


def _opening(faces):
    """The cheeks and the floor of an opening cut through a wall.

    A slot cut through a wall — a scupper — leaves two vertical faces looking
    **at** each other, the cheeks, and where it does not run to the bottom an
    upward face between them, the sill. The two faces across a wall's thickness
    are also opposed, and so are the two ends of a wall, but both of those look
    **away** from each other. That sign is the same measure `_next_lift` takes
    when it asks for faces "across this element's thickness". Nothing is
    authored.

    It is half the test and not the whole of it, which took a courtyard to show:
    a wall turning both inner corners of one holds a return on each of the two
    planes that face each other across it, and they face **toward**. So a cheek
    must also be **cut through** its wall, reaching both of its sides — see
    `through`, which is the other half of this function's own first sentence.

    Read per **body**, not per element, and that is not a detail. Group the
    scupper by element and the answer inverts twice over: the slot cuts through
    the cap plates as well, so `CapPlate-Headhouse-E`'s reveal and `E2`'s look at
    each other and the coping reads as a cheek pair; and the cornice is grouped
    into the parapet, so its own two ends are an away-facing pair sitting on the
    very same coplanar region as the sill, which makes the sill read as a
    thickness. Per body, each plate has its own thickness and the sill's only
    flanks are the cheeks.

    The price of that is paid at the end instead: a slot cuts through the plates
    over the wall too, and a plate split by the slot has one reveal rather than a
    pair, so the pairing cannot see it and the lining stopped 34 mm below the
    coping. The cheek set is therefore **grown along the surface** once the
    pairing and the floor are settled — a vertical face reached from a cheek by
    walking adjacency without leaving its plane is that cheek continuing. That is
    what "the slot cuts through the plate too" means geometrically, and it keeps
    the pairing per body where it belongs. **Contiguity, not the plane**: see the
    comment on the walk itself for why that distinction is the whole of it.

    Also read per coplanar **region** rather than per triangle, since the union
    triangulates a sill and one triangle of it may touch only one cheek.
    """
    body = faces.body
    vertical = np.abs(faces.normals[:, 2]) < TOL
    part, ids = faces.owner, _plane_ids(body)[0]

    regions: dict[tuple, list] = {}
    for f in range(len(part)):
        regions.setdefault((int(part[f]), int(ids[f])), []).append(f)
    middle = {k: faces.centres[v].mean(axis=0) for k, v in regions.items()}

    where = np.empty(len(part), dtype=int)
    for number, members in enumerate(regions.values()):
        where[members] = number
    neighbours: dict[int, set] = {n: set() for n in range(len(regions))}
    for u, v in body.face_adjacency:
        a, b = int(where[u]), int(where[v])
        if a != b:
            neighbours[a].add(b)
            neighbours[b].add(a)
    keys = list(regions)

    cut_through: dict[tuple, bool] = {}

    def through(key) -> bool:
        """Is this region a reveal — cut through its wall, side to side?

        A reveal reaches both faces of the wall the opening is cut through, so
        it comes through the union flanked by them: an opposed pair looking
        **away** from each other, which is a thickness by the same sign this
        function pairs cheeks with. The scupper's cheeks are flanked by their
        parapet's exterior and interior faces, 248 mm apart.

        This is the other half of "cut **through** a wall", and the half the
        toward-facing test above cannot supply. Both are true of a scupper;
        only the first is true of a courtyard, and a body carrying two opposite
        corners of one — `Parapet-Deck9-W`, which turns at both ends of the deck
        and so holds a return on each of the two planes that face each other
        across it — read as a 7.1 m cheek pair without it. What that cost was not
        a stray face: `cheeks` is grown along the surface below, so both planes
        were claimed the whole way round the building and the cladding came down
        the inside of every deck parapet to the ledge instead of stopping at its
        drip. Duncan, 2026-08-27: *"It looks like the rule is being interpreted
        differently in slightly different contexts."*

        The sign is the whole of it here too, and a flanking **pair** rather than
        a flanking face is what carries it: a court's inner face is flanked by
        the returns at its two ends, which are opposed as well — and look
        *toward* each other, because what lies between them is the court and not
        a wall.

        A **rebated** reveal — one stepped in the middle of the wall's thickness,
        as a window's often is — reaches one side only and is refused here. That
        is an under-claim rather than a wrong claim, it is posed by no substrate
        yet, and the shape of the answer when one poses it is that the step's two
        halves are one reveal continuing, which is what the growth below already
        says about a plate split by a slot.
        """
        if key not in cut_through:
            at = [
                keys[n]
                for n in neighbours[where[regions[key][0]]]
                if vertical[regions[keys[n]][0]]
            ]
            cut_through[key] = any(
                abs(faces.normals[regions[u][0]] @ faces.normals[regions[v][0]] + 1) < TOL
                # a thickness, so `-TOL` rather than `0`: two flanks on one
                # plane are a knife, and a knife is not a wall to cut through
                and faces.normals[regions[u][0]] @ (middle[v] - middle[u]) < -TOL
                for u, v in combinations(at, 2)
            )
        return cut_through[key]

    cheeks = np.zeros(len(part), dtype=bool)
    by_body: dict[int, list] = {}
    for key in regions:
        if vertical[regions[key][0]]:
            by_body.setdefault(key[0], []).append(key)
    for members in by_body.values():
        for i, u in enumerate(members):
            for v in members[i + 1:]:
                nu, nv = faces.normals[regions[u][0]], faces.normals[regions[v][0]]
                if abs(nu @ nv + 1) > TOL:
                    continue
                if nu @ (middle[v] - middle[u]) <= 0:   # away, not toward
                    continue
                if not (through(u) and through(v)):
                    continue
                cheeks[regions[u]] = cheeks[regions[v]] = True

    floor = np.zeros(len(part), dtype=bool)
    beside: dict[tuple, set] = {}
    tops = body.triangles[:, :, 2].max(axis=1)
    for near, far in np.vstack([body.face_adjacency, body.face_adjacency[:, ::-1]]):
        near, far = int(near), int(far)
        if not (cheeks[far] and not vertical[near] and part[far] == part[near]):
            continue
        # only a cheek that *rises* above the face bounds an opening in it. The
        # same cheeks also touch the wall's own coping, where the slot cuts
        # through it -- but there they stop at that level rather than standing
        # over it, and a coping is not the floor of anything
        if tops[far] > body.triangles[near][:, 2].max() + TOL:
            beside.setdefault((int(part[near]), int(ids[near])), set()).add(far)
    for key, flanks in beside.items():
        flanks = sorted(flanks)
        for i, u in enumerate(flanks):
            for v in flanks[i + 1:]:
                if abs(faces.normals[u] @ faces.normals[v] + 1) < TOL:
                    floor[regions[key]] = True

    # ...and only now is the cheek set **grown up the stack**, deliberately
    # after the floor is settled. A slot cut through a wall cuts through the cap
    # plates over it too, and this cap is two bodies split by the slot, so
    # neither plate contains a pair and the per-body pairing above cannot see
    # either reveal: the cladding's lining stopped at the parapet, 34 mm below
    # the coping (Duncan, 2026-08-22, correction 1). Do **not** fix that by
    # pairing per element -- `_opening`'s docstring rules that out for two other
    # reasons that both still hold.
    #
    # A reveal is instead recognised by being **the same surface continuing**:
    # a face on a cheek's plane, reached from that cheek by walking adjacency
    # without leaving the plane. Contiguity is the whole bound, and it has to be
    # -- growing on the shared plane alone is the `_meets_region` mistake this
    # module already made once and retired, because a building shares a plane
    # right up a stack and a coincidence a storey away is not this opening. The
    # walk crosses the parapet/plate boundary because the two are genuinely one
    # surface there, and stops at the edge of it because there is nothing
    # coplanar to step onto.
    #
    # After the floor, because a grown cheek reaches *above* the coping the slot
    # cuts through, and the floor test asks whether a cheek stands over an
    # upward face. Growing first would make the wall's own coping the floor of
    # an opening, and `cladding_faces` subtracts the floor -- so the coping
    # would silently leave the cladding. Measured before this was written.
    beyond: dict[int, list] = {}
    for u, v in body.face_adjacency:
        u, v = int(u), int(v)
        if ids[u] == ids[v]:
            beyond.setdefault(u, []).append(v)
            beyond.setdefault(v, []).append(u)

    edge = [int(f) for f in np.flatnonzero(cheeks)]
    while edge:
        f = edge.pop()
        for n in beyond.get(f, ()):
            if not cheeks[n] and vertical[n]:
                cheeks[n] = True
                edge.append(n)

    return cheeks, floor


def membrane_faces(faces, fall):
    """Membrane: the roof, the interior faces it climbs, and those walls' tops.

    It carries over the top rather than stopping at it, and the cladding takes
    that same top as its coping — see `cladding_faces`. The overlap is intended.
    """
    exterior, interior, roof, climbed = _rules(faces, fall)
    # ...and the cheeks of any opening cut through a wall it covers. They lie
    # *across* their wall's fall, so `wall_faces` calls them ends and neither
    # exterior nor interior could ever reach them: the membrane used to arrive
    # at the scupper cheeks as three overlapping laps instead of covering them.
    # Covering them is what lining an outlet is, and it is what lets the skin
    # flange out of the mouth -- with the cheek covered, the facade beside it
    # becomes a face the skin runs into. Duncan, 2026-08-20.
    cheeks, _ = _opening(faces)
    return (
        roof
        | (interior & climbed)
        | (_upward(faces.normals) & climbed)
        | (cheeks & climbed)
    )


def membrane_laps(faces, fall):
    """The membrane never stops on an arris: it laps onto whatever it runs into.

    One rule where there were two. A skirt down a coping's outer face and a
    flange up the wall a roof runs into are the same move — the surface reaching
    an edge of what it covers and continuing across the face beyond — and which
    way it turns is a fact about that face, not about which list the wall was
    on. `skinning.skin.offset._across` reads the direction off the receiving face and
    `_lap` picks the drip or the upstand distance from it.

    So there is nothing left to elect here, and the two predicates that used to
    do the electing are gone with it: `membrane_skirts` (exterior faces of
    carried-over walls, minus the ones a roof ran into) and `membrane_flanges`
    (exterior faces of walls a roof ran into). Both were the geometry worked out
    by hand, in the way `wall_faces` retired the hand-listed planes before them.

    What is left is the one restriction Duncan's rule states outright: the
    membrane laps onto **vertical** surfaces. A sloped receiver would take a
    sloped lap, and nothing in this substrate wants one — where the membrane
    meets a slope it either covers it or ends over air.

    Two things this now reaches that no election did. The **scupper cheeks**:
    vertical faces lying across their parapet's fall, so `wall_faces` calls them
    ends and neither skirt nor flange could ever claim them, while the membrane
    plainly has to wrap them. And `Headhouse-N`'s **west end face**, where the
    Unit8 parapet butts in line — the membrane did turn up there, but only
    because the elected face beside it happened to overlap the cap by the 8 mm
    the offset itself adds. It is elected on its own account now.
    """
    return np.abs(faces.normals[:, 2]) < TOL


def facades_of(faces, system, fall):
    """The facade faces of every wall whose facade takes this cladding system.

    Geometry says which faces are facades; the part says which system clads them.
    A brick street front and a rainscreen headhouse can face the same way and sit
    in different planes, so neither a compass direction nor a named plane can
    separate them — but the material can, and it is authored anyway.
    """
    exterior, _ = wall_faces(faces, fall)
    return exterior & faces.tagged(FACADE, system)


def masonry_faces(faces, fall):
    """Masonry: every exterior facade of a wall a cornice finishes.

    Duncan, 2026-08-26: *"A vertical exterior wall with a cornice at the top
    (excludes scupper cornices) is clad with a separate skin at a seeded
    offset."* The cornice is the datum for it, and nothing else has to be said:
    `group_cornices` stamps `TOP_CORNICE` on the wall a cornice is flush with,
    and this is that wall's facades. `cladding_faces` subtracts the same set, so
    the two systems partition the facade set rather than overlapping — which is
    the one thing `check_facades` now asserts on top of the tag.

    It is the face the cornice **overhangs**, and not the wall's other exterior
    faces. A corner grows a wall's end into the exterior set (see `wall_faces`),
    but that end is the neighbouring elevation and is clad in whatever clads
    that elevation — so the test is the half-space `n . outward > 0`, using the
    direction `group_cornices` stamped. A half-space rather than a match on the
    axis, so a wall at a plan angle still reads.

    That face is then **grown along the surface**, the same move `_opening`
    makes for a cheek: a facade reached from it by walking adjacency without
    leaving its plane is that facade continuing. A wall is built in lifts and a
    cornice only touches the topmost one, so the host body alone is the parapet
    and not the wall — and the panel below it, sharing one facade plane, would
    stay rainscreen. That is not merely an under-claim, it **breaks the build**:
    one plane would be asked to move 0.085 and 0.150 at the same vertex, and
    `_vertex_planes` refuses. Found on review, 2026-08-26, and the reason the
    stack stopped being something to defer.

    **Contiguity is the bound**, as it is for the cheeks, and it is a real
    bound: a wall in the same plane and *touching* is the same elevation, where
    the same plane a storey away or across a joint is the `_meets_region`
    mistake this module made once and retired. Where a substrate does put two
    systems contiguous and coplanar, the growth over-claims — and
    `check_cladding` is what notices, because the grown set would then span two
    `FACADE` materials.

    Where the masonry meets that neighbour is then a miter like any other, and
    `facade_offsets` is what makes it the right one — the masonry runs through
    the corner to the rainscreen's own face, and the rainscreen stops behind it
    on the wall. Duncan, 2026-08-26: the brick will be thickened towards the
    wall, *"the ends of the bricks will be exposed on both ends and not covered
    by metal cladding"*.

    What this does **not** say is which masonry. Brick on a street front and
    block on a firewall are two allowances and therefore two skins, and which a
    wall takes is a material — authored on the part like every other cladding
    system, never derived.

    That join is **not made here, because nothing yet has two sides to join**:
    every part of every substrate is stamped one system, and intersecting with
    `Faces.tagged(FACADE, ...)` would empty this skin rather than select within
    it. So the cornice alone selects the wall, and the material will select
    *between* masonry skins the day a second allowance exists. Until then the
    hole that leaves is guarded rather than left open — `check_cladding` raises
    if the corniced walls of one substrate do not all carry the same system,
    which is exactly the moment this predicate stops being enough (found on
    review, 2026-08-26).
    """
    exterior, _ = wall_faces(faces, fall)
    seed = np.zeros(len(faces.owner), dtype=bool)
    for index, part in enumerate(faces.parts):
        outward = part.metadata.get(TOP_CORNICE)
        if outward is None:
            continue
        seed |= (
            exterior
            & (faces.owner == index)
            & (faces.normals @ np.asarray(outward, dtype=float) > TOL)
        )
    return _grow_coplanar(faces, seed, exterior)


def facade_offsets(faces, fall, mine, keep, others):
    """How far each face's plane moves when this cladding skin is solved.

    Its own `mine` everywhere, except on a **facade another cladding skin
    dresses**, which is where the two systems meet at a building corner. There
    the miter has to be taken onto the neighbour's plane rather than onto a copy
    of this skin's, and which plane that is depends on which of the two stands
    further out — Duncan's demonstration, 2026-08-26, and both halves of it fall
    out of one rule:

    - **A neighbour no further out than me: mitre onto its own surface.** The
      masonry at 150 mm meets the rainscreen at 85 mm, so it runs through the
      corner and its end lands in the rainscreen's plane, `y = 2.43 - 0.085`.
      The brick's end is exposed there, flush with the metal beside it.
    - **A neighbour standing further out than me: stop at the substrate.** The
      rainscreen meets the masonry, which is 65 mm proud of it, so it does not
      mitre onto the masonry's face at all — it dies on the wall behind it, at
      `x = 0`, which is the back of the cavity. That is the offset **zero** case
      and it is what "the outer system owns the corner" means in arithmetic.

    Scoped to facades, and that scoping is what keeps it honest rather than a
    general coupling between skins: a roof, a coping or a lap is dressed by
    whoever dresses it and no cladding skin mitres onto it. Only `wall_faces`'
    exterior set is consulted, and the membrane claims none of it.

    Two things this has to get right, and both were found by running it:

    - **A skin that clads no facade takes no facade miter.** The membrane covers
      roofs, interior faces, copings and cheeks and never an exterior facade, so
      it has no corner with a cladding system and every plane it touches moves
      by its own 8 mm. Derived, not listed: the test is whether this skin covers
      any of the exterior set at all. It cuts one way only, and that is the
      catch: `others` is every **sibling skin**, not every cladding system, so
      the membrane is also a miter *target*, and what keeps the cladding from
      taking an 8 mm miter onto it is the same emptiness read from the other
      side (`membrane_faces & exterior` is 0 on every substrate here). Not a
      construction: `membrane_faces` claims cheeks, and `wall_faces` grows a
      wall end coplanar with a neighbour's facade into the exterior set, so a
      scupper cut at a building corner would put a membrane face in it. Found on
      review, 2026-08-26; measured, not fixed, because a system list here would
      be a second place that says what `CLADDING_SYSTEMS` already says.
    - **The decision is per *plane*, not per face — over everything this skin
      does not itself cover.** A facade plane carries faces of several parts: at
      the north corner the `y = 2.43` plane holds the parapet's end, the wall
      beside it and the cornice's own end, and the cornice is clad by nobody.
      Per face, the cornice's end kept `mine` while the parapet's end took the
      neighbour's, and `_vertex_planes` refused the vertex they share — rightly,
      because a plane is one surface and one system finishes it.

      What that leaves, said plainly rather than claimed away: a plane carrying
      **both** a neighbour's face and one of this skin's own still splits, and
      still raises. It is not papered over, because the two readings are not
      reconcilable — a face this skin covers moves by `mine` by definition. That
      condition is two cladding systems finishing one surface, and it wants a
      decision rather than a default. `masonry_faces` grows along the plane
      exactly so the one substrate that would otherwise pose it — a wall built
      in lifts under one cornice — does not.

    `check_cladding` has already established that exactly one cladding skin
    covers each facade, so there is no order dependence here and no face can be
    claimed twice. A face **this** skin covers is masked out regardless, because
    that one is not a neighbour and moves by `mine` by definition.
    """
    exterior, _ = wall_faces(faces, fall)
    offsets = np.full(len(faces.owner), float(mine))
    covers = keep(faces)
    if not (exterior & covers).any():
        return offsets  # clads no facade, so it meets no cladding system

    elsewhere = exterior & ~covers
    ids, _ = _plane_ids(faces.body)
    for other, distance in others:
        theirs = np.unique(ids[other(faces) & elsewhere])
        if not len(theirs):
            continue
        # the neighbour's facade **plane**, not just the facade faces on it. A
        # plane is one surface to the solve -- `_vertex_planes` refuses a vertex
        # asked for two distances on one normal -- so a face that is on the
        # plane but is nobody's facade cannot be left at `mine` beside one that
        # mitres. `Roof_Deck9_CLT`'s end lies in the court elevation at
        # `x = 8.5` between two rainscreen-clad walls; leaving it out asked that
        # plane for 0.085 and 0.150 at once, at the vertex it shares with the
        # parapet above it. Faces this skin covers stay excluded, because those
        # move by `mine` by definition -- a plane carrying one of those and a
        # neighbour's facade too still splits, and still raises, which is the
        # decision described above
        offsets[np.isin(ids, theirs) & ~covers] = (
            float(distance) if distance <= mine else 0.0
        )
    return offsets


def reveal_faces(faces, fall, covers):
    """The substrate faces a cladding skin stops `reveal` off, not its own allowance.

    Duncan, 2026-08-27: *"The top of the masonry cladding should be offset by
    this value under a cornice. The cladding should be offset from bottom, and
    sides of the two scuppers by this value."* Two sets, and they are the same
    thing said of two features — a surface the skin **dies against** rather than
    covers, where dying `distance` away leaves a gap the size of the cavity
    instead of a joint:

    * **a cornice's soffit and its ends**, where this skin reaches them. Never an
      upward face, and that exclusion is the whole of the second half of Duncan's
      sentence — *"maintain its original offset from the top of the scuppers"*.
      A scupper cornice's top is the sill, which is the roof surface running out
      through the outlet, and a wall cornice's top is flush with the coping. Both
      are surfaces the water crosses, not edges the cladding stops beside, and
      both are shared with something the skin does hold at `distance`: at
      `v93 [8.5, 4.985, 14.495]` the headhouse taper lands on the sill plane
      exactly, so moving it asked one continuous surface to be 18 mm and 85 mm
      from the skin at one vertex. Measured before the exclusion existed: 68.703
      mm of slope absorption — `slope_deviation` is a max, so that pinned the
      build's second diagnostic at a value it could not fall below — and the
      cladding's turn-down band crossing the membrane over the roof by 0.1 mm.
    * **the cheeks of an opening this skin lines.** These it *covers*, so this is
      the one place a covered face moves by something other than `distance` —
      see `planar_offset`. A rainscreen returning into a reveal closes its cavity
      down to a sheet rather than carrying 85 mm of it into the opening.

    Only a skin that clads a facade takes a reveal, which is the gate
    `facade_offsets` already uses and is derived rather than listed. It is what
    keeps the **membrane** out: it lines the same cheeks and dies against the
    same cornices, at its own 8 mm, and it should — the reveal is where a
    cladding system stops, not where the waterproofing does.
    """
    target = np.zeros(len(covers), dtype=bool)
    exterior, _ = wall_faces(faces, fall)
    if not (exterior & covers).any():
        return target                   # clads no facade, so it meets no cornice
    cheeks, _ = _opening(faces)
    cornice = faces.tagged(CORNICE, True)
    return (
        cornice & ~_upward(faces.normals) & ~wrapped(faces, covers)
        & faces.touching(covers)
    ) | (cheeks & covers)


def wrapped(faces, covers) -> np.ndarray:
    """Faces of a cornice this skin **wraps** rather than stops against.

    Duncan, 2026-08-27: *"the skirt covering a cornice should extend to the
    bottom of the cornice."* Where a cornice's face continues a plane the skin
    is already on — the coping's fascia and the cornice's outer face flush with
    each other, which is how the band is drawn — `cladding_faces` grows onto it
    and the skin runs down the band. Such a cornice is not a thing this skin
    dies against, so it takes no `reveal`: there is no joint to hold when the
    surface simply carries on over it.

    Read per **body**, not per face. Being wrapped is a fact about the cornice —
    it is one band, and the skin either runs down it or stops above it — where
    per face would give its fascia one answer and the soffit sharing its bottom
    arris another, which is the same vertex asked two things.

    The covered face has to be one the skin runs **down**, which is why an
    upward one does not count. A cornice joined to a climbed parapet has its
    exposed top picked up by the membrane's "every upward face of a climbed
    wall", so on that test alone every such cornice read as wrapped and the
    membrane set its soffit to zero — a waterproofing layer holding a cladding
    detail. Covering a band's top is not running down its face.
    """
    cornice = faces.tagged(CORNICE, True)
    down = cornice & covers & ~_upward(faces.normals)
    return np.isin(faces.owner, np.unique(faces.owner[down])) & cornice


def flush_faces(faces, fall, covers) -> np.ndarray:
    """The soffit of a cornice this skin wraps — the plane it stops **flush** with.

    A flashing running down a cornice's face stops at its bottom arris. It does
    not hang `distance` below it into thin air, and it does not stop `reveal`
    short of it and leave the arris bare: it ends exactly where the substrate
    does, which is the offset-**zero** case `facade_offsets` already has a use
    for. Duncan's own arithmetic says so — the band drops 0.184719 off the
    coping's edge at `z = 12.920719`, and `12.920719 - 0.184719` is `12.736`,
    the cornice's underside to the micron.

    Only the underside, and only of a cornice this skin wraps. A cornice it
    merely reaches is `reveal_faces`' business and holds the joint instead.

    Gated on cladding a facade, the same test `reveal_faces` makes and for the
    same reason: both are where a *cladding* system finishes, and the membrane
    should hold neither. Today `wrapped`'s "runs down its face" clause already
    keeps it out — measured 0 on all four substrates — but only because no
    cornice here presents a return that reads as an interior face of a climbed
    parapet, which `membrane_faces` would cover. That is a fact about these
    bakes, where this is a fact about what a reveal is for. Found on review.
    """
    exterior, _ = wall_faces(faces, fall)
    if not (exterior & covers).any():
        return np.zeros(len(covers), dtype=bool)
    return wrapped(faces, covers) & (faces.normals[:, 2] < -TOL)


def skin_offsets(faces, fall, mine, reveal, keep, others):
    """How far each face's plane moves when this skin is solved: the whole rule.

    `facade_offsets` first — the miter onto a neighbouring cladding system — and
    then `reveal_faces` over the top of it. The two are composed here rather than
    written as one function because they answer different questions: one is about
    where this skin **meets another skin**, the other about where it **stops
    against the substrate**, and only the first needs to know the siblings exist.

    Both are applied **per plane**, for the reason `facade_offsets` gives at
    length: a plane is one surface to the solve, and `_vertex_planes` refuses a
    vertex asked for two distances on one normal. Per face is not an option and
    was measured — `two offsets on one plane at vertex 83 [8.08, 4.785, 14.495]`,
    where the scupper's sill and the drip cornice's top share the plane they are
    coplanar on.

    A plane is taken **only if it carries no face this skin covers that is not
    itself a reveal face**, and that clause is doing real work rather than
    guarding a hypothetical. A *scupper* cornice's ends carry nothing but the
    cornice — two faces, nothing clad — where a *wall* cornice's ends lie in the
    neighbouring elevation: `Cornice-Deck9-N` puts one on the `x = 8.5` court
    plane, which carries 21 faces of which 15 are the cladding's own. Taking that
    plane raised at `v90`, rightly; leaving it to `facade_offsets` is correct,
    because there the cornice's end is one face on an elevation this skin clads
    and the elevation owns the plane. The exception is a cheek, which this skin
    covers *and* holds at `reveal`: there the whole plane is reveal and the test
    passes on its own, with no special case to write.

    Where the two rules want the same plane it **raises** rather than picking.
    That is two systems and a substrate feature claiming one surface, and it is
    the same decision `facade_offsets` refuses to take by default. No substrate
    here poses it — every reveal plane is left at `mine` by the miter.
    """
    offsets = facade_offsets(faces, fall, mine, keep, others)
    covers = keep(faces)
    # the joint, and the arris the skin stops flush with. Disjoint by
    # construction -- `reveal_faces` excludes a cornice `wrapped` names -- so
    # the two lists below can never ask one plane for two distances
    held = reveal_faces(faces, fall, covers)
    flush = flush_faces(faces, fall, covers)
    if not (held.any() or flush.any()):
        return offsets

    ids, _ = _plane_ids(faces.body)

    def where(on) -> str:
        return (f"plane {np.round(faces.normals[on][0], 6).tolist()} at "
                f"{np.round(faces.centres[on][0], 4).tolist()}")

    # collected per plane **before** anything is written, because the two masks
    # are disjoint by face and that is not the same as disjoint by plane: two
    # cornices whose soffits sit at one level, one this skin wraps and one it
    # stops against, put a `held` face and a `flush` face on one plane. Writing
    # as we went made the second pass read the first's own value back and raise
    # the *facade* miter error, naming a cause that was not there. No substrate
    # here poses it -- the three soffits are at 11.4644, 12.736 and 14.425 --
    # and the guard is structural rather than measured for that reason. Found
    # on review, 2026-08-27
    want: dict[int, float] = {}
    for mask, distance in ((held, float(reveal)), (flush, 0.0)):
        for plane in np.unique(ids[mask]):
            plane = int(plane)
            if want.get(plane, distance) != distance:
                on = ids == plane
                raise ValueError(
                    f"{where(on)} is asked for {want[plane]} m and {distance} m at "
                    f"once: this skin wraps one cornice on it and stops against "
                    f"another. One surface cannot be both the arris a skirt ends on "
                    f"and the joint it holds — the two cornices want separating, or "
                    f"one of them is not what it looks like"
                )
            want[plane] = distance

    for plane, distance in want.items():
        on = ids == plane
        if (on & covers & ~(held | flush)).any():
            continue        # a facade this skin clads; `facade_offsets` owns it
        moved = offsets[on] != mine
        if moved.any():
            raise ValueError(
                f"{where(on)} is claimed both by a neighbouring cladding system "
                f"(moving it {sorted(set(offsets[on][moved].tolist()))} m) and by "
                f"this skin at {distance} m. One surface cannot be finished by two "
                f"systems and stopped short of at once — decide which, rather than "
                f"letting the order of these two rules decide it"
            )
        offsets[on] = distance
    return offsets


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
    # by something other than the tag — which is now the case, so the skin-level
    # half of this lives in `check_cladding` below
    bare = exterior & ~claimed
    if bare.any():
        loose = sorted({int(o) + 1 for o in faces.owner[bare]})
        raise ValueError(
            f"{int(bare.sum())} facade faces on part(s) {loose} are claimed by no "
            f"cladding system in {systems} — check the {FACADE!r} metadata"
        )


def check_cladding(faces, fall):
    """Every facade skinned by exactly one cladding skin, or raise.

    `check_facades` asks the same question of the authored **tag**, and that was
    the whole of it while a system was a tag and nothing else. The masonry set
    is *derived*: `masonry_faces` claims a corniced wall's facades and
    `cladding_faces` subtracts the same set, so the tag check now passes
    whatever that carve-out does — including passing while a facade is skinned
    twice or not at all. Reading the two predicates against each other is the
    only way to notice, so it is done here rather than left to whoever edits
    either of them next.

    A **cornice's own faces** are the one exterior thing a cladding skin may
    leave unclaimed, and that is the 2026-08-19 decision rather than an
    omission: the band is dressed by neither where both stop at it. Since
    2026-08-27 that is no longer all cornices — where a cornice's face continues
    a plane the cladding is already on, `cladding_faces` grows onto it and the
    skirt runs down the band. What is left unclaimed is exactly the cornices
    that stand proud of their wall, so that nothing clad is coplanar with them:
    the **scupper** drips, 4 faces on the live deck bake and 2 on each of the
    others, and nothing else on any of them.

    Kept separate from `check_facades` because they are separate claims. The
    two-facade fixture in the tests poses a facade tagged for a system no skin
    builds, which is a legitimate thing to assert about the tag and a failure to
    assert about the skins.
    """
    exterior, _ = wall_faces(faces, fall)
    cladding = cladding_faces(faces, fall)
    masonry = masonry_faces(faces, fall)

    # one masonry skin is one allowance, and `masonry_faces` selects on the
    # cornice alone because no substrate yet carries two masonry systems to
    # choose between. The day one does — the student-house has two corniced
    # walls, brick at 0.150 and the firewall's block at 0.140 + 0.020 — both
    # would land in this one skin at one offset, and `check_facades` would keep
    # passing because neither tag is wrong. So the condition that makes the
    # cornice insufficient is named here rather than discovered as geometry
    systems = {
        faces.parts[o].metadata.get(FACADE) for o in set(faces.owner[masonry].tolist())
    }
    if len(systems) > 1:
        raise ValueError(
            f"the walls a cornice finishes carry {sorted(map(str, systems))} — one "
            f"masonry skin is one allowance, so a substrate posing two needs a skin "
            f"each, selected on {FACADE!r} as well as on the cornice"
        )

    for mask, trouble in (
        (cladding & masonry, "claimed by both the cladding and the masonry skin"),
        (
            exterior & ~faces.tagged(CORNICE, True) & ~cladding & ~masonry,
            "claimed by neither cladding skin",
        ),
    ):
        if mask.any():
            loose = sorted(
                str(faces.parts[o].metadata.get("name", int(o) + 1))
                for o in set(faces.owner[mask].tolist())
            )
            raise ValueError(
                f"{int(mask.sum())} facade faces on part(s) {loose} are {trouble} — "
                f"`cladding_faces` and `masonry_faces` must partition the facade set"
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
    # ...but never a cornice, where the cladding runs *into* one: it stands
    # proud of the facade and the skin stops at its underside rather than
    # wrapping round from the wall face -- Duncan, 2026-08-19. The face below it
    # already ends there, so excluding the cornice's own faces is the whole of
    # that; the coping above is a separate face and is still claimed. What this
    # exclusion is **not** about is a cornice the skin is already level with --
    # see the growth at the end of this function, and note the two are not in
    # tension: one is the rainscreen declining to wrap a band from the wall
    # face, the other is the coping's fascia continuing down a plane it is
    # already on.
    # ...and never the floor of an opening cut through a wall. The scupper sill
    # is a wall top, so "every wall top" claimed it and the cladding lined the
    # inside of a 400 mm outlet -- which is not what a rainscreen does, and which
    # flared the coping's own mitre out through the mouth to within 8.7 mm of the
    # membrane. A rainscreen stops at the opening; the membrane lines it, and
    # still does. Duncan, 2026-08-20.
    # ...and the cheeks of an opening, but not its floor. A rainscreen lines the
    # reveal of an opening cut through a wall and stops at its sill, the same
    # way it stops at a window's. Duncan, 2026-08-22, having weighed it against
    # the floor's own reasoning above and kept the two apart. The selection is
    # right, and so is the geometry, as of 2026-08-25. It took three goes: the
    # selection (2026-08-22), then `_opening` growing the cheek set along the
    # surface so the lining reaches the coping, then `offset._knife_side` so its
    # bottom edge runs flat at the sill's offset instead of diving into the
    # scupper knife. `_trim_beside`, which cut the miter back and was the second
    # of those attempts, is backed out and is not wanted back -- it treated the
    # symptom. See NOTES, "Cause 1 fixed" and "Cause 2 fixed".
    # ...and never a face the masonry claims -- the one face of a corniced wall
    # its cornice overhangs, clad on its own account at its own allowance
    # (Duncan, 2026-08-26). It is the masonry's *own* mask that is subtracted,
    # not the corniced wall, and the difference is the whole corner: the wall's
    # ends are the neighbouring elevation and this skin still clads them, which
    # is what carries the rainscreen round to the wall face at `x = 0`. The
    # corniced wall's **top** is still a wall top and still takes this skin's
    # coping, which is the 2026-08-16 "both skins cap a wall" decision unchanged
    # ...and never a **ledge**: a wall top at the finished roof level, where the
    # roof runs into the wall rather than stopping at it. "Every wall top" meant
    # every upward face of a wall, so the rainscreen came down the inside of the
    # parapet and out across the ledge, under the membrane -- which is not
    # somewhere a rainscreen goes. Duncan, 2026-08-27; the test is below
    cornice = faces.tagged(CORNICE, True)
    _, _, roof, _ = _rules(faces, fall)
    tops = _upward(faces.normals) & faces.of_role(substrate.WALL)
    # a ledge is `_rules`' own sentence read the other way round: an upward face
    # of a wall that is **thicker below the roof than above it**. Both halves are
    # needed. The roof running in is what makes it roof rather than coping -- it
    # is the finished roof level, continuous with the build-up, and the membrane
    # covers it on that same election. And the wall carrying on above it is what
    # makes it a step rather than a top: a coping with a cornice beside it shares
    # an edge with the cornice's top, and where that cornice is its own element
    # -- ungrouped, as `group_cornices` leaves it -- the cornice classifies
    # `ROOF` and the coping would read as a ledge on the first half alone.
    highest = np.array([
        max(faces.parts[i].bounds[1][2] for i in members)
        for members in faces.elements
    ])[faces.element_of[faces.owner]]
    under = faces.body.triangles[:, :, 2].max(axis=1) < highest - TOL
    # ...and grown along the surface to the whole ledge, because the union
    # triangulates one and only the triangles on the roof's own edge touch it --
    # the same reason `_opening` reads a sill per coplanar region and `_rules`
    # elects a whole wall off the one triangle that meets the roof
    ledges = _grow_coplanar(faces, tops & under & faces.touching(roof), tops)
    cheeks, floor = _opening(faces)
    base = (
        (facades_of(faces, RAINSCREEN, fall) & ~masonry_faces(faces, fall))
        | (tops & ~ledges)
        | (cheeks & faces.of_role(substrate.WALL))
    ) & ~cornice & ~floor
    # ...except where a cornice's own face continues a plane this skin is
    # already on, which is the coping's fascia running down over the band --
    # Duncan, 2026-08-27: *"the skirt covering a cornice should extend to the
    # bottom of the cornice."* Grown along the surface rather than named, the
    # same move `masonry_faces` and `_opening` make, so the extent is derived
    # from the cornice's own depth and nothing is authored: it runs to the
    # bottom because that is where the coplanar run ends
    return base | (_grow_coplanar(faces, base, base | cornice) & cornice)


def cladding_laps(faces, fall):
    """Down every wall's interior face, and nowhere else — for now.

    The membrane's rule is geometric; this one is still the old election, held
    deliberately. Deciding what the cladding does where it runs into something
    is a separate conversation from deciding what the membrane does, and the
    membrane came first (Duncan, 2026-08-20). Widening this to
    `np.abs(faces.normals[:, 2]) < TOL` is the shape of the change when that
    conversation happens.

    The hazard this used to carry is **gone at source**, and the shape of it is
    worth keeping because it is what a widening has to not reintroduce. `_lap`
    read a receiving face's offset plane as `plane + distance`, the skin's own
    scalar — true of every receiver until `facade_offsets` began moving a
    neighbouring facade's plane by somebody else's allowance, or by zero. Widen
    this to every vertical face on that footing and the cladding could lap onto a
    facade the masonry dresses, where the assumption is 85 mm out: the run-on and
    fold tests would compare against a level that is not the surface, and
    silently place nothing or start a probe out in space. Measured on the live
    bake by doing it — `clearance` 74.89 → 8.62 mm.

    `_lap` now takes the per-face offsets, so every place it reasons about a
    named face reads that face's own. It moved no geometry when it landed
    (2026-08-27, with `reveal`): the four sites are `drip_at`'s miter, the fold's
    receiving level, the fold probe's step back onto the arris and the turned
    band's level, and on all four substrates each already had the scalar right.
    It is a backstop rather than a repair — but it is the backstop that makes
    widening this predicate a question about *what the cladding should do*
    rather than one about whether the machinery can express the answer.
    """
    exterior, interior, roof, climbed = _rules(faces, fall)
    return interior


# The face rules, keyed by skin name. Code, not numbers — this is the half of a
# skin spec that cannot go in a parameter file, and the half `skinning/skin/` never learns.
# Two predicates, not four: `keep` is what the skin covers and `lap` is what it
# may continue onto. The skirt/flange pair that used to sit here was one rule
# split in two by hand — see `membrane_laps`.
RULES = {
    "Membrane": {"keep": membrane_faces, "lap": membrane_laps},
    "Cladding": {"keep": cladding_faces, "lap": cladding_laps},
    # `lap: None` -- a skin that genuinely stops where it ends. Masonry is
    # abstracted as a surface here and what it does at a termination is a
    # thickness question, deferred with the thickness. `skins()` reads the None
    # and leaves `drop` and `out` unread, so both are authored zero
    "Masonry": {"keep": masonry_faces, "lap": None},
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


def _surveyed(predicate, fall):
    """`predicate` bound to `fall`, and never selecting an unsurveyed wall.

    Applied once here, to every skin's `keep` and `lap` alike, rather than
    written into each rule set: "no skin covers a wall the substrate cannot
    place" is one sentence about the substrate, not a different sentence per
    skin, and a rule set that had to remember it would eventually forget.

    `wall_faces` already keeps such a wall out of the exterior and interior
    sets, which is what leaves its facade and its neighbours' returns bare. This
    is the rest of it: a wall is claimed by role as well as by side — the
    cladding takes *every* wall top — and the top of an internal join panel is a
    slab bearing rather than a coping. Measured on the whole-building bake at 6
    faces, two on each of the three panels, and they survive into the union at
    all only because the floor slabs are absent: at every other lift the panel
    above sits straight on the one below and the top is buried.
    """
    ready = partial(predicate, fall=fall)

    def keep(faces):
        return ready(faces) & ~faces.tagged(UNSURVEYED, True)

    return keep


def skins(params: dict | None = None) -> tuple[dict, ...]:
    """The skin specs: the authored numbers joined to `RULES` by name.

    One spec per skin, holding exactly what `skin_over` takes plus `name`,
    `display` and `close` — the last two are read by `build()`, not by the
    offset: one says how Blender shows the skin and the other how wide a tear
    `skinning/skin/clean.py` may gusset. The predicates come out already bound to the authored `fall`, and
    the classifier to the authored thresholds, so what `skinning/skin/` receives still has
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

    # every skin's own `keep`, bound, so each spec can be handed the *others* --
    # `facade_offsets` needs them to know which system dresses the facade it
    # ends against. This is the only place one skin learns of another, and it
    # learns nothing but a predicate and a distance. `reveal` rides alongside it
    # into `skin_offsets`, which composes the two: a reveal is about the
    # substrate and needs no sibling at all
    bound = {
        spec["name"]: (_surveyed(RULES[spec["name"]]["keep"], fall), spec["distance"])
        for spec in params["skins"]
    }

    specs = []
    for spec in params["skins"]:
        rules = RULES[spec["name"]]
        # a rule set may say `"lap": None` -- a skin that genuinely stops where it
        # ends. `drop` and `out` are then unread, so the check below applies only
        # to a skin that does lap: both zero would leave it stopping dead on every
        # arris it reaches, which is the same thing said in two places
        if rules["lap"] is not None and float(spec["drop"]) == float(spec["out"]) == 0.0:
            raise parameters.ParameterError(
                f"parameter skins.{spec['name']}: both drop and out are zero, so the "
                f"skin has no lap in any direction and would stop dead on every arris "
                f"it reaches — set one of them, or set the rule set's `lap` to None"
            )
        specs.append(
            {
                "name": spec["name"],
                "distance": spec["distance"],
                "drop": spec["drop"],
                "out": spec["out"],
                "base": spec["base"],
                "close": spec["close"],
                "display": spec["display"],
                "keep": bound[spec["name"]][0],
                "offsets": partial(
                    skin_offsets,
                    fall=fall,
                    mine=spec["distance"],
                    reveal=params["reveal"],
                    keep=bound[spec["name"]][0],
                    others=tuple(
                        pair for name, pair in bound.items() if name != spec["name"]
                    ),
                ),
                "lap": None
                if rules["lap"] is None
                else _surveyed(rules["lap"], fall),
                "classify": classify,
            }
        )
    return tuple(specs)
