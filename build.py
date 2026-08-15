#!/usr/bin/env python3
"""Build the geometry headless into build/. Blender only ever loads the result."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from skin import clearance, separation, skin_over, substrate, write_obj
from skin.offset import Faces, _owner

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


# The membrane stops against a wall's exterior face rather than covering it. Every
# panel that ends there turns out this far along the axis it faces: the roof panels
# turn up, the step-wall climb turns -X, the exterior-wall skirt turns +X.
#
# Seeds here are deliberately non-degenerate (student-house CLAUDE.md, hard rule):
# no two of the five skin distances are equal, and none is an integer multiple of
# another. `Membrane.drop` used to be 0.100 and so did `Cladding.distance`, which
# meant a bug swapping a skirt depth for an offset produced identical geometry —
# invisible to both the tests and the eye.
UPSTAND = 0.310

# cos 45 deg. A wall's vertical face counts as exterior or interior when it faces
# along the fall of that wall's own top, and as an end when it lies across it.
FALL = 0.707


# Which cladding system a wall's facade takes. Not derivable — no property of a
# wall's shape implies brick — so it rides on the part as metadata and the reader
# stamps it. Here that reader is the transcription below; in the student-house it
# is one read of the IFC material. A facade in a plane a rule could have picked
# out ("the frontmost -X one") would still be the wrong thing to key on: the
# headhouse has a second -X facade that is not brick, and a facade's material is
# a design decision, not a fact about where it sits.
FACADE = "facade"
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


def uphill(part) -> np.ndarray:
    """The unit horizontal direction a part's top rises in.

    A plane of normal `n` carries z uphill along `-(n_x, n_y)`, so the top names
    its own fall. Area-weighted over the part's upward faces, because a wall
    carrying a hip has more than one top and the large one should govern.
    """
    up = part.face_normals[:, 2] > TOL
    if not up.any():
        raise ValueError("part has no upward face, so it has no high side")
    fall = (part.face_normals[up][:, :2] * part.area_faces[up][:, None]).sum(axis=0)
    length = float(np.linalg.norm(fall))
    if length < TOL:
        raise ValueError(
            "flat top: no high side, so exterior and interior are undefined. A "
            "stacked wall panel must take its direction from the parapet above it."
        )
    return -fall / length


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


def wall_faces(faces):
    """Every wall's exterior and interior faces, read off its own top.

    A wall's top falls toward its interior, so the face under the high edge is
    the exterior — the facade — and the one under the low edge is the interior.
    A vertical face lying across the fall is an end, and is neither: that is how
    this sample's section cuts drop out without anything having to list them.

    Except that a facade wraps a corner. Where one wall's end is coplanar with
    and joins its neighbour's facade, it is a return of that facade rather than
    an end, and is grown into the exterior set. Part 1's +X end is exactly this:
    the same plane as part 2's +X facade, continuing it round the corner. Its -X
    end is not, and stays bare.
    """
    vertical = np.abs(faces.normals[:, 2]) < TOL
    exterior = np.zeros(len(faces.owner), dtype=bool)
    interior = np.zeros(len(faces.owner), dtype=bool)
    for index, part in enumerate(faces.parts):
        if faces.roles[index] != substrate.WALL:
            continue
        facing = faces.normals[:, :2] @ uphill(part)
        mine = vertical & (faces.owner == index)
        exterior |= mine & (facing > FALL)
        interior |= mine & (facing < -FALL)

    ends = vertical & faces.of_role(substrate.WALL) & ~exterior & ~interior
    return _grow_coplanar(faces, exterior, ends), interior


def _rules(faces):
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
    exterior, interior = wall_faces(faces)
    roof = _upward(faces.normals) & faces.of_role(substrate.ROOF)
    meets = faces.touching(roof)
    climbed = np.isin(faces.owner, np.unique(faces.owner[interior & meets]))
    flanged = np.isin(faces.owner, np.unique(faces.owner[exterior & meets]))
    return exterior, interior, roof, climbed, flanged


def membrane_faces(faces):
    """Membrane: the roof, the interior faces it climbs, and those walls' tops."""
    exterior, interior, roof, climbed, flanged = _rules(faces)
    return roof | (interior & climbed) | (_upward(faces.normals) & climbed)


