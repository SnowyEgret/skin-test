"""Reading a substrate from OBJ — the import path for geometry too large to
transcribe. Every check here is one the student-house export will actually meet."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from skin import skin_over, substrate
from skin.export import write_objs


def _two_object_obj(tmp_path, parts=None):
    parts = parts or [substrate.cube(2.0), substrate.cube(2.0, center=(3, 0, 0))]
    return write_objs(zip(("Wall_A", "Roof_B"), parts), tmp_path / "sub.obj")


def test_each_o_group_becomes_its_own_part(tmp_path):
    """Object identity is load bearing: `_owner` maps union faces back to parts
    and `classify` runs per part, so two objects must not arrive as one.

    trimesh 5.0.0's own OBJ loader merges every `o` group into a single mesh
    named after the first, which is why `_parse_obj` exists.
    """
    parts = substrate.from_obj(_two_object_obj(tmp_path))

    assert len(parts) == 2
    assert [p.metadata["name"] for p in parts] == ["Wall_A", "Roof_B"]
    assert all(p.is_watertight for p in parts)
    assert [round(p.volume, 9) for p in parts] == [8.0, 8.0]

    merged = trimesh.load(str(_two_object_obj(tmp_path)), force="scene")
    assert len(merged.geometry) == 1  # the behaviour being worked around


def test_metadata_is_stamped_on_every_part(tmp_path):
    """`skin/` does not know what a facade is, so the caller names the fact."""
    parts = substrate.from_obj(_two_object_obj(tmp_path), metadata={"facade": "brick"})
    assert all(p.metadata["facade"] == "brick" for p in parts)
    assert parts[0].metadata["name"] == "Wall_A"  # and the name still survives


def test_coordinates_are_snapped_on_the_way_in(tmp_path):
    """Transcription used to snap; the import path has to do it instead, or
    near-coincident faces become slivers in the union."""
    off = substrate.cube(2.0)
    off.vertices = off.vertices + 4.4e-8  # the skew a modelled part arrives with
    path = write_objs([("Skewed", off)], tmp_path / "skew.obj")

    part = substrate.from_obj(path)[0]
    assert np.allclose(part.vertices, np.round(part.vertices, 6), atol=0)
    assert np.allclose(np.abs(part.vertices), 1.0, atol=1e-12)  # back on the grid


def test_an_open_shell_is_refused_by_name(tmp_path):
    """`skin_over` unions the parts; a union over an open shell produces nonsense
    rather than an error, so it has to be caught at the seam."""
    box = substrate.cube(2.0)
    holed = trimesh.Trimesh(vertices=box.vertices, faces=box.faces[:-2], process=False)
    path = write_objs([("Wall_A", box), ("Holed_B", holed)], tmp_path / "open.obj")

    with pytest.raises(ValueError, match="'Holed_B' is not a closed solid"):
        substrate.from_obj(path)


def test_a_face_the_fan_cannot_tile_is_ear_clipped(tmp_path):
    """`polyhedron` fan-triangulates, which is faithful only for a loop that is
    star-shaped from its first vertex. A baked wall with a notch is not, and a
    silently inverted triangle inside a substrate is close to undebuggable.

    Signed triangle areas telescope to the true polygon area whatever the shape,
    so area cannot detect this — the fan test is that no triangle is inverted.
    What `from_obj` then does about it is ear-clip the loop: rotating it to start
    somewhere else does not save a U, which is star-shaped from no vertex at all.
    """
    u = np.array(  # a U in plan: star-shaped from no vertex at all
        [[0, 0, 0], [3, 0, 0], [3, 3, 0], [2, 3, 0],
         [2, 1, 0], [1, 1, 0], [1, 3, 0], [0, 3, 0]], dtype=float,
    )
    assert not substrate._fan_is_valid(u)
    assert substrate._fan_is_valid(u[[0, 1, 2, 7]])  # a convex quad of the same loop
    assert not any(substrate._fan_is_valid(np.roll(u, -r, axis=0)) for r in range(8))

    ears = substrate._triangulated(u)
    assert len(ears) == 6  # n - 2, so no corner was dropped
    tiled = trimesh.Trimesh(vertices=u, faces=ears)
    assert tiled.area == pytest.approx(7.0)  # 3x3 less the 1x2 slot
    assert (tiled.face_normals @ [0, 0, 1] > 0).all()  # none inverted


def test_a_loop_that_crosses_itself_is_refused_by_name(tmp_path):
    """Ear clipping tiles a *simple* loop. A bowtie is not one, and the clip has
    to say so rather than return whichever half it managed to cover — the area
    check is what notices, since the ears themselves are all well formed.
    """
    bowtie = np.array(  # skewed, so the two lobes do not cancel to no plane
        [[0, 0, 0], [4, 4, 0], [4, 0, 0], [0, 1, 0]], dtype=float
    )
    with pytest.raises(ValueError, match="not simple"):
        substrate._triangulated(bowtie)

    path = tmp_path / "bowtie.obj"
    path.write_text(
        "o Bowtie\n"
        + "".join(f"v {x:g} {y:g} {z:g}\n" for x, y, z in bowtie)
        + "f 1 2 3 4\n"
    )
    with pytest.raises(ValueError, match="'Bowtie' has a 4-sided face"):
        substrate.from_obj(path)


def test_a_collinear_corner_is_tiled_faithfully_rather_than_refused(tmp_path):
    """A redundant vertex on an edge — a T-junction left by a subdivided
    neighbour, ordinary in a Blender export — reads to `_fan_is_valid` as
    concavity, but only when it sits next to vertex 0 (the test is `> 0` and a
    straight corner gives exactly 0). That asymmetry was a standing open item:
    the same redundancy further round the loop passed and emitted a zero-area
    triangle.

    The clip settles it in the direction of accepting both. It uses the corner
    as an ordinary triangle vertex where an ear is available there, and drops it
    without emitting anything where one is not — either way no zero-area
    triangle reaches the mesh and the tiled area is the polygon's.
    """
    square = np.array(
        [[0, 0, 0], [1, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], dtype=float
    )
    assert not substrate._fan_is_valid(square)  # the extra corner leaves vertex 0
    assert substrate._fan_is_valid(np.roll(square, -1, axis=0))  # further round, fine

    tiled = trimesh.Trimesh(vertices=square, faces=substrate._triangulated(square))
    assert tiled.area == pytest.approx(4.0)
    assert (tiled.area_faces > 0).all()  # nothing zero-area was emitted
    assert (tiled.face_normals @ [0, 0, 1] > 0).all()


def test_a_face_before_any_object_is_refused(tmp_path):
    """Blender can merge objects on export; that has to fail, not import as one."""
    path = tmp_path / "unnamed.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

    with pytest.raises(ValueError, match="face before any `o` group"):
        substrate.from_obj(path)


def test_an_imported_substrate_skins(tmp_path):
    """The whole point: a substrate read from OBJ goes through `skin_over`
    exactly as a transcribed one does."""
    parts = substrate.from_obj(_two_object_obj(tmp_path))
    skin = skin_over(parts, 0.1)

    assert skin.is_watertight
    assert skin.metadata["offset_residual"] < 1e-9
    # abutting cubes 3 apart with a 2 gap: two separate offset bodies, not one
    assert np.allclose(skin.bounds, [[-1.1, -1.1, -1.1], [4.1, 1.1, 1.1]])


def _leaved_parapet():
    """A baked parapet: inner leaf, outer leaf, and a sloped cap over both."""
    inner = substrate.prism((0.00, 0, 0.0), (0.25, 4, 0.7))
    outer = substrate.prism((0.25, 0, 0.0), (0.42, 4, 0.7))
    cap = substrate.polyhedron(  # 0.75 high at x=0, 0.73 at x=0.42: falls +X
        [(0, 0, 0.70), (0.42, 0, 0.70), (0.42, 4, 0.70), (0, 4, 0.70),
         (0, 0, 0.75), (0.42, 0, 0.73), (0.42, 4, 0.73), (0, 4, 0.75)],
        [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
         [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]],
    )
    for part in (inner, outer, cap):
        part.metadata["object"] = "Parapet"
    return [inner, outer, cap]


def test_a_wall_takes_its_direction_from_the_element_not_the_body():
    """Only the cap is sloped, so a per-body reading raises on two thirds of a
    wall that plainly has a high side.

    Summing over the element fixes it without merging anything and without
    hunting for "the cap above": a flat face contributes (0, 0), so the leaf tops
    dilute the magnitude and never the direction.
    """
    from build import uphill

    inner, outer, cap = _leaved_parapet()

    for leaf in (inner, outer):
        with pytest.raises(ValueError, match="flat top"):
            uphill([leaf])                       # a leaf alone has no high side

    assert np.allclose(uphill([cap]), [-1, 0], atol=1e-3)
    assert np.allclose(uphill([inner, outer, cap]), [-1, 0], atol=1e-3)

    # the cap covers both leaves exactly, so the hidden flat top matches the
    # sloped one in area — half the upward surface of this wall is flat, and the
    # direction is still the cap's, because flat contributes (0, 0) not a vote
    flat = sum(p.area_faces[p.face_normals[:, 2] > 1e-6].sum() for p in (inner, outer))
    sloped = cap.area_faces[cap.face_normals[:, 2] > 1e-6].sum()
    assert np.isclose(flat, sloped, rtol=0.01)

    # and merging the leaves upstream would give the same answer, so the rule
    # does not commit us to the split
    assert np.allclose(uphill([trimesh.boolean.union([inner, outer, cap])]),
                       [-1, 0], atol=1e-3)


def test_elements_group_by_object_and_fall_back_to_one_part_each():
    """`metadata["object"]` names the element. Absent, every part is its own —
    the identity grouping, which is exactly the transcribed `PART_N` case."""
    from build import classifier, current_substrate
    from skin.offset import Faces, _owner
    from skin import parameters

    params = parameters.load_validated()
    grouped = _leaved_parapet()
    body = substrate.union(grouped)
    faces = Faces(body, grouped, _owner(body, grouped), classifier(params))
    assert faces.elements == [[0, 1, 2]]           # one wall, three bodies

    loose = current_substrate()                    # no `object` stamped
    body = substrate.union(loose)
    faces = Faces(body, loose, _owner(body, loose), classifier(params))
    assert faces.elements == [[0], [1], [2], [3]]  # four elements, one part each


def test_the_union_is_computed_about_the_origin():
    """manifold3d is float32, whose resolution scales with magnitude, so a boolean
    far from the origin resolves less finely — and where two nearly-coplanar faces
    meet, that error is amplified by the shallow angle between them.

    The artifact itself is **not** reproduced here. It needs sloped faces mitring
    at a shallow angle 15 m out, which this substrate has no way to pose; the
    evidence is the headhouse parapets, where the union returned a second body,
    a 359 mm sliver of mean thickness 0.04 µm — an order of magnitude below
    manifold3d's own accuracy floor, so arithmetic rather than geometry. Centred
    on the origin the same parts return one clean body. See NOTES.md.

    What is pinned here is the mechanism, which is what could silently break: the
    shift is undone, so callers get the substrate where they left it.
    """
    near = [substrate.cube(2.0), substrate.cube(2.0, center=(2, 0, 0))]
    far = [substrate.cube(2.0, center=(0, 0, 1e5)),
           substrate.cube(2.0, center=(2, 0, 1e5))]

    here, there = substrate.union(near), substrate.union(far)
    assert np.allclose(here.bounds, [[-1, -1, -1], [3, 1, 1]])
    assert np.allclose(there.bounds - np.array([[0, 0, 1e5]] * 2), here.bounds)
    assert np.isclose(here.volume, there.volume)
    assert here.body_count == there.body_count == 1

    # the shift is snapped, so the substrate stays on the 1 um lattice
    assert np.allclose(here.vertices, np.round(here.vertices, 6), atol=0)
    # one part needs no union at all — but it comes back as a **copy**, not the
    # caller's own mesh. This asserted `is only` until 2026-08-25, which pinned
    # an optimisation that broke the invariant above it: `skin_over` treats the
    # union as a throwaway and writes plane ids into its metadata, so handing
    # back the part itself mutated the substrate. Same geometry, separate object
    only = substrate.cube(2.0)
    alone = substrate.union([only])
    assert alone is not only
    assert np.allclose(alone.vertices, only.vertices)
    assert np.array_equal(alone.faces, only.faces)

    # ...and the invariant that motivates it, end to end: skinning a one-part
    # substrate leaves that part exactly as it was found
    keys = set(only.metadata)
    skin_over([only], 0.05, keep=lambda faces: faces.normals[:, 2] > 0.9,
              classify=lambda part, **kw: substrate.WALL)
    assert set(only.metadata) == keys


def test_a_degenerate_sliver_is_refused_rather_than_flung_away(tmp_path):
    """A detached boolean fragment offsets to nonsense, and nothing else notices.

    Measured on the headhouse parapets: a four-vertex wedge orphaned at a mitred
    corner by 6 mm of overshoot went 20 km out under a 20 mm offset, while the
    120-face body it came from offset exactly. `offset_residual` stayed at 7e-12
    throughout — the hard constraints were all satisfied — so the failure first
    surfaced as a crash in the OBJ writer.
    """
    from skin import planar_offset

    sound = substrate.cube(2.0)
    assert planar_offset(sound, 0.02).metadata["max_displacement"] < 0.05

    # the wedge itself, transcribed off the union and moved to the origin: 254 mm
    # across, 29 mm tall, 5.8e-10 m^3 of volume. Its four faces carry exactly two
    # normals, +/-(0.707, 0.707, 0) — it is a fin of no thickness, and that is
    # what is now detected. A comment here used to claim it had four mutually
    # skew planes; it does not, and the claim only survived because the runaway
    # guard caught the symptom without anyone reading the planes.
    sliver = trimesh.Trimesh(
        vertices=np.array([[0.005647, 0.248100, 0.000000],
                           [0.000000, 0.253747, 0.011479],
                           [0.253747, 0.000000, 0.000000],
                           [0.253747, 0.000000, 0.028999]]),
        faces=np.array([[1, 0, 3], [2, 3, 0], [1, 2, 0], [1, 3, 2]]),
        process=False,
    )
    assert sliver.is_watertight
    with pytest.raises(ValueError, match="folds back on itself"):
        planar_offset(sliver, 0.02)  # no selection, so every plane is required


def test_the_transcribed_substrate_round_trips_through_obj(tmp_path):
    """The real oracle: write the four `PART_N` parts out, read them back, and
    get the same skins. Coordinates are already on the 1 µm grid, so the round
    trip has to be exact rather than merely close."""
    from build import current_substrate

    parts = current_substrate()
    names = [f"Part_{i + 1}" for i in range(len(parts))]
    path = write_objs(zip(names, parts), tmp_path / "transcribed.obj")

    back = substrate.from_obj(path, metadata={"facade": "rainscreen"})
    assert [p.metadata["name"] for p in back] == names
    for before, after in zip(parts, back):
        assert np.isclose(before.volume, after.volume, rtol=0, atol=1e-9)
        assert np.allclose(np.sort(before.bounds, axis=0), np.sort(after.bounds, axis=0))


REPO = Path(__file__).resolve().parent.parent
BAKE = REPO / "headhouse-walls-parapets-caps-clt-insulation.obj"
LIVE = REPO / "unit8-parapets-caps-clt-insulation-headhouse-extended-cornices.obj"
DECK = REPO / "deck9-parapets-caps-cornices-clt-insulation-unit7-walls-headhouse.obj"


def test_the_baked_headhouse_reads_and_skins():
    """The bake is the requirement, so it is a regression check and not a note.

    Four exports were committed before this one and nothing read any of them,
    which left every figure quoted about them unfalsifiable. This one pins what
    matters about the current bake: it reads, both skins solve, and each sits at
    its own offset with the two exactly their offset difference apart.

    The face counts are deliberately not pinned. They move whenever the bake
    does, and a test that has to be re-blessed on every export stops being read.
    """
    from build import (
        FACADE, RAINSCREEN, classifier, covered, group_caps, rise, skins, _skin_from,
    )
    from skin import parameters, substrate
    from skin.measure import buried, clearance, intersects, separation
    from skin.offset import Faces, _owner, elements_of

    parts = substrate.from_obj(BAKE, metadata={FACADE: RAINSCREEN})
    assert len(parts) == 18
    assert all(part.is_watertight for part in parts)

    params = parameters.load_validated()
    # the five cap plates are their own objects in this bake, and each joins the
    # parapet it caps: 16 elements become 11
    assert len(elements_of(parts)) == 16
    group_caps(parts, classifier(params))
    assert len(elements_of(parts)) == 11

    body = substrate.union(parts)
    assert body.is_watertight and body.body_count == 1

    # every wall resolves to an exact outboard axis, through two flat-topped
    # lifts to the cap plate that carries the fall
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    walls = [
        m for m in faces.elements if faces.roles[m[0]] == substrate.WALL
    ]
    assert len(walls) == 8  # four walls and the four parapets above them
    for members in walls:
        direction = rise(faces, members)
        assert np.abs(np.abs(direction) - [1.0, 0.0]).min() < 1e-9 or np.abs(
            np.abs(direction) - [0.0, 1.0]
        ).min() < 1e-9

    built = {}
    for spec in skins(params):
        # this bake carries no cornice, so it poses no masonry facade and that
        # skin is skipped here exactly as `build()` skips it -- see
        # `build.covered`. Asserted rather than silently filtered: a bake that
        # started posing one would be worth noticing
        if not covered(spec, faces):
            assert spec["name"] == "Masonry"
            continue
        skin = _skin_from(spec, parts)
        built[spec["name"]] = skin
        assert skin.metadata["offset_residual"] < 1e-14
        # every fold is an x = 8.5 self-contact: the knife corner where the E and
        # N walls meet, and the two jambs of the scupper slot. The membrane sees
        # all three; the **cladding sees one**, because `_knife_side` resolves the
        # two at the scupper before the contradiction reaches `_reconcile` — it
        # dresses no part of the roof taper, so the taper's end plane is read from
        # the parapet's side. That is cause 2, fixed 2026-08-25
        assert len(skin.metadata["folds"]) == (1 if spec["name"] == "Cladding" else 3)
        assert (np.abs(body.vertices[skin.metadata["folds"]][:, 0] - 8.5) < 1e-6).all()
        # every skin stands at its own offset -- kept generic, and kept in the
        # loop, so a skin added to `RULES` and the parameter file is checked by
        # arriving rather than by anyone remembering to name it here. The
        # cladding is exempt on this bake and the reason is **geometry, not a
        # defect**: the scupper reveal's mouth sits directly on the headhouse
        # roof, so no correct panel can stand 85 mm off everything there. It
        # reads 79.9703, pinned below. This is the documented `clearance`
        # exception -- "a skin that deliberately stops short of something
        # standing proud" -- and it is why `clearance` was demoted from the
        # build's verdict to a printed number on 2026-08-25
        if spec["name"] != "Cladding":
            gap = clearance(parts, skin)
            assert gap > spec["distance"] - skin.metadata["slope_deviation"] - 1e-6

    membrane, cladding = built["Membrane"], built["Cladding"]

    # Both read wrong until 2026-08-25 -- 3.6593 mm and 4.337 mm -- for one
    # reason, the scupper knife, and both came right together when `_knife_side`
    # landed, at 79.9703 and 71.973. They moved once more on 2026-08-26, when
    # the skirt's turn-down ran down to the sill's offset at Duncan's *"E84, 86
    # should be 5 mm lower"*: the sample taking the low reading is now the
    # turn-down's own bottom-outer corner, which stands over the headhouse roof
    # taper where the lining's corner 115 mm inboard stands 79.9703. Both
    # figures are the same geometry read at two points, and neither is a defect
    # -- this is the documented `clearance` exception, which is why it is
    # printed and asserts nothing in `build.py`. The corner is at
    # `(8.585, 4.752, 14.580)` and reads 74.8902 mm; it was at 4.755 reading
    # 75.0194 until `Cladding.drop` went 0.030 -> 0.033 on 2026-08-26, when the
    # masonry allowance arrived at 0.150 and `check_seeds` refused an exact 5x.
    # The 3 mm is the seed moving, not the geometry changing shape
    assert clearance(parts, cladding) == pytest.approx(0.0748902, abs=1e-6)
    # 0.0670180 until the same 3 mm seed change; the closest approach is at the
    # scupper, where the cladding's turn-down runs past the membrane's
    assert separation(membrane, cladding) == pytest.approx(0.0668889, abs=1e-6)

    # both skins cap the coping, as they did when the plates lived inside their
    # parapets. The cladding wraps over the plate; the membrane goes under it
    top = body.vertices[:, 2].max()
    assert cladding.vertices[:, 2].max() > top + 0.08
    # the membrane sits between the plate and the cladding over it, its own
    # offset up. Not pinned to the micron: the plate is sloped, so it is
    # least-squares and the high corner is not exactly `distance` in z
    assert membrane.vertices[:, 2].max() == pytest.approx(top + 0.008, abs=1e-3)
    assert top < membrane.vertices[:, 2].max() < cladding.vertices[:, 2].max()

    # the cladding stops at the scupper rather than lining it: the sill is a
    # wall top, so "every wall top" claimed it until `_opening` was written, and
    # the coping's own mitre then flared out through the mouth. Pinned by the
    # sill's own offset plane, 85 mm above it, being empty
    sill = body.vertices[:, 2].max() - 0.257     # z = 14.495, the slot's floor
    on = np.abs(cladding.triangles[:, :, 2] - (sill + 0.085)).max(axis=1) < 1e-6
    assert not on.any(), "the cladding is lining the inside of the scupper"

    # the verdict, since 2026-08-25: neither skin passes through the substrate
    # and neither folds through itself. `clearance` cannot see either -- it is
    # unsigned, and it moves when the surface is re-triangulated -- which is why
    # it is now a printed number and these are what `build.py` asserts
    surface = trimesh.util.concatenate(parts)
    for skin in built.values():
        assert buried(parts, skin) == 0
        assert intersects(skin, surface) == 0
        assert intersects(skin, skin) == 0

    # ...and the two skins do not cross. They did, at 2 triangle pairs on the
    # cheek lining just above the sill, where cause 2's raked bottom edge cut
    # down through the membrane lining the scupper. This assertion was pinned at
    # 2 on 2026-08-25 with a comment saying it was expected to **fail** when the
    # knife was fixed; it did, the same day, and this is the other side of it
    assert intersects(membrane, cladding) == 0


def test_the_scupper_comes_out_symmetrical_on_the_live_bake():
    """Duncan, 2026-08-21: *"The scupper is symmetrical."*

    It is — the slot, its cheeks, the cornice that runs past both jambs and the
    parapet around them are all mirrored about `y = 4.985` — so the membrane
    over it has to be, and it was not: the south side was missing the drip's
    return round the cornice end and 205 mm of the upstand beside the mouth.
    Nothing in the rules was asymmetric. `_room` read the first coplanar triangle
    that held its probe rather than every one of them, so the answer came out of
    the union's triangulation order, which is mirrored by nothing.

    The **vertex set** is pinned and the triangulation is not: the two sides
    agree point for point, while which diagonal each quad is split on does not
    have to mirror and does not.
    """
    from build import FACADE, RAINSCREEN, classifier, group_caps, group_cornices
    from build import skins, _skin_from
    from skin import parameters, substrate

    parts = substrate.from_obj(LIVE, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    membrane = _skin_from(
        next(spec for spec in skins(params) if spec["name"] == "Membrane"), parts
    )

    # the scupper's own neighbourhood: outboard of the parapet's inner face,
    # within a jamb's reach of the slot, and above the cornice's drip
    tri = membrane.triangles
    near = (
        (tri[:, :, 0] <= 8.6).all(axis=1)
        & (tri[:, :, 1] >= 4.3).all(axis=1)
        & (tri[:, :, 1] <= 5.7).all(axis=1)
        & (tri[:, :, 2] >= 14.3).all(axis=1)
    )
    assert near.sum() > 20, "the scupper is not dressed at all"

    axis = 4.985
    lattice = lambda p: tuple(np.round(np.asarray(p) / 1e-6).astype(np.int64))
    points = tri[near].reshape(-1, 3)
    here = {lattice(p) for p in points}
    mirrored = {lattice((p[0], 2 * axis - p[1], p[2])) for p in points}
    stray = here ^ mirrored
    assert not stray, (
        f"{len(stray)} vertices of the scupper have no counterpart across "
        f"y = {axis}: " + str(sorted(np.round(np.array(k) * 1e-6, 4).tolist()
                                     for k in stray)[:8])
    )


def test_the_bake_needs_ear_clipping_to_read_at_all():
    """Fourteen of its faces are notched, and six of those are star-shaped from
    no vertex, so no rotation of the loop would let the fan tile them. Pinned so
    that the clip is not mistaken for a nicety that could be dropped.
    """
    vertices, groups = substrate._parse_obj(BAKE.read_text())
    points = substrate.snapped(vertices)

    notched = unfannable = 0
    for _, loops in groups:
        for body in substrate._bodies(loops):
            used = sorted({i for loop in body for i in loop})
            local = {whole: part for part, whole in enumerate(used)}
            corners = points[used]
            faces, _ = substrate._collapsed(
                [[local[i] for i in loop] for loop in body], corners
            )
            for loop in faces:
                if len(loop) <= 3 or substrate._fan_is_valid(corners[loop]):
                    continue
                notched += 1
                turned = corners[loop]
                if not any(
                    substrate._fan_is_valid(np.roll(turned, -r, axis=0))
                    for r in range(len(loop))
                ):
                    unfannable += 1

    assert (notched, unfannable) == (14, 6)


def test_the_bake_s_separately_authored_cap_plates_are_capped_by_both_skins():
    """Duncan, 2026-08-19: the cap plates are skinned by both the membrane and
    the cladding, the same way they were when integrated with the parapet. That
    is the 2026-08-16 "both cap it" decision, which separating them into their
    own objects had reversed — each plate became its own element, classified
    `ROOF`, and `cladding_faces`' "every wall top" stopped reaching any coping.

    Pinned on the *plates* specifically, because the earlier version of this
    property was pinned on the rig, where a coping is a sloped wall top rather
    than a part of its own.
    """
    from build import (
        FACADE, RAINSCREEN, cladding_faces, classifier, group_caps, membrane_faces,
    )
    from skin import parameters, substrate
    from skin.offset import Faces, _owner

    params = parameters.load_validated()
    parts = substrate.from_obj(BAKE, metadata={FACADE: RAINSCREEN})
    group_caps(parts, classifier(params))

    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    plates = np.array(
        [parts[o].metadata["name"].startswith("CapPlate-") for o in faces.owner]
    )
    assert plates.any()

    # every cap plate face that is exposed upward is claimed by both skins
    tops = plates & (faces.normals[:, 2] > 0.9)
    assert tops.sum() == 10  # five plates, two triangles each
    assert membrane_faces(faces, params["fall"])[tops].all()
    assert cladding_faces(faces, params["fall"])[tops].all()

    # and every plate reads `wall`, through the parapet it was joined to --
    # alone, a 29 mm plate is unmistakably a slab
    assert all(faces.roles[o] == substrate.WALL for o in faces.owner[plates])
    lone = substrate.from_obj(BAKE)
    plate = next(p for p in lone if p.metadata["name"] == "CapPlate-Headhouse-N")
    assert classifier(params)(plate) == substrate.ROOF


def test_the_cheek_lining_reaches_the_coping_on_the_live_bake():
    """Duncan's corrections 1 and 2, 2026-08-22: *"V5 should be at V4, V52 should
    be at V49."*

    The lining stopped 34 mm below the coping, at the top of the parapet. Cause:
    the slot cuts through the cap plate as well as the parapet, `_opening` pairs
    cheeks **per body**, and this cap is two bodies split by the slot — so
    neither plate holds a pair and neither reveal ever became a cheek. Fixed
    2026-08-25 by *growing* the cheek set up the stack rather than by relaxing
    the pairing, which has to stay per body for two other reasons.

    Both cheeks, because the scupper is mirrored and the last defect here read
    correctly on one side and not the other.

    All four of Duncan's corrections are pinned here now. The bottom edge — his
    third and fourth — came right on 2026-08-25 with `_knife_side`, which reads
    the roof taper's end plane from the parapet's side because the cladding
    dresses no part of the taper. Until then it kinked at `x = 8.415` and dived
    to `z = 14.5036` over the last 170 mm.
    """
    from build import FACADE, RAINSCREEN, classifier, group_caps, group_cornices, skins, _skin_from
    from skin import parameters, substrate

    parts = substrate.from_obj(LIVE, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    spec = next(s for s in skins(params) if s["name"] == "Cladding")
    cladding = _skin_from(spec, parts)

    # the coping is laid to fall, so the reveal's head is sloped: west corner
    # high, east corner 21 mm lower. Both are the offset of the cap plate's own
    # top, and both are what Duncan named
    for cheek in (4.87, 5.10):
        on = np.abs(cladding.vertices[:, 1] - cheek) < 1e-6
        assert on.any(), f"nothing on the cheek plane y = {cheek}"
        corners = np.unique(np.round(cladding.vertices[on][:, [0, 2]], 6), axis=0)

        def has(x, z):
            return np.isclose(corners, [x, z], atol=1e-6).all(axis=1).any()

        assert has(7.995, 14.84009), f"y={cheek}: the lining's head misses V4"
        # corrections 3 and 4 -- the bottom edge, fixed 2026-08-25 by
        # `_knife_side`. It runs **flat** at the sill's offset from the facade's
        # offset out to the parapet's, where it used to kink at x = 8.415 and
        # dive to z = 14.5036 over the last 170 mm
        assert has(7.995, 14.580), f"y={cheek}: the lining's bottom-west corner"
        assert has(8.585, 14.580), f"y={cheek}: the lining's bottom-east corner"
        flat = corners[np.abs(corners[:, 1] - 14.580) < 1e-6]
        assert len(flat) == 2, f"y={cheek}: the bottom edge is not one straight run"
        assert corners[:, 1].min() == pytest.approx(14.580, abs=1e-6), (
            f"y={cheek}: something still hangs below the sill's offset"
        )
        assert has(8.585, 14.819018), f"y={cheek}: the lining's head misses V49"
        # ...and it reaches the full depth of the reveal, not the parapet's 8.5
        assert corners[:, 0].max() == pytest.approx(8.585, abs=1e-6)
        # ...and the old defect is gone: the lining used to *end* at 14.718, the
        # top of the parapet. That level is still a vertex on the west edge --
        # it is where the parapet's cheek meets the plate's reveal, collinear
        # along the edge and dissolved out of the written mesh -- so what
        # separates the two states is where the plane stops, not whether the
        # point exists
        assert corners[:, 1].max() == pytest.approx(14.84009, abs=1e-6)


def test_a_wall_a_cornice_finishes_is_clad_in_masonry_at_its_own_allowance():
    """Duncan, 2026-08-26: *"A vertical exterior wall with a cornice at the top
    (excludes scupper cornices) is clad with a separate skin at a seeded
    offset."*

    The live bake carries both kinds of cornice, which is what makes it the
    substrate that can pose this: `Cornice-Unit8-E` finishes `Parapet-Unit8-E`
    and `Cornice-Headhouse-E` is the scupper's outflow drip, partway up
    `Parapet-Headhouse-E`'s face. Only the first makes a masonry facade.

    The offset is checked against the substrate rather than against the
    parameter file alone, and the substrate agrees: the cornice was modelled
    170 mm deep, and the student-house authors a 150 mm street-front allowance
    with a 20 mm cornice projection over it. So the band standing exactly 20 mm
    proud of the masonry face is the drawing and the seed agreeing about the
    same detail from two directions.
    """
    from build import (
        CORNICE, FACADE, RAINSCREEN, TOP_CORNICE, classifier, cladding_faces,
        covered, group_caps, group_cornices, masonry_faces, skins, _skin_from,
    )
    from skin import parameters, substrate
    from skin.measure import separation
    from skin.offset import Faces, _owner

    parts = substrate.from_obj(LIVE, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    named = {part.metadata["name"]: part for part in parts}

    # both bodies are cornices; only one finishes the wall it hangs on
    assert named["Cornice-Unit8-E"].metadata[CORNICE] is True
    assert named["Cornice-Headhouse-E"].metadata[CORNICE] is True
    stamped = {n for n, part in named.items() if part.metadata.get(TOP_CORNICE)}
    assert stamped == {"Parapet-Unit8-E"}, (
        "the scupper's drip sits 223 mm below its parapet's top and must not "
        "make that parapet a masonry facade"
    )
    # ...and the stamp is the direction it stands proud in
    assert named["Parapet-Unit8-E"].metadata[TOP_CORNICE] == (-1.0, 0.0, 0.0)

    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    masonry = masonry_faces(faces, params["fall"])

    # the masonry is the face the cornice overhangs and nothing else -- not the
    # wall's ends, which are the north and south elevations and stay rainscreen.
    # That is Duncan's demonstration, 2026-08-26: the piece that turned the
    # corner is deleted
    assert masonry.any()
    assert {parts[o].metadata["name"] for o in faces.owner[masonry]} == {
        "Parapet-Unit8-E"
    }
    assert (faces.normals[masonry][:, 0] < -0.999).all(), "masonry turned a corner"
    assert not (masonry & cladding_faces(faces, params["fall"])).any()

    spec = next(s for s in skins(params) if s["name"] == "Masonry")
    assert covered(spec, faces)
    skin = _skin_from(spec, parts)
    assert skin.metadata["offset_residual"] < 1e-14

    # one panel, the whole east facade: at the authored allowance off the wall's
    # face at x = 0, stopping under the cornice's underside rather than wrapping
    # it, and mitred at each end onto the **rainscreen's** plane rather than its
    # own -- 2.430 - 0.085 and 11.300 + 0.085. See `build.facade_offsets`
    assert np.abs(skin.vertices[:, 0] + spec["distance"]).max() < 1e-6
    corners = {
        (round(v[1], 4), round(v[2], 4)) for v in skin.vertices
    }
    assert corners == {
        (2.345, 12.2), (2.345, 12.8566), (11.385, 12.2), (11.385, 12.8566)
    }
    z = skin.triangles[:, :, 2]
    assert z.max() == pytest.approx(13.0066 - spec["distance"], abs=1e-6)
    # ...and the cornice, modelled 170 mm deep, oversails it by the 20 mm the
    # student-house authors as `cornice.projection.street-front`
    cornice = named["Cornice-Unit8-E"].bounds
    assert -0.15 - cornice[0][0] == pytest.approx(0.020, abs=1e-6)

    # the rainscreen carries on round the corner onto the wall's ends and dies
    # on the wall's own face -- the back of the masonry cavity -- rather than
    # mitring onto a plane 85 mm out that nothing is clad to. Duncan, 2026-08-26:
    # *"E90 is moved -x to align with the exterior plane of the wall."* So its
    # end drops straight down at x = 0, and no panel stands at x = -0.085
    rainscreen = next(s for s in skins(params) if s["name"] == "Cladding")
    cladding = _skin_from(rainscreen, parts)
    assert not (np.abs(cladding.vertices[:, 0] + 0.085) < 1e-6).any()
    for end in (2.345, 11.385):
        here = cladding.vertices[np.abs(cladding.vertices[:, 1] - end) < 1e-6]
        # `TOL` rather than an exact zero: an offset of zero holds a vertex
        # where the union put it, and manifold3d's float32 leaves that up to
        # ~5e-7 m off the true plane -- the accuracy floor everything here sits
        # on, not a miss
        drop = here[np.abs(here[:, 0]) < 1e-6][:, 2]
        assert drop.min() == pytest.approx(12.265, abs=1e-6)
        assert drop.max() == pytest.approx(13.0766, abs=1e-6)

    # ...which leaves the two exactly the masonry's allowance apart at the
    # corner: the rainscreen at the wall face and the brick 150 mm off it. That
    # gap is the brick and its cavity, and it is left open until the masonry is
    # thickened -- Duncan, 2026-08-26, *"the ends of the bricks will be exposed
    # on both ends and not covered by metal cladding"*
    assert separation(cladding, skin) == pytest.approx(spec["distance"], abs=1e-6)


def test_a_skin_mitres_onto_the_plane_of_the_system_that_dresses_it():
    """The corner rule, read off the offsets themselves rather than the mesh.

    Duncan, 2026-08-26, having moved two edges in Blender to show the answer:
    the masonry's end aligns with *"the plane of the metal cladding"* and the
    metal's end with *"the exterior plane of the wall"*. Both are one rule — a
    skin mitres onto a neighbouring facade at that facade's own cladding offset,
    unless the neighbour stands further out, where it stops at the substrate.
    """
    from build import (
        FACADE, RAINSCREEN, TOP_CORNICE, classifier, group_caps, group_cornices,
        masonry_faces, skins, wall_faces, _owner,
    )
    from skin import parameters, substrate
    from skin.offset import Faces

    parts = substrate.from_obj(LIVE, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    exterior, _ = wall_faces(faces, params["fall"])
    masonry = masonry_faces(faces, params["fall"])
    spec = {s["name"]: s for s in skins(params)}

    # the membrane clads no facade, so it has no corner with a cladding system
    # and every plane it touches moves by its own 8 mm
    membrane = spec["Membrane"]["offsets"](faces)
    assert not (exterior & spec["Membrane"]["keep"](faces)).any()
    assert (membrane == spec["Membrane"]["distance"]).all()

    # the rainscreen meets masonry standing 65 mm proud of it, so it does not
    # mitre onto that face at all: it dies on the wall behind it, offset zero
    cladding = spec["Cladding"]["offsets"](faces)
    assert (cladding[masonry] == 0.0).all()
    assert (cladding[~masonry] == spec["Cladding"]["distance"]).all()

    # ...and the masonry, being the outer system, runs through the corner and
    # lands in the rainscreen's own plane
    stone = spec["Masonry"]["offsets"](faces)
    assert (stone[masonry] == spec["Masonry"]["distance"]).all()
    neighbour = exterior & spec["Cladding"]["keep"](faces)
    assert neighbour.any()
    assert (stone[neighbour] == spec["Cladding"]["distance"]).all()

    def owned_by(name):
        return np.array(
            [p.metadata.get("name") == name for p in parts]
        )[faces.owner]

    # the decision is per **plane**, not per face: `Cornice-Unit8-E`'s own end
    # face is clad by nobody, yet shares the `y = 2.43` plane with the parapet
    # end beside it, and one plane cannot move two distances at one vertex --
    # `_vertex_planes` raises on exactly that, and did before this was per plane
    finishing = exterior & owned_by("Cornice-Unit8-E")
    assert finishing.any()
    assert (stone[finishing] == spec["Cladding"]["distance"]).all()

    # ...and a face on no cladding plane at all keeps this skin's own distance,
    # because there is nothing there to mitre onto. The scupper's cornice is the
    # case: clad by nobody and coplanar with nothing anyone clads
    lonely = exterior & owned_by("Cornice-Headhouse-E")
    assert lonely.any()
    assert (stone[lonely] == spec["Masonry"]["distance"]).all()


def test_the_skirt_turns_down_to_the_sill_on_the_live_bake():
    """Duncan, 2026-08-22: *"The skirt should turn downwards on each side of the
    scupper."* And, reading the built bake on 2026-08-26: *"E84, 86 should be
    5 mm lower, even with E70, 71."*

    So the turn-down's bottom edge sits at the sill's offset, `z = 14.580`,
    level with the cheek lining's own bottom edge beside it — not at 14.585,
    where the **receiving** face corners. The parapet's inner face is buried by
    the roof taper's end below `z = 14.5036`, 8.6 mm above the sill, so the band
    runs past that corner to the end of the arris the cheek gives it.

    Pinned on the bake rather than on a synthetic rig deliberately: the shape
    that poses this is a knife, and a miniature of it raises in `_reconcile`
    unless the lap predicate is contrived to dress one side and not the other,
    which is the bake's own condition and not a general one.

    Both sides, because the scupper is mirrored and defects here have read
    correctly on one side and not the other before.
    """
    from build import FACADE, RAINSCREEN, classifier, group_caps, group_cornices, skins, _skin_from
    from skin import parameters, substrate

    parts = substrate.from_obj(LIVE, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    spec = next(s for s in skins(params) if s["name"] == "Cladding")
    skin = _skin_from(spec, parts)

    # the skirt lies on the parapet's inner face offset, x = 8.5 + 0.085
    on = np.abs(skin.triangles[:, :, 0] - 8.585).max(axis=1) < 1e-6
    assert on.any(), "no skirt at all on the parapet's inner face"
    y, z = skin.triangles[on][:, :, 1], skin.triangles[on][:, :, 2]

    # the cheek at 4.785 less the drip, out to the cheek's own lining at 4.870
    # -- and mirrored on the far side. Read off the authored `drop` rather than
    # written out, because these are seeds and a seed moves: `Cladding.drop` went
    # 0.030 -> 0.033 on 2026-08-26 when the masonry allowance arrived at 0.150
    # and `check_seeds` refused an exact 5x
    drop, out = spec["drop"], spec["distance"]
    for lo, hi in (
        (4.785 - drop, 4.785 + out),   # the near cheek, drip to lining
        (5.185 - out, 5.185 + drop),   # ...and the far one, mirrored
    ):
        band = (y.min(axis=1) > lo - 1e-6) & (y.max(axis=1) < hi + 1e-6)
        assert band.any(), f"no turn-down between y {lo} and {hi}"
        assert z[band].min() == pytest.approx(14.580, abs=1e-6), (
            f"the turn-down at y {lo}…{hi} stops at z = {z[band].min():.4f}: it "
            "ended where the parapet's inner face is buried by the roof taper "
            "rather than at the sill's offset, level with the lining beside it"
        )
        assert y[band].min() == pytest.approx(lo, abs=1e-6)
        assert y[band].max() == pytest.approx(hi, abs=1e-6)
        # ...and it reaches the coping's offset at the top
        assert z[band].max() == pytest.approx(14.819018, abs=1e-6)


def _slab(lo, hi, name):
    """One axis-aligned box, named and grouped as its own element."""
    lo, hi = np.array(lo, dtype=float), np.array(hi, dtype=float)
    box = trimesh.creation.box(
        extents=hi - lo,
        transform=trimesh.transformations.translation_matrix((lo + hi) / 2),
    )
    box.metadata.update({"name": name, "object": name})
    return box


def test_a_cornice_at_a_corner_hangs_on_the_wall_it_runs_along():
    """A band runs past the returns at each end, so it touches three walls.

    Every condition in `group_cornices` holds for all three — the returns are
    within its height, taller than it, outside its plan footprint and thicker
    than it projects — and where the three are the same height, as parapets
    around one roof are, the old "tallest wins" could not tell them apart and
    took whichever came first. On the live deck that was a 380 mm return, and
    the union of that wall with a band four times its own length classified
    `ROOF`: the build stopped in `group_caps` before any skin was tried.
    """
    from build import TOP_CORNICE, group_cornices

    parts = [
        _slab((0.0, 0.0, 0.0), (0.4, 5.0, 2.0), "Return-W"),   # first in the file
        _slab((0.4, 0.0, 0.0), (9.6, 0.4, 2.0), "Wall-Along"),
        _slab((9.6, 0.0, 0.0), (10.0, 5.0, 2.0), "Return-E"),
        _slab((0.0, -0.1, 1.9), (10.0, 0.0, 2.0), "Cornice"),
    ]
    group_cornices(parts)

    assert parts[3].metadata["object"] == "Wall-Along", (
        "the cornice joined a wall it only crosses at its end"
    )
    # ...and the stamp that makes a masonry elevation goes with it
    assert TOP_CORNICE in parts[1].metadata
    assert TOP_CORNICE not in parts[0].metadata
    assert TOP_CORNICE not in parts[2].metadata


def test_a_cap_plate_joins_the_wall_that_backs_most_of_it():
    """One plate over two walls in line is the longer wall's coping.

    `_next_lift` accepts it for both — it rests on each and is flush with the
    same pair of faces across both, which is exactly what "the next lift of
    this wall" means — so the plate is genuinely claimed twice and something
    has to choose. Assigning inside the loop chose whichever element came last
    in the file, which is not a property of the geometry at all.
    """
    from build import classifier, group_caps
    from skin import parameters

    parts = [
        _slab((0.0, 0.0, 0.0), (8.0, 0.4, 2.0), "Wall-Long"),
        _slab((8.0, 0.0, 0.0), (9.2, 0.4, 2.0), "Wall-Short"),  # last in the file
        _slab((0.0, 0.0, 2.0), (9.2, 0.4, 2.03), "Plate"),
    ]
    group_caps(parts, classifier(parameters.load_validated()))

    assert parts[2].metadata["object"] == "Wall-Long"
    # the walls themselves are untouched: `group_caps` groups the cap and not
    # the parapet under it, and the two walls are separate elements either way
    assert parts[0].metadata["object"] == "Wall-Long"
    assert parts[1].metadata["object"] == "Wall-Short"


@pytest.mark.parametrize("path", (BAKE, LIVE))
def test_dissolving_collinear_vertices_moves_no_outline(path):
    """`clean`'s `dissolve` is a tidy-up, and its whole claim is that it thins
    a ring without moving it. So the area it leaves is the area it was given.

    It stopped being true where a ring came back from GEOS with two consecutive
    coordinates a couple of ulps apart: they weld to one point, each then reads
    as straight through *its own self*, and both are dropped — which cuts the
    corner off. Measured on the deck bake before the fix: one L-shaped ring of
    the cladding came back as a diagonal and the skin gained 0.910 m² of
    surface the offset never placed. Neither bake here poses it; this states
    the property so that the next one that does is caught rather than shipped.
    """
    from build import FACADE, RAINSCREEN, classifier, covered, group_caps, group_cornices
    from build import skins, _skin_from
    from skin import parameters, substrate
    from skin.clean import clean
    from skin.offset import Faces, _owner

    parts = substrate.from_obj(path, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))

    for spec in skins(params):
        if not covered(spec, faces):
            continue
        skin = _skin_from(spec, parts)
        thin = clean(skin, dissolve=True, close=spec["close"])
        whole = clean(skin, dissolve=False, close=spec["close"])
        assert len(thin.faces) <= len(whole.faces), spec["name"]
        assert thin.area == pytest.approx(whole.area, abs=1e-8), (
            f"{spec['name']}: dissolving moved an outline — "
            f"{(thin.area - whole.area) * 1e6:+.3f} mm²"
        )


def test_a_roof_under_the_building_is_a_floor():
    """`_under_cover`, on the shape that poses it: a slab with a canopy over part
    of it.

    A roof is a roof because it is the outside, and the same slab is both — the
    student-house's deck 9 CLT is the roof where the insulation and the membrane
    sit on it and the **headhouse floor** where it runs on under the headhouse.
    One part, one role, two surfaces, so nothing about the part can separate
    them.
    """
    from build import _under_cover, _upward
    from skin import substrate
    from skin.offset import Faces, _owner

    parts = [
        _slab((0.0, 0.0, 0.0), (6.0, 6.0, 0.2), "Slab"),
        _slab((1.0, 1.0, 2.0), (3.0, 5.0, 2.2), "Canopy"),
        _slab((0.8, 0.8, 0.2), (1.0, 5.2, 2.0), "Prop"),
    ]
    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts))
    up = _upward(faces.normals)
    covered = _under_cover(faces, up)

    assert covered.any() and not covered.all()
    for f in np.flatnonzero(up):
        under = 1.0 <= faces.centres[f][0] <= 3.0 and 1.0 <= faces.centres[f][1] <= 5.0
        # ...on the slab, and below the canopy. The canopy's own top is not
        assert bool(covered[f]) == (under and faces.centres[f][2] < 1.0), (
            f"face at {np.round(faces.centres[f], 3).tolist()} read as "
            f"{'covered' if covered[f] else 'open'}"
        )
    # ...and it answers only what it is asked: a face outside the mask is left
    # alone, whatever is over it
    assert not _under_cover(faces, np.zeros(len(up), dtype=bool)).any()


def test_the_deck_bake_reads_and_skins():
    """The fourth substrate, and the one that found most of this.

    It poses what the two headhouse bakes do not: cap plates **mitred** at the
    corners rather than overlapped, a cornice running the full width of an
    elevation and past the returns at each end, a wall cantilevered over the
    court, and a roof deck that runs on under the headhouse and is that
    building's floor there.

    Pinned here: the union is one body (two of the mitres return a detached
    zero-thickness flap that `substrate.union` drops), all three skins solve,
    none of them crosses the substrate or itself, and the two things Duncan read
    back on 2026-08-26 — nothing inside the headhouse, and every parapet's ledge
    and coping carried.
    """
    from build import (
        FACADE, RAINSCREEN, classifier, covered, group_caps, group_cornices,
        skins, _skin_from,
    )
    from skin import parameters, substrate
    from skin.measure import buried, intersects

    parts = substrate.from_obj(DECK, metadata={FACADE: RAINSCREEN})
    assert len(parts) == 42          # 35 objects, six taper bodies in one of them
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))

    body = substrate.union(parts)
    assert body.body_count == 1, "a boolean flap survived the union"
    assert body.metadata["flaps_dropped"] == 2

    built = {}
    for spec in skins(params):
        skin = _skin_from(spec, parts)
        built[spec["name"]] = skin
        assert not intersects(skin, skin), f"{spec['name']} folds through itself"
        assert not intersects(skin, body), f"{spec['name']} crosses the substrate"
        assert not buried(parts, skin), f"{spec['name']} has a sample inside a part"
    assert set(built) == {"Membrane", "Cladding", "Masonry"}

    # nothing inside the headhouse: that deck is its floor, not a roof
    tri = built["Membrane"].triangles
    room = np.all(
        (tri >= (8.51, 2.86, 10.9)) & (tri <= (13.09, 7.11, 14.0)), axis=(1, 2)
    )
    assert not room.any()

    # ...and every deck 9 parapet carries the membrane from its ledge, at the
    # roof's own finished level, up and over its coping
    ledge = (np.abs(tri[:, :, 2] - (11.5344 + 0.008)) < 1e-6).all(axis=1)
    assert ledge.sum() >= 8
    for name, low, high in (("S", 7.11, 7.70), ("N", -0.20, 0.40),
                            ("E", 8.49, 8.94), ("W", 20.50, 20.92)):
        axis = 1 if name in "SN" else 0
        band = (tri[:, :, axis] >= low).all(axis=1) & (tri[:, :, axis] <= high).all(axis=1)
        assert (ledge & band).any(), f"parapet {name} has no membrane on its ledge"
        assert (band & (tri[:, :, 2] > 12.80).all(axis=1)).any(), (
            f"parapet {name} carries no membrane over its coping"
        )


def test_the_cladding_skirt_stops_at_its_drip_all_round_the_deck():
    """Duncan, 2026-08-27, reading the deck 9 build back: *"The cladding skirt is
    inconsistent around the deck... To the west of the scupper the skirt descends
    all the way down to the ledge (E44) instead of stopping at 12.792 and turning
    down the scupper as it did correctly to the east... It looks like the rule is
    being interpreted differently in slightly different contexts."*

    One skirt, four parapets, and it was three different things. Two rules were
    wrong under it and a third accident hid them apart:

    * `_opening` read `Parapet-Deck9-W`'s two corner returns as a 7.1 m cheek
      pair — they look at each other across the deck — and grew that along both
      planes, so the cladding **covered** the inside of the north and south
      parapets head to foot instead of lapping a drip onto them.
    * "every wall top" claimed the ledge at the finished roof level, so the skin
      then ran out across it, under the membrane.
    * and the two accidents that hid it: the scupper's sill takes the whole south
      ledge out with it as the floor of an opening, and the false cheek pair took
      the west one, leaving north and east clad and the other two bare.

    So the pin is the whole run: on every one of the four inner faces the skirt
    is a band from the coping's offset down to `12.825 - drop`, and the only
    cladding below that anywhere on the deck is the two turn-downs at the
    scupper, which are mirrored.
    """
    from build import FACADE, RAINSCREEN, classifier, group_caps, group_cornices, skins, _skin_from
    from skin import parameters, substrate

    parts = substrate.from_obj(DECK, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    spec = next(s for s in skins(params) if s["name"] == "Cladding")
    skin = _skin_from(spec, parts)
    out, drop = spec["distance"], spec["drop"]
    tri = skin.triangles
    arris, sill = 12.8250, 11.5344

    # the two turn-downs beside the scupper: `out` across the reveal the band
    # laps out of, plus its own `drop`, and mirrored about the slot
    turns = [(15.19 - drop, 15.19 + out), (16.39 - out, 16.39 + drop)]
    # the slot's own arris comes through the union up to a float32 ulp off the
    # nominal -- 1.0 um at the east cheek -- and these are containment tests
    # rather than measurements, so they are given the union's own accuracy floor
    near = 1e-5

    for name, axis, plane in (
        ("N", 1, 0.1881 + out), ("S", 1, 7.2919 - out),
        ("E", 0, 8.7481 + out), ("W", 0, 20.6919 - out),
    ):
        # ...at deck level: these planes carry the storey below as well, where
        # `L7-alleyback-W` reads its own return as a facade -- see NOTES
        on = (np.abs(tri[:, :, axis] - plane).max(axis=1) < 1e-6) & (
            tri[:, :, 2].min(axis=1) > sill - 1e-6
        )
        assert on.any(), f"no skirt at all on parapet {name}'s inner face"
        z, x = tri[on][:, :, 2], tri[on][:, :, 1 - axis]
        assert z.max() > arris + out - 0.005, f"parapet {name}'s skirt misses the coping"
        assert z.min() == pytest.approx(
            min(sill + out, arris - drop) if name == "S" else arris - drop, abs=1e-6
        )
        for f in range(len(z)):
            if z[f].min() > arris - drop - 1e-6:
                continue
            assert name == "S" and any(
                x[f].min() > lo - near and x[f].max() < hi + near for lo, hi in turns
            ), (
                f"parapet {name} carries cladding down to z = {z[f].min():.4f}, "
                f"below its own drip at {arris - drop:.4f}, away from the scupper"
            )
        if name == "S":
            for lo, hi in turns:
                band = (x.min(axis=1) > lo - near) & (x.max(axis=1) < hi + near)
                assert band.any(), f"no turn-down between x {lo} and {hi}"
                assert z[band].min() == pytest.approx(sill + out, abs=1e-6)

    # ...and nothing of this skin lies on the ledge, which is the roof's own
    # level and the membrane's to cover
    assert not (np.abs(tri[:, :, 2] - (sill + out)).max(axis=1) < 1e-6).any(), (
        "the rainscreen ran out across a ledge at the finished roof level"
    )


def test_the_deck_s_inner_corners_are_the_enclosure_continuing():
    """A facade wraps a corner and so does an interior.

    `Parapet-Deck9-W` runs past the ends of the north and south parapets, so it
    presents a return on each of *their* inner planes, joined to them. Those are
    the inside of the deck's enclosure continuing round the corner, and the
    membrane lining it covers them. Until 2026-08-27 it reached them only
    because `_opening` was reading two of them as a scupper's cheeks — which is
    not a fact about an enclosure at all, and which clad the whole of both planes
    on the way past.
    """
    from build import FACADE, RAINSCREEN, classifier, group_caps, group_cornices, wall_faces, _owner
    from skin import parameters, substrate
    from skin.offset import Faces

    parts = substrate.from_obj(DECK, metadata={FACADE: RAINSCREEN})
    params = parameters.load_validated()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    exterior, interior = wall_faces(faces, params["fall"])

    names = [parts[o].metadata.get("object") for o in faces.owner]
    for plane, axis, sign in ((0.1881, 1, 1.0), (7.2919, 1, -1.0)):
        corner = np.array([
            abs(faces.centres[f][axis] - plane) < 1e-6
            and faces.normals[f][axis] * sign > 1 - 1e-6
            and names[f] == "Parapet-Deck9-W"
            for f in range(len(faces.owner))
        ])
        assert corner.any(), f"the fixture has no return on the plane at {plane}"
        assert not (corner & ~interior).any(), (
            f"the return on the plane at {plane} is not read as the inside of "
            "the deck: the membrane laps onto it instead of covering it"
        )
        assert not (corner & exterior).any(), "...and it is not a facade either"