def membrane_skirts(faces):
    """Down the exterior face of every wall the membrane carried over."""
    exterior, interior, roof, climbed, flanged = _rules(faces)
    # a wall with a roof on both sides is carried over from one side and met from
    # the other; meeting wins, because that face gets a flange rather than a skirt
    return exterior & climbed & ~flanged


def membrane_flanges(faces):
    """Where the membrane runs into a wall's exterior face, it stops and turns out."""
    exterior, interior, roof, climbed, flanged = _rules(faces)
    return exterior & flanged


def facades_of(faces, system):
    """The facade faces of every wall whose facade takes this cladding system.

    Geometry says which faces are facades; the part says which system clads them.
    A brick street front and a rainscreen headhouse can face the same way and sit
    in different planes, so neither a compass direction nor a named plane can
    separate them — but the material can, and it is authored anyway.
    """
    exterior, _ = wall_faces(faces)
    return exterior & faces.tagged(FACADE, system)


def check_facades(faces, systems=CLADDING_SYSTEMS):
    """Every facade claimed by exactly one cladding system, or raise.

    Without this a mis-stamped or unstamped part simply drops out of every skin:
    a facade silently left bare, or a whole system emitted as an empty mesh. That
    is the failure this module is being rewritten to stop making.
    """
    exterior, _ = wall_faces(faces)
    claimed = np.zeros(len(faces.owner), dtype=bool)
    for system in systems:
        claimed |= facades_of(faces, system)

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


def cladding_faces(faces):
    """Cladding: every rainscreen facade, plus every wall top it wraps over."""
    return facades_of(faces, RAINSCREEN) | (
        _upward(faces.normals) & faces.of_role(substrate.WALL)
    )


def cladding_skirts(faces):
    """Down every wall's interior face."""
    exterior, interior, roof, meets, climbed = _rules(faces)
    return interior


# The two skins. Their offsets differ so they cannot collide: everywhere both
# exist they are 80 mm apart, normal to a shared substrate face.
SKINS = (
    {
        "name": "Membrane",
        "distance": 0.020,
        "drop": 0.145,  # skirt down the exterior walls
        "keep": membrane_faces,
        "turn_down": membrane_skirts,
        # every panel that stops on part 4's exterior face turns out there
        "out": UPSTAND,
        "turn_out": membrane_flanges,
        "display": "solid",
    },
    {
        "name": "Cladding",
        "distance": 0.085,
        "drop": 0.225,  # skirt down the interior walls, part 4's included
        "keep": cladding_faces,
        "turn_down": cladding_skirts,
        "display": "wire",
    },
)


def _skin_from(spec, parts, distance=None):
    """Build one skin from its spec. `turn_out`/`out` are optional."""
    return skin_over(
        parts,
        spec["distance"] if distance is None else distance,
        keep=spec["keep"],
        turn_down=spec["turn_down"],
        drop=spec["drop"],
        turn_out=spec.get("turn_out"),
        out=spec.get("out", 0.0),
    )


def separation_check(parts=None):
    """Both skins plus the smallest distance between them."""
    parts = current_substrate() if parts is None else parts
    skins = [_skin_from(s, parts) for s in SKINS]
    return separation(*skins), skins


def build(parts: list | None = None, emit_substrate: bool = False) -> list[dict]:
    """Build the skins and write them to `build/`.

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
    parts = current_substrate() if parts is None else parts
    body = trimesh.boolean.union(parts)
    check_facades(Faces(body, parts, _owner(body, parts)))

    named = []
    if emit_substrate:
        named += [
            (f"Substrate_{i + 1}", part, "solid", "substrate")
            for i, part in enumerate(parts)
        ]

    skins = {}
    for spec in SKINS:
        distance = spec["distance"]
        skin = _skin_from(spec, parts)
        skins[spec["name"]] = skin
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
        # anything closer than the slope planes were allowed to move is a real fold
        if gap < distance - slope - TOL:
            print(
                f"           WARNING: {(distance - gap) * 1000:.3f} mm inside the"
                f" requested offset — self-intersecting"
            )

    if len(skins) == 2:
        a, b = skins.values()
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
    build(emit_substrate=True)
