import numpy as np
import pytest
import trimesh

from skin import clearance, parameters, planar_offset, skin_over, substrate, write_obj

D = 0.1

# The authored parameters, read once. Nothing under test defaults them any more,
# so a test that exercises a rule has to bind them the way `build.skins()` does.
PARAMS = parameters.load_validated()
FALL = PARAMS["fall"]


def _faces(parts, body=None):
    """`Faces` over the union of `parts`, with the authored classifier bound."""
    from build import classifier
    from skin.offset import Faces, _owner

    body = trimesh.boolean.union(parts) if body is None else body
    return Faces(body, parts, _owner(body, parts), classifier(PARAMS))


def _classify(part):
    from skin.substrate import classify

    return classify(part, **PARAMS["classify"])


def test_convex_offset_is_exact():
    base = substrate.cube(2.0)
    skin = planar_offset(base, D)

    assert skin.is_watertight and skin.volume > base.volume
    assert np.allclose(skin.bounds, [[-1.1] * 3, [1.1] * 3])
    assert skin.metadata["offset_residual"] < 1e-9


def test_concave_offset_keeps_reflex_corner_sharp():
    base = substrate.l_block()
    skin = planar_offset(base, D)

    assert skin.is_watertight
    assert skin.metadata["offset_residual"] < 1e-9
    # the reflex corner miters outward to (1+D, 1+D) rather than rounding off
    assert np.isclose(np.abs(skin.vertices[:, :2] - (1 + D)).sum(axis=1).min(), 0.0)


def test_abutting_parts_share_no_skin():
    parts = [substrate.cube(2.0), substrate.cube(2.0, center=(2, 0, 0))]
    skin = skin_over(parts, D)

    assert np.allclose(skin.bounds, [[-1.1, -1.1, -1.1], [3.1, 1.1, 1.1]])
    # a solid box's worth of volume: no skin surface inside the shared face
    assert np.isclose(skin.volume, 4.2 * 2.2 * 2.2)
    assert np.isclose(clearance(parts, skin), D)
    # the union was temporary: the substrate is still two separate cubes
    assert [round(p.volume, 9) for p in parts] == [8.0, 8.0]
    assert all(np.allclose(p.extents, 2.0) for p in parts)


def test_clearance_equals_offset_distance():
    for base in (substrate.cube(2.0), substrate.l_block(), substrate.u_block()):
        assert np.isclose(clearance(base, planar_offset(base, D)), D)


def test_self_intersection_is_detected():
    # a 1 m slot cannot carry a 0.6 m offset: opposing walls cross inside it
    base = substrate.u_block(slot=1.0)
    assert clearance(base, planar_offset(base, 0.6)) < 0.6


def test_upward_finds_flat_tops_and_rejects_sloped_soffits():
    """A top is a face that points up, not one that is merely off-axis.

    Testing `abs(n_z)` gets this wrong twice: a sloped soffit reads as a top, and
    a flat top is missed entirely. This substrate can prove neither — every top
    in it is sloped and every underside is exactly horizontal — so the part is
    built here on purpose. Both cases are ordinary in the student-house: a wall
    panel with a flat top has another panel stacked on it.
    """
    from build import _upward

    # flat top at z = 1; underside sloping from z = 0 up to z = 0.5.
    # wound outward throughout: polyhedron() can only re-wind an inconsistent
    # face list when networkx is installed, and it is not
    part = substrate.polyhedron(
        [(0, 0, 1), (2, 0, 1), (2, 1, 1), (0, 1, 1),
         (0, 0, 0), (2, 0, 0.5), (2, 1, 0.5), (0, 1, 0)],
        [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
         [3, 2, 6, 7], [0, 3, 7, 4], [1, 5, 6, 2]],
    )
    nz = part.face_normals[:, 2]
    up = _upward(part.face_normals)

    assert (nz > 0.999).any() and (nz < -0.001).any()  # the part poses both cases
    assert up[nz > 0.999].all()  # the flat top is a top
    assert not up[nz < 0].any()  # nothing facing down is, however it slopes
    assert np.isclose(part.area_faces[up].sum(), 2.0)  # exactly the 2 x 1 top

    # the substrate's own faces are unaffected: its tops all slope, its
    # undersides are all exactly horizontal
    from build import current_substrate

    for solid in current_substrate():
        z = solid.face_normals[:, 2]
        chosen = _upward(solid.face_normals)
        assert (chosen == (z > 1e-6)).all()
        assert not chosen[z < -1e-6].any()


def test_classify_reads_wall_or_roof_from_geometry_alone():
    """No IFC, no part indices: the shape decides.

    Parts 1, 2 and 4 are wall panels and part 3 is a roof, and `classify` has to
    recover that from geometry alone so the rules survive a substrate with
    hundreds of parts.
    """
    from skin.substrate import ROOF, WALL, horizontality

    from build import current_substrate

    parts = current_substrate()
    assert [_classify(p) for p in parts] == [WALL, WALL, ROOF, WALL]
    # the roof is the only part with more horizontal surface than vertical
    assert [horizontality(p) > 0.5 for p in parts] == [False, False, True, False]


def test_classify_survives_a_wall_that_does_not_run_along_an_axis():
    """The case bounds get wrong.

    An axis-aligned box around a diagonal wall inflates both horizontal extents
    until the height is the smallest of the three, so a bounds test calls it a
    slab. Face normals and the oriented box both still see a wall.
    """
    from skin.substrate import WALL

    wall = trimesh.creation.box(extents=(10.0, 0.3, 3.0))
    wall.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
    )
    assert int(np.argmin(wall.extents)) == 2  # AABB thinks it is thin vertically
    assert _classify(wall) == WALL  # and is wrong


def test_classify_raises_rather_than_guessing():
    """A part it cannot read must fail loudly, carrying the numbers.

    Silently mislabelling one part inside a large model is the failure mode that
    made the old module hard to debug.
    """
    from skin.substrate import AmbiguousPart

    for label, solid in (
        ("cube", trimesh.creation.box(extents=(1.0, 1.0, 1.0))),
        ("column", trimesh.creation.box(extents=(0.4, 0.4, 3.0))),
    ):
        with pytest.raises(AmbiguousPart) as raised:
            _classify(solid)
        assert "thin direction" in str(raised.value), label
        assert "extents" in str(raised.value), label


def test_exterior_and_interior_are_read_off_each_wall_s_own_slope():
    """The rule that replaced four hand-computed plane coordinates.

    A wall's top falls toward its interior, so the face under the high edge is
    the facade and the one under the low edge is the interior. Nothing names a
    plane or a part index.
    """
    from build import current_substrate, uphill, wall_faces

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    faces = _faces(parts, body)
    exterior, interior = wall_faces(faces, FALL)

    # each wall's top falls toward the interior, so uphill points at the facade
    assert np.allclose(uphill([parts[1]]), [1.0, 0.0], atol=1e-3)  # part 2 -> +X
    assert np.allclose(uphill([parts[3]]), [0.0, 1.0], atol=1e-3)  # part 4 -> +Y

    def planes(mask):
        return {
            tuple(np.round(n, 3))
            for n in np.unique(np.round(faces.normals[mask], 6), axis=0)
        }

    assert planes(exterior) == {(0.0, 1.0, 0.0), (1.0, 0.0, -0.0)}
    assert planes(interior) == {(0.0, -1.0, 0.0), (-1.0, 0.0, -0.0)}
    assert not (exterior & interior).any()

    # part 4's exterior faces back into the substrate, because its top falls
    # outward -- the rule follows the slope, not which way looks "outside"
    assert exterior[(faces.owner == 3) & (faces.normals[:, 1] > 0.999)].all()

    # ends and bottoms are neither, so the section cuts drop out unlisted...
    down = faces.normals[:, 2] < -0.999
    assert not (exterior | interior)[down].any()
    minus_x = (faces.owner == 0) & (faces.normals[:, 0] < -0.999)
    assert minus_x.any() and not (exterior | interior)[minus_x].any()

    # ...except where a facade wraps a corner: part 1's +X end is coplanar with
    # part 2's +X facade and continues it
    plus_x = (faces.owner == 0) & (faces.normals[:, 0] > 0.999)
    assert plus_x.any() and exterior[plus_x].all()


def test_uphill_refuses_a_flat_top():
    """A stacked wall panel has no high side, so it cannot name its own facade.

    `uphill` reads one element's own upward faces and stops there. Walking the
    stack to find the slope is `rise`'s job, below.
    """
    from build import uphill

    with pytest.raises(ValueError, match="flat top"):
        uphill([substrate.prism((0, 0, 0), (4.0, 0.3, 3.0))])


def _lift(name, lo, hi, tilt=0.0):
    """A box from `lo` to `hi`, its top falling `tilt` from the y0 edge."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    part = substrate.polyhedron(
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1 - tilt), (x0, y1, z1 - tilt)],
        [[0, 3, 2, 1], [4, 5, 6, 7], [0, 4, 7, 3],
         [1, 2, 6, 5], [0, 1, 5, 4], [3, 7, 6, 2]],
    )
    part.metadata["object"] = name
    return part


def test_a_flat_topped_panel_takes_its_direction_from_the_lift_above_it():
    """The open item this file carried from the start, arriving for real.

    A wall built in lifts is flat-topped all the way up — panel, parapet, and
    only the cap plate on top is laid to fall. `uphill` raises on every one of
    them; `rise` walks the stack and hands each the cap's direction. The stack
    here is three deep, as the headhouse's is, so a rule that only looked one
    element up would still leave the panel undefined.
    """
    from build import rise, uphill

    parts = [
        _lift("Panel", (0, 0, 0), (6.0, 0.4, 3.0)),
        _lift("Parapet", (0, 0, 3.0), (6.0, 0.4, 3.7)),
        _lift("Cap", (0, 0, 3.7), (6.0, 0.4, 3.73), tilt=0.01),
    ]
    faces = _faces(parts)
    assert [len(m) for m in faces.elements] == [1, 1, 1]

    for members in faces.elements[:2]:
        with pytest.raises(ValueError, match="flat top"):
            uphill([faces.parts[i] for i in members])

    # the cap falls toward +y, so the whole stack faces -y
    for members in faces.elements:
        assert np.allclose(rise(faces, members), [0.0, -1.0], atol=1e-3)


def test_one_dead_end_lift_does_not_cost_the_wall_its_direction():
    """A parapet over part of a panel and a plinth over the rest is ordinary,
    and the parapet still names the sides. Found by review 2026-08-19: the
    recursive call was unguarded, so a `ValueError` from the flat branch came
    out of the loop and the wall got no direction at all, despite the sloped
    branch having one. The area weighting the docstring promised never ran.
    """
    from build import rise

    parts = [
        _lift("Wall", (0, 0, 0), (6.0, 0.4, 3.0)),
        _lift("Cap", (0, 0, 3.0), (4.0, 0.4, 3.03), tilt=0.01),  # sloped
        _lift("Stub", (4.5, 0, 3.0), (6.0, 0.4, 3.3)),  # flat, and stays flat
    ]
    faces = _faces(parts)
    named = {faces.parts[m[0]].metadata["object"]: m for m in faces.elements}
    assert len(_next_lift_names(faces, named["Wall"])) == 2  # both are lifts

    assert np.allclose(rise(faces, named["Wall"]), [0.0, -1.0], atol=1e-3)

    # but a wall with nothing but dead ends above it still raises
    bare = [parts[0], parts[2]]
    faces = _faces(bare)
    named = {faces.parts[m[0]].metadata["object"]: m for m in faces.elements}
    with pytest.raises(ValueError, match="'Wall' has no high side"):
        rise(faces, named["Wall"])


def _next_lift_names(faces, members):
    from build import _next_lift

    return [
        faces.parts[m[0]].metadata["object"]
        for m in _next_lift(faces.parts, faces.elements, members)
    ]


def test_a_lift_must_be_flush_on_both_sides_not_merely_bear_on_the_top():
    """What keeps a roof deck, and a neighbour's cap, out of the answer.

    Both rest on the wall's top. The deck is set in from every wall face, so it
    is flush with none. The neighbour's cap runs over the wall's *end* and is
    flush with the building's outer plane there — one of the wall's two faces,
    but only one — which is why the test is the opposed pair rather than any
    single plane. Weighting the strays down by area instead leaves the answer
    tilted by a few degrees and dependent on how long the wall happens to be.
    """
    from build import rise

    wall = _lift("Wall", (0, 0, 0), (6.0, 0.4, 3.0))
    cap = _lift("Cap", (0, 0, 3.0), (6.0, 0.4, 3.03), tilt=0.01)
    deck = _lift("Deck", (0.2, 0.3, 3.0), (5.8, 4.0, 3.2))
    # a return wall's cap, crossing the end of this wall and flush at y = 0
    stray = _lift("Stray", (5.6, 0, 3.0), (6.0, 4.0, 3.03), tilt=0.01)

    parts = [wall, cap, deck, stray]
    faces = _faces(parts)
    named = {
        faces.parts[m[0]].metadata["object"]: m for m in faces.elements
    }
    assert _next_lift_names(faces, named["Wall"]) == ["Cap"]

    # and with only the strays present there is no direction to be had, which
    # raises naming the element rather than averaging two unrelated slopes
    faces = _faces([wall, deck, stray])
    named = {faces.parts[m[0]].metadata["object"]: m for m in faces.elements}
    with pytest.raises(ValueError, match="'Wall' has no high side"):
        rise(faces, named["Wall"])


def _facing_wall(x0, x1, y0, y1, high, low):
    """A wall whose top falls from `high` at x0 to `low` at x1, so it faces -X."""
    return substrate.polyhedron(
        [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
         (x0, y0, high), (x1, y0, low), (x1, y1, low), (x0, y1, high)],
        [[0, 3, 2, 1], [4, 5, 6, 7], [0, 4, 7, 3],
         [1, 2, 6, 5], [0, 1, 5, 4], [3, 7, 6, 2]],
    )


def test_a_facade_s_cladding_system_comes_from_the_part_not_its_position():
    """Two facades facing the same way, at different setbacks, clad differently.

    This is the street-front-versus-headhouse condition, which the real substrate
    cannot pose — it has no -X-facing facade at all. Neither a compass direction
    nor "the frontmost plane" separates these two: only the material does, and no
    property of a wall's shape implies brick.
    """
    from build import BRICK, FACADE, RAINSCREEN, check_facades, facades_of, uphill

    front = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)  # brick, at x = 0
    headhouse = _facing_wall(3.0, 3.4, 1.0, 4.0, 4.0, 3.99)  # rainscreen, set back
    front.metadata[FACADE] = BRICK
    headhouse.metadata[FACADE] = RAINSCREEN

    parts = [front, headhouse]
    body = trimesh.boolean.union(parts)
    faces = _faces(parts, body)

    # both walls face the same way, so direction cannot tell them apart
    assert np.allclose(uphill([front]), [-1.0, 0.0], atol=1e-3)
    assert np.allclose(uphill([headhouse]), [-1.0, 0.0], atol=1e-3)

    brick = facades_of(faces, BRICK, FALL)
    rainscreen = facades_of(faces, RAINSCREEN, FALL)
    assert brick.any() and rainscreen.any()
    assert not (brick & rainscreen).any()

    # the brick is the one at x = 0; the rainscreen the one set back at x = 3
    assert np.allclose(body.vertices[body.faces[brick]][:, :, 0], 0.0, atol=1e-6)
    assert np.allclose(body.vertices[body.faces[rainscreen]][:, :, 0], 3.0, atol=1e-6)

    # together they claim every facade, and the check agrees
    check_facades(faces, FALL, systems=(BRICK, RAINSCREEN))


def test_a_cornice_is_stamped_whether_or_not_there_is_an_element_to_join():
    """Being a cornice, and finishing a wall, are facts about the geometry.

    Whether there is an element to join is a fact about how the substrate was
    authored: `substrate.polyhedron` stamps no `"object"`, so gating the stamps
    on one switched both off for every transcribed substrate and every fixture
    here — `cladding_faces` would have wrapped the cornice instead of stopping
    below it. Found on review, 2026-08-26.
    """
    from build import CORNICE, TOP_CORNICE, group_cornices

    def band(x0, x1, z0, z1):
        return substrate.polyhedron(
            [(x0, 0, z0), (x1, 0, z0), (x1, 4, z0), (x0, 4, z0),
             (x0, 0, z1), (x1, 0, z1), (x1, 4, z1), (x0, 4, z1)],
            [[0, 3, 2, 1], [4, 5, 6, 7], [0, 4, 7, 3],
             [1, 2, 6, 5], [0, 1, 5, 4], [3, 7, 6, 2]],
        )

    wall, cornice = band(0.0, 0.4, 0.0, 3.0), band(-0.17, 0.0, 2.93, 3.0)
    group_cornices([wall, cornice])
    assert cornice.metadata[CORNICE] is True
    # the stamp is the direction the band stands proud in, not merely the fact
    # of one: the masonry is the face it overhangs and not the wall's ends
    assert wall.metadata[TOP_CORNICE] == (-1.0, 0.0, 0.0)
    assert "object" not in cornice.metadata  # ...and nothing was regrouped

    # a band that does not reach the top is the scupper kind: a cornice, but not
    # one that finishes the wall
    wall, low = band(0.0, 0.4, 0.0, 3.0), band(-0.17, 0.0, 1.5, 1.57)
    group_cornices([wall, low])
    assert low.metadata[CORNICE] is True
    assert TOP_CORNICE not in wall.metadata


def _stacked_box(x0, x1, y0, y1, z0, z1, ztop=None):
    """A box, optionally sloped on top so `uphill` can read a fall off it."""
    high = z1 if ztop is None else ztop
    return substrate.polyhedron(
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, high), (x1, y1, high), (x0, y1, z1)],
        [[0, 3, 2, 1], [4, 5, 6, 7], [0, 4, 7, 3],
         [1, 2, 6, 5], [0, 1, 5, 4], [3, 7, 6, 2]],
    )


def test_the_masonry_runs_the_whole_face_below_a_cornice_not_one_lift():
    """A wall is built in lifts and a cornice only touches the topmost one.

    Claiming the host body alone leaves the panel below it rainscreen on the
    *same facade plane*, and that is not an under-claim, it breaks the build:
    one plane is then asked to move 0.085 and 0.150 at the same vertex and
    `_vertex_planes` refuses. So the face the cornice overhangs is grown along
    the surface, contiguously, the way `_opening` grows a cheek. Found on
    review, 2026-08-26 — the live bake cannot pose it, because its wall is one
    lift and its cap plate is coplanar with the cornice rather than the wall.
    """
    from build import (
        FACADE, RAINSCREEN, TOP_CORNICE, classifier, cladding_faces, group_caps,
        group_cornices, masonry_faces, skins, _owner, _skin_from,
    )
    from skin import parameters, substrate
    from skin.offset import Faces

    params = parameters.load_validated()
    panel = _stacked_box(0.0, 0.4, 0.0, 6.0, 0.0, 3.0)
    parapet = _stacked_box(0.0, 0.4, 0.0, 6.0, 3.0, 4.0, ztop=3.97)
    cornice = _stacked_box(-0.17, 0.0, 0.0, 6.0, 3.9, 4.0)
    parts = [panel, parapet, cornice]
    for part, name in zip(parts, ("panel", "parapet", "cornice")):
        part.metadata[FACADE] = RAINSCREEN
        part.metadata["name"] = name

    group_cornices(parts)
    group_caps(parts, classifier(params))
    # the cornice touches the parapet and nothing else
    assert parapet.metadata[TOP_CORNICE] == (-1.0, 0.0, 0.0)
    assert TOP_CORNICE not in panel.metadata

    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    masonry = masonry_faces(faces, params["fall"])
    owners = {parts[o].metadata["name"] for o in faces.owner[masonry]}
    assert owners == {"panel", "parapet"}, "the masonry stopped at the lift"
    assert not (masonry & cladding_faces(faces, params["fall"])).any()

    # ...and it builds, which is the point: one plane, one offset
    for spec in skins(params):
        skin = _skin_from(spec, parts)
        assert skin.metadata["offset_residual"] < 1e-9
    masonry_skin = _skin_from(
        next(s for s in skins(params) if s["name"] == "Masonry"), parts
    )
    # the whole facade, ground to cornice underside, at the masonry allowance
    assert np.abs(masonry_skin.vertices[:, 0] + 0.15).max() < 1e-6
    assert masonry_skin.vertices[:, 2].min() == pytest.approx(0.0, abs=1e-6)
    assert masonry_skin.vertices[:, 2].max() == pytest.approx(3.9 - 0.15, abs=1e-6)


def test_a_wall_corniced_on_two_faces_is_refused():
    """Two masonry elevations on one wall, and one stamp cannot name both.

    Assigning in a loop kept whichever cornice came last and left the other
    face rainscreen with no warning — found on review, 2026-08-26.
    """
    from build import TOP_CORNICE, group_cornices

    wall = _stacked_box(0.0, 0.4, 0.0, 6.0, 0.0, 3.0)
    front = _stacked_box(-0.17, 0.0, 0.0, 6.0, 2.93, 3.0)
    back = _stacked_box(0.4, 0.57, 0.0, 6.0, 2.93, 3.0)
    with pytest.raises(ValueError, match="two masonry elevations on one wall"):
        group_cornices([wall, front, back])

    group_cornices([wall, front])  # ...one of them alone is fine
    assert wall.metadata[TOP_CORNICE] == (-1.0, 0.0, 0.0)


def test_two_masonry_systems_on_one_substrate_are_refused():
    """One masonry skin is one allowance. The student-house has two corniced
    walls — brick and the firewall's block — and `masonry_faces` selects on the
    cornice alone, so both would land in one skin at one offset while
    `check_facades` kept passing, neither tag being wrong. Name the condition
    that makes the cornice insufficient rather than meet it as geometry."""
    from build import BRICK, FACADE, RAINSCREEN, TOP_CORNICE, check_cladding

    one = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)
    two = _facing_wall(3.0, 3.4, 1.0, 4.0, 4.0, 3.99)
    for part, system in ((one, BRICK), (two, RAINSCREEN)):
        part.metadata[FACADE] = system
        part.metadata[TOP_CORNICE] = (-1.0, 0.0, 0.0)

    parts = [one, two]
    with pytest.raises(ValueError, match="one masonry skin is one allowance"):
        check_cladding(_faces(parts), FALL)

    two.metadata[FACADE] = BRICK  # ...one system, and it builds
    check_cladding(_faces(parts), FALL)


def test_a_facade_no_cladding_skin_covers_is_refused():
    """`check_facades` asks the authored tag; `check_cladding` asks the skins.

    They are different claims and the fixture above is why they had to split: a
    facade tagged for a declared system is legitimately claimed at the tag while
    being covered by no skin at all, which is the brick-skin open item in
    miniature. The masonry set is *derived* rather than tagged, so nothing at
    the tag level can notice a carve-out that drops a facade or claims one
    twice.

    Stamping the wall the way `group_cornices` stamps one a cornice finishes is
    what puts it back in a skin — the same fixture, read by the other check.
    """
    from build import BRICK, FACADE, TOP_CORNICE, check_cladding, check_facades

    front = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)
    front.metadata[FACADE] = BRICK
    parts = [front]
    faces = _faces(parts)

    # the tag is happy: brick is a declared system and this wall carries it
    check_facades(faces, FALL, systems=(BRICK,))
    # the skins are not: no rule set in RULES claims a brick-tagged facade
    with pytest.raises(ValueError, match="claimed by neither cladding skin"):
        check_cladding(faces, FALL)

    front.metadata[TOP_CORNICE] = (-1.0, 0.0, 0.0)
    check_cladding(_faces(parts), FALL)  # ...now the masonry skin covers it


def test_an_unclaimed_facade_is_refused():
    """A facade no cladding system claims is a silently bare wall. Fail instead."""
    from build import BRICK, FACADE, RAINSCREEN, check_facades

    front = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)
    front.metadata[FACADE] = BRICK  # but only rainscreen is declared below
    parts = [front]
    faces = _faces(parts)

    with pytest.raises(ValueError, match="claimed by no cladding system"):
        check_facades(faces, FALL, systems=(RAINSCREEN,))


def test_build_does_not_emit_the_substrate_unless_asked():
    """The module reads the substrate and never writes it.

    Where the substrate is live geometry — Bonsai IFC parts carrying semantic
    data — emitting it would put a second, dead copy of every part into the
    scene beside the original. Opting in has to be deliberate.
    """
    import build as build_module
    from build import build, current_substrate, skins

    parts = current_substrate()
    before = [(p.vertices.copy(), p.faces.copy()) for p in parts]

    manifest = build(parts)
    roles = {e["name"]: e["role"] for e in manifest}
    # every skin the rig poses, which is not every skin authored: the masonry
    # needs a wall a cornice finishes and the rig has no cornice. `build` skips
    # it and says so -- see `build.covered`
    assert set(roles) == {"Membrane", "Cladding"}
    assert {s["name"] for s in skins()} - set(roles) == {"Masonry"}
    assert set(roles.values()) == {"skin"}
    assert not list(build_module.BUILD_DIR.glob("Substrate_*.obj"))

    # a skin this run skipped must not leave last run's file in build/, holding
    # geometry offset from a different substrate. Found on review, 2026-08-26
    stale = build_module.BUILD_DIR / "Masonry.obj"
    stale.write_text("# left by an earlier bake that posed a cornice\n")
    build(parts)
    assert not stale.exists()

    opted_in = build(parts, emit_substrate=True)
    kinds = {e["role"] for e in opted_in}
    assert kinds == {"skin", "substrate"}
    assert sum(e["role"] == "substrate" for e in opted_in) == len(parts)

    # reading the substrate never alters it, either way
    for part, (verts, faces) in zip(parts, before):
        assert np.array_equal(part.vertices, verts)
        assert np.array_equal(part.faces, faces)


def test_export_writes_ngons_not_triangles(tmp_path):
    path = tmp_path / "cube.obj"
    write_obj(substrate.cube(2.0), path, "Cube")
    faces = [ln.split()[1:] for ln in open(path) if ln.startswith("f ")]
    assert len(faces) == 6 and all(len(f) == 4 for f in faces)  # quads, not 12 tris


def test_sloped_substrate_keeps_axis_planes_and_horizontals_exact():
    """A sloped top over a concave plan over-determines the offset; the error
    must land on the sloped planes, never on the axis-aligned ones."""
    import trimesh

    from build import current_substrate

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    skin = skin_over(parts, D)

    assert skin.is_watertight
    assert skin.metadata["offset_residual"] < 1e-9  # every hard constraint met
    assert skin.metadata["slope_deviation"] > 1e-4  # and the slopes did absorb it

    axis = np.abs(body.face_normals).max(axis=1) > 1 - 1e-6
    moved = (skin.vertices[skin.faces[axis]] * body.face_normals[axis][:, None]).sum(2)
    fixed = (body.vertices[body.faces[axis]] * body.face_normals[axis][:, None]).sum(2)
    assert np.allclose(moved - fixed, D, atol=1e-9)  # axis planes exactly offset

    sharp = body.face_adjacency_angles > 1e-6
    for a, b in body.face_adjacency_edges[sharp]:
        if abs(body.vertices[a][2] - body.vertices[b][2]) < 1e-6:
            assert abs(skin.vertices[a][2] - skin.vertices[b][2]) < 1e-9


def test_partial_skin_is_an_open_surface_with_constraints_intact():
    import trimesh

    from build import current_substrate, skins

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    membrane = skins()[0]
    surface = skin_over(parts, D, keep=membrane["keep"],
                        classify=membrane["classify"])

    assert not surface.is_watertight  # a surface, not a solid
    border = trimesh.grouping.group_rows(surface.edges_sorted, require_count=1)
    assert len(border) and len(set(surface.edges_sorted[border].ravel())) == len(border)

    kept = membrane["keep"](_faces(parts, body))
    assert kept.sum() < len(kept)  # something is left bare
    assert surface.faces.shape[0] == kept.sum()

    # the vertical faces it does cover are still offset exactly
    for n in np.unique(np.round(surface.face_normals, 4), axis=0):
        if abs(n[2]) > 1e-3:
            continue
        a = (surface.vertices[surface.faces[np.abs(surface.face_normals - n).max(1) < 1e-3]] @ n).min()
        b = (body.vertices[body.faces[np.abs(body.face_normals - n).max(1) < 1e-3]] @ n).min()
        assert np.isclose(a - b, D, atol=1e-9)


def test_a_drip_hangs_the_right_walls_to_the_right_depth():
    """The membrane's drip is derived, not elected.

    There is no `turn_down` predicate any more: `_lap` finds the wall under a
    covered top by adjacency and reads the direction off it. This checks the
    result is what the old election produced -- the facades of the two walls the
    roof runs into, and nothing else -- and that the depth is still measured
    from the *substrate* edge rather than from the skin above it.
    """
    import trimesh

    from build import current_substrate, skins, wall_faces
    from skin.offset import _owner, _receivers

    membrane = skins()[0]
    drop = membrane["drop"]
    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    owner = _owner(body, parts)
    faces = _faces(parts, body)

    kept = membrane["keep"](faces)
    walls = _receivers(body, kept, membrane["lap"](faces))
    height = np.abs(body.face_normals[:, 2])
    # the drips: a wall face carrying a covered top directly above it
    tops = kept & (height > 1e-6)
    below = np.zeros(len(kept), dtype=bool)
    for (f, g), (a, b) in zip(body.face_adjacency, body.face_adjacency_edges):
        for near, far in ((f, g), (g, f)):
            if tops[near] and walls[far] and body.vertices[[a, b], 2].min() > 1.0:
                below[far] = True

    # parts 1 and 2 are the two whose interior face the roof runs into
    assert {0, 1} <= set(owner[below].tolist())
    exterior, interior = wall_faces(faces, FALL)
    assert (below & exterior).any() and not (below & interior).any()

    surface = skin_over(parts, D, keep=membrane["keep"], lap=membrane["lap"],
                        drop=drop, out=membrane["out"], classify=membrane["classify"])
    tops = {round(float(z), 6) for z in body.vertices[:, 2] if z > 1.5}
    hems = {round(float(z), 6) for z in surface.vertices[:, 2]} & {
        round(t - drop, 6) for t in tops
    }
    assert hems, "drip should sit exactly drop below a substrate top edge"

    # a near-level edge must be exactly level, drip included
    e = surface.vertices[surface.edges_unique]
    dz = np.abs(e[:, 0, 2] - e[:, 1, 2])
    assert dz[dz < 1e-3].max() < 1e-12


def test_cladding_and_membrane_cover_complementary_walls_and_never_meet():
    import trimesh

    from build import current_substrate, separation_check, skins

    parts = current_substrate()
    faces = _faces(parts)

    membrane, cladding = skins()[:2]
    # the membrane climbs the interior walls and laps down the exterior; the
    # cladding does the reverse. The membrane may lap onto any vertical face,
    # so the discriminating direction is the cladding's
    assert (membrane["keep"](faces) & cladding["lap"](faces)).any()
    assert not (cladding["keep"](faces) & cladding["lap"](faces)).any()

    gap, skins = separation_check(parts)
    assert len(skins) == 2, "the rig poses no masonry: it has no cornice"
    assert gap > 0.05, f"skins only {gap * 1000:.1f} mm apart"
    for skin in skins:
        assert not skin.is_watertight
        assert skin.metadata["offset_residual"] < 1e-9


def test_both_skins_cover_the_coping_and_stack_rather_than_collide():
    """A wall top the membrane carries over is claimed by the cladding too, and
    that double cover is intended — Duncan's call, 2026-08-16.

    It is what a real parapet is: a membrane upstand carried over the top, and a
    metal coping laid over that. The two alternatives were giving the top to one
    skin or the other; both were rejected, so neither `membrane_faces` nor
    `cladding_faces` should be narrowed to make the skins disjoint.

    What has to hold is not separation but **order**: the cladding coping sits
    outboard of the membrane's everywhere, by the difference of the two offsets.
    A coping is sloped, so it is a least-squares plane rather than a hard one and
    the gap is the offset difference only to within each skin's slope deviation
    — checked against the deviations the skins themselves report, not a constant.
    """
    from build import _upward, cladding_faces, current_substrate, membrane_faces, skins

    parts = current_substrate()
    faces = _faces(parts)
    membrane, cladding = skins()[:2]

    shared = membrane["keep"](faces) & cladding["keep"](faces)
    assert shared.any(), "the coping should be claimed by both skins"

    # and only the coping: a facade or a roof face in here would be two skins
    # covering the same surface for no reason, which is not what was decided
    tops = _upward(faces.normals) & faces.of_role(substrate.WALL)
    assert not (shared & ~tops).any()
    assert (shared & _sloped(faces.normals)).sum() == shared.sum()

    patches = [
        skin_over(parts, spec["distance"], keep=lambda f: shared,
                  classify=spec["classify"])
        for spec in (membrane, cladding)
    ]
    inner, outer = patches
    assert len(inner.faces) == len(outer.faces) == shared.sum()

    # plane offset of each patch face along its own normal: the cladding's must
    # be the further out, by distance difference +/- what the slopes absorbed
    def carried(patch):
        return (patch.triangles.mean(axis=1) * patch.face_normals).sum(axis=1)

    gap = carried(outer) - carried(inner)
    expected = cladding["distance"] - membrane["distance"]
    slack = sum(p.metadata["slope_deviation"] for p in patches)
    assert gap.min() > 0, "the cladding coping must sit outboard of the membrane's"
    assert np.abs(gap - expected).max() <= slack, (
        f"coping gap {gap.min():.6f}..{gap.max():.6f} m is not {expected} m "
        f"to within the {slack:.6f} m the sloped planes absorbed"
    )


def _sloped(normals):
    """Neither vertical nor horizontal — the planes the solve leaves soft."""
    return (np.abs(normals[:, 2]) > 1e-6) & (np.abs(normals[:, 2]) < 1 - 1e-6)


def test_the_cladding_is_cut_at_its_datum_rather_than_clamped_to_it():
    """The cladding stops at ground level — Duncan's call, 2026-08-16.

    Untrimmed it mitres with the substrate's unskinned underside and hangs
    `distance` below it, which is what every skin edge does against an unskinned
    neighbour. `base: 0.0` cuts that off.

    The point of the test is *how* it stops. A clamp — pushing the low vertices
    up to the datum — would give the same silhouette while tilting the bottom of
    every sloped panel off its offset plane, and the residual would not notice
    because the solve has already run. So the assertions are that the surviving
    geometry is untouched and its planes are unmoved, not merely that nothing is
    below zero.
    """
    from build import _skin_from, current_substrate, skins

    parts = current_substrate()
    cladding = skins()[1]
    assert cladding["base"] == 0.0

    whole = dict(cladding, base=None)
    untrimmed = _skin_from(whole, parts)
    trimmed = _skin_from(cladding, parts)

    # the control: without the trim it really does hang below, by the offset
    assert np.isclose(untrimmed.vertices[:, 2].min(), -cladding["distance"], atol=1e-6)

    z = trimmed.vertices[:, 2]
    assert z.min() == 0.0, "the datum is a coordinate, not a tolerance"
    assert (z == 0.0).sum() >= 4, "the cut should leave an edge lying on the datum"

    # every vertex that survived is exactly where the offset put it
    survivors = untrimmed.vertices[untrimmed.vertices[:, 2] > 1e-9]
    moved = [np.abs(trimmed.vertices - v).max(axis=1).min() for v in survivors]
    assert max(moved) == 0.0

    # and every remaining face is still on a plane the offset produced
    def planes(mesh):
        carried = (mesh.triangles.mean(axis=1) * mesh.face_normals).sum(axis=1)
        return np.column_stack([mesh.face_normals, carried])

    apart = np.abs(planes(trimmed)[:, None] - planes(untrimmed)[None]).max(axis=2)
    assert apart.min(axis=1).max() < 1e-9

    # the cut must not crack: the two triangles sharing a crossed edge have to
    # land on one vertex, not on two that agree to nine places
    datum = trimmed.vertices[z == 0.0]
    assert len(np.unique(np.round(datum, 9), axis=0)) == len(datum)
    assert trimmed.area_faces.min() > 1e-9, "no zero-area slivers shed by the cut"

    assert trimmed.metadata["offset_residual"] == untrimmed.metadata["offset_residual"]
    assert clearance(parts, trimmed) > cladding["distance"] - 0.007


def test_a_cut_vertex_never_lands_outside_the_edge_it_cut():
    """The cut classifies against the datum exactly, with no tolerance band.

    A band reads well and is wrong: `crossing` interpolates to exactly z = base,
    so a vertex inside the band but *below* the plane would be called above, and
    the interpolation — solving for a plane that vertex is already past — runs
    its parameter negative and puts the cut vertex outside the edge. This is the
    case that produced a 333 mm triangle out of a 1 mm one.
    """
    from skin.offset import _trim_below

    verts = [np.array(v) for v in ([0, 0, -5e-7], [1.0, 0, -2e-6], [0, 1.0, -2e-6])]
    with pytest.raises(ValueError, match="base"):
        _trim_below(verts, [[0, 1, 2]], 0.0)  # wholly below: nothing survives
    assert len(verts) == 3, "and no cut vertex was invented on the way"

    # the ordinary straddle still cuts where it should, exactly halfway here
    verts = [np.array(v) for v in ([0, 0, -1.0], [1.0, 0, 1.0], [0, 1.0, 1.0])]
    _trim_below(verts, [[0, 1, 2]], 0.0)
    cut = np.array(verts[3:])
    assert np.allclose(cut, [[0.5, 0, 0], [0, 0.5, 0]], atol=0)


def test_a_datum_above_the_whole_skin_is_refused_at_the_seam():
    """Authoring `base` in the wrong datum — site elevation for building-local —
    trims everything away. Before this raised, the empty mesh reached trimesh and
    came back as `IndexError: too many indices`, which names nothing."""
    from build import _skin_from, current_substrate, skins

    parts = current_substrate()
    with pytest.raises(ValueError, match=r"base=100.0 leaves nothing"):
        _skin_from(dict(skins()[1], base=100.0), parts)


def test_a_skin_with_no_datum_is_not_trimmed():
    """`base: null` is not `base: 0.0`. The membrane authors null — it never
    reaches the ground — and the two must not be the same code path, or a skin
    that legitimately goes below zero would be silently cut."""
    from build import _skin_from, current_substrate, skins

    parts = current_substrate()
    membrane = skins()[0]
    assert membrane["base"] is None

    low = _skin_from(dict(membrane, base=1.5), parts)
    # 0.959, not the 1.090 this read before 2026-08-21: the turn-out against
    # part 4 now folds round the corner onto the wall beside it — the fold's
    # probe used to start `distance` short of the arris and read the void past
    # the corner as no room — and that band then runs on 205 mm down the wall
    assert np.isclose(_skin_from(membrane, parts).vertices[:, 2].min(), 0.959, atol=1e-3)
    assert low.vertices[:, 2].min() == 1.5  # the same skin, cut where told


def test_opposed_normals_are_compared_as_unit_vectors():
    """`_vertex_normals` quantises to the PLANE_TOL lattice, so a sloped normal
    comes back a hair short of unit length and an exactly antiparallel pair dots
    to -|n|^2 rather than -1. Comparing that raw against `-1 + PLANE_TOL` missed
    3.65% of genuine contradictions over 20 000 random sloped normals — found by
    review 2026-08-19.

    An undetected contradiction is the worst kind: `_reconcile` never runs, no
    fold is reported, and the solve quietly splits the difference. Axis-aligned
    normals were never affected, which is why every fold met so far was one.
    """
    from skin.offset import PLANE_TOL, _opposed

    rng = np.random.default_rng(0)
    normals = rng.normal(size=(4000, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    # only sloped ones: near-axis normals are snapped to exact units upstream
    normals = normals[np.abs(normals).max(axis=1) < 1 - 1e-6]
    quantised = np.round(normals / PLANE_TOL) * PLANE_TOL
    assert np.abs((quantised * quantised).sum(axis=1) - 1).max() > PLANE_TOL

    for n in quantised:
        assert _opposed(np.array([n, -n])) is not None

    # and a pair that merely diverges is still not a contradiction
    apart = np.array([[0.0, 0.0, 1.0], [0.0, 0.6, -0.8]])
    assert _opposed(apart) is None


def test_a_lap_stops_at_the_faces_it_reaches_not_at_their_plane():
    """A wall's outer face and the parapet's above it are the *same plane*.

    A building shares a plane right up a stack, so anything that matched a
    continuation on the plane alone would reach every coplanar surface in the
    model. On the Unit8 bake that turned the membrane's parapet skirt out 205 mm
    into thin air 1.5 m above the roof whose flange elected it, and put 35
    crossings through the cladding.

    `_receivers` now settles it structurally rather than by a region test: a lap
    only ever turns onto a face **adjacent to one the skin covers**, so the lift
    above is not a candidate at all. This poses the condition in miniature --
    two lifts of one wall presenting the same plane, with a covered panel over
    only the lower one.
    """
    from skin.offset import _receivers

    lower = trimesh.creation.box(extents=[1, 1, 1], transform=trimesh.transformations.
                                 translation_matrix([0.5, 0.5, 0.5]))
    upper = trimesh.creation.box(extents=[1, 1, 1], transform=trimesh.transformations.
                                 translation_matrix([0.5, 0.5, 1.7]))
    body = trimesh.util.concatenate([lower, upper])
    outer = np.abs(body.face_normals @ [-1, 0, 0] - 1) < 1e-9
    assert outer.sum() == 4, "two lifts, both presenting a face on x = 0"

    # the lower lift's top is covered; nothing else is
    kept = (np.abs(body.face_normals @ [0, 0, 1] - 1) < 1e-9) & (
        body.triangles[:, :, 2].min(axis=1) > 1.0 - 1e-9
    ) & (body.triangles[:, :, 2].max(axis=1) < 1.0 + 1e-9)
    assert kept.sum() == 2, "one lift top covered"

    vertical = np.abs(body.face_normals[:, 2]) < 1e-9
    reached = _receivers(body, kept, vertical)
    assert reached.sum(), "the lower lift's own faces are lapped onto"
    z = body.triangles[reached][:, :, 2]
    assert z.max() <= 1.0 + 1e-9, (
        f"a lap reached up to z {z.max():.3f}: it followed the plane onto the "
        "lift above instead of stopping at the faces it touches"
    )


def test_a_cornice_joins_the_wall_it_projects_from():
    """A projecting band is the wall it hangs on, not a slab of its own.

    `Cornice-Unit8-E` reads `ROOF` at horizontality 0.704 and the 400 mm scupper
    drip reads 0.533 — dead on the halfway mark, where `classify` refuses and the
    build stops. Both are the wall. The relation has to hold off two look-alikes:
    a cap plate rests on the top rather than standing proud of the face, and a
    neighbouring parapet butting a taller wall is outside its footprint and
    shorter than it, but stands metres proud of a 420 mm wall.
    """
    from build import CORNICE, group_cornices

    def box(name, extents, centre):
        part = substrate._box(extents, centre)
        part.metadata.update(name=name, object=name)
        return part

    wall = box("Wall", [0.42, 6.0, 0.72], [0.21, 3.0, 12.71])          # x 0..0.42, top 13.07
    cornice = box("Cornice", [0.17, 6.0, 0.07], [-0.085, 3.0, 13.035])  # proud of the face
    cap = box("Cap", [0.59, 6.0, 0.03], [0.085, 3.0, 13.085])          # rests on the top
    # butts the wall's end, inside its height and shorter than it: excluded only
    # because it stands 6 m proud of a 420 mm wall
    other = box("Neighbour", [0.42, 6.0, 0.60], [0.21, 9.0, 12.65])

    group_cornices(parts := [wall, cornice, cap, other])
    stamped = [p.metadata["name"] for p in parts if p.metadata.get(CORNICE)]
    assert stamped == ["Cornice"], f"cornices identified: {stamped}"
    assert cornice.metadata["object"] == "Wall", "joined to the wall it projects from"
    assert cap.metadata["object"] == "Cap", "a cap rests on the top; group_caps has it"
    assert other.metadata["object"] == "Neighbour", (
        "a wall butting another's end is outside its footprint and shorter than it, "
        "but stands proud of it by far more than its thickness — not a cornice"
    )

    group_cornices(parts)  # idempotent: a substrate already grouped is untouched
    assert [p.metadata["name"] for p in parts if p.metadata.get(CORNICE)] == ["Cornice"]


def _slotted_wall():
    """One wall body with a slot cut down through it, like a scupper.

    A single body, not three abutting ones: a slot is *cut into* a parapet, so
    its two cheeks belong to the same part, and `_opening` reads them per body
    for the reasons its docstring gives. Every face is axis-aligned, so every
    lap direction is exact.
    """
    wall = substrate.prism((0.0, 0.0, 0.0), (2.4, 0.4, 1.0))
    slot = substrate.prism((1.0, -0.1, 0.8), (1.4, 0.5, 1.5))
    notched = trimesh.boolean.difference([wall, slot])
    notched.vertices = substrate.snapped(notched.vertices)
    return [notched]


def test_a_lap_wraps_the_cheeks_of_a_slot_the_old_election_could_not_see():
    """The scupper, in miniature.

    A slot's cheeks lie *across* the wall's fall, so `wall_faces` calls them
    ends and neither the skirt nor the flange predicate could ever claim one --
    which is why the membrane stopped dead at the scupper cheeks and left them
    bare. `_lap` asks the substrate instead: the covered sill runs into the
    cheek, so the surface turns and goes up it, and the covered top runs into it
    from above, so it comes down. Nothing elects anything.
    """
    parts = _slotted_wall()
    d, drop, out = 0.01, 0.06, 0.2

    skin = skin_over(
        parts, d,
        keep=lambda faces: faces.normals[:, 2] > 1e-6,
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=drop, out=out,
    )

    for x, sign in ((1.0, +1), (1.4, -1)):
        plane = x + sign * d
        on = np.abs(skin.triangles[:, :, 0] - plane).max(axis=1) < 1e-6
        assert on.any(), f"nothing on the cheek at x = {plane}"
        z = skin.triangles[on][:, :, 2]
        # up `out` from the sill at 0.8, and down `drop` from the top at 1.0,
        # which between them cover the whole 0.2 m cheek
        assert z.min() <= 0.8 + d + 1e-6
        assert z.max() >= 1.0 - drop - 1e-6

    assert clearance(parts, skin) > d - 1e-6, "a cheek lap folded into the wall"


def test_a_lap_runs_on_where_the_wall_it_hangs_from_butts_in_line():
    """The junction at `Parapet-Unit8-N`'s east end, in miniature.

    A low wall butts a tall one **in line**: both present the same face, so the
    surface simply continues past the join. There is no arris to turn round, and
    a lap that stopped at the end of the thing it hangs from would leave the
    open edge the membrane leaked through. It runs on instead.
    """
    low = substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 1.0))
    tall = substrate.prism((1.0, 0.0, 0.0), (2.0, 0.4, 2.0))
    parts = [low, tall]
    d, drop, out = 0.01, 0.06, 0.2

    # only the low wall's top is covered, so its drip runs out at x = 1.0
    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6)
        & (faces.centres[:, 2] < 1.5),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=drop, out=out,
    )

    on = np.abs(skin.triangles[:, :, 1] - (0.0 - d)).max(axis=1) < 1e-6
    assert on.any(), "no drip on the front face"
    reach = skin.triangles[on][:, :, 0].max()
    assert reach == pytest.approx(1.0 - d + out, abs=1e-6), (
        f"the drip stopped at x = {reach:.4f}: it ended where the wall it hangs "
        "from ends instead of running on across the wall that continues it"
    )
    assert clearance(parts, skin) > d - 1e-6


def test_an_in_line_butt_runs_on_the_same_way_at_both_ends():
    """A run-on moves the seam it lengthens, so anything read off the runs before
    it fires is stale — the *other* end of that same run included.

    Caught by `/code-review high` 2026-08-20. Held over a whole pass, the second
    end read the first end's vertex as its own, `tip == root` blocked it, and a
    substrate symmetric about its own centre came out lapped on one side only.
    """
    low = substrate.prism((1.0, 0.0, 0.0), (2.0, 0.4, 1.0))
    parts = [
        low,
        substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 2.0)),
        substrate.prism((2.0, 0.0, 0.0), (3.0, 0.4, 2.0)),
    ]
    d, out = 0.01, 0.2
    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6) & (faces.centres[:, 2] < 1.5),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=0.06, out=out,
    )
    on = np.abs(skin.triangles[:, :, 1] - (0.0 - d)).max(axis=1) < 1e-6
    x = skin.triangles[on][:, :, 0]
    west, east = float(x.min()), float(x.max())
    assert (1.0 + d) - west == pytest.approx(east - (2.0 - d), abs=1e-6), (
        f"ran on to x {west:.4f} at one end and {east:.4f} at the other, on a "
        "substrate symmetric about x = 1.5"
    )


def test_a_run_on_is_priced_as_an_upstand_whichever_way_the_seam_rakes():
    """Duncan, 2026-08-21: *"F39 does not extend as far east as before (.062 east
    of V48 — should be .205)."*

    A run-on runs **sideways**, along the surface, so it is an upstand's `out`
    and never a drip's `drop`. It used to be priced by `reach` — which answers
    "which way does this lap leave its arris" — applied to the direction of the
    *run*, and a seam raking down a coping laid to fall therefore read as a drip
    at one end and an upstand at the other, purely because the two ends face
    opposite ways along the same fall. Measured on this fixture before the fix:
    199 mm west, 60 mm east, off one straight arris.

    So the assertion is symmetry in plan. The wedge's top slopes, but its two
    ends sit at x = 1 and x = 2 against identical neighbours, and a run-on of the
    same length along the seam projects to the same length in x at each end.
    """
    top = substrate.polyhedron(
        [(1, 0, 0), (2, 0, 0), (2, 0.4, 0), (1, 0.4, 0),
         (1, 0, 1.0), (2, 0, 0.9), (2, 0.4, 0.9), (1, 0.4, 1.0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    parts = [
        top,
        substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 2.0)),
        substrate.prism((2.0, 0.0, 0.0), (3.0, 0.4, 2.0)),
    ]
    d = 0.01
    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6) & (faces.centres[:, 2] < 1.5),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=0.06, out=0.2,
    )
    on = np.abs(skin.triangles[:, :, 1] - (0.0 - d)).max(axis=1) < 1e-6
    x = skin.triangles[on][:, :, 0]
    west, east = float(x.min()), float(x.max())
    assert west < 1.0 - d and east > 2.0 + d, "neither end ran on at all"
    assert (1.5 - west) == pytest.approx(east - 1.5, abs=1e-6), (
        f"ran on to x {west:.4f} at one end and {east:.4f} at the other, off one "
        "straight arris on a substrate symmetric in plan about x = 1.5"
    )


def test_room_reads_every_triangle_holding_the_probe_not_the_first():
    """`_room` marches, and a lap always starts on an arris, so its probe sits on
    a shared edge or a shared corner every single time. Two or three coplanar
    triangles hold it and only some of them carry the ray onward — a triangle
    that merely *corners* on the probe exits at once and reports no room at all.

    Reading the first such triangle in index order made the answer depend on how
    manifold3d happened to triangulate the face. These two are transcribed from
    the shipping bake's east facade at the cornice's south end, where it bit:
    marching south the corner triangle comes first and says 0, and the same
    detail mirrored at the cornice's *north* end had the carrying triangle first
    and ran the full 205 mm. That is Duncan's *"F34 is missing on the south side
    of the scupper. The scupper is symmetrical."*

    A made-up pair will not reproduce it. `_inside` admits the corner triangle
    only within `PLANE_TOL` — the probe is 9.6e-7 outside its edge — and a
    triangle that genuinely contained the probe would carry the ray too.
    """
    from skin.offset import _room

    corners_on_it = [
        [8.079999971389771, 5.185000052452087, 14.49500005340576],
        [8.079999971389771, 7.119999995231628, 14.717999983787536],
        [8.079999971389771, 5.284999957084655, 14.49500005340576],
    ]
    carries_the_ray = [
        [8.079999971389771, 5.284999957084655, 14.425000000953673],
        [8.079999971389771, 5.284999957084655, 14.49500005340576],
        [8.079999971389771, 7.119999995231628, 14.717999983787536],
    ]
    here = np.array([8.079999971389771, 5.284999957084655, 14.49500005340576])
    facing = np.array([-1.0, 0.0, 0.0])
    south = np.array([0.0, 1.0, 0.0])

    for label, order in (("corner first", 0), ("carrier first", 1)):
        pair = [corners_on_it, carries_the_ray][:: 1 if order == 0 else -1]
        body = trimesh.Trimesh(
            vertices=np.array(pair).reshape(-1, 3),
            faces=np.arange(6).reshape(2, 3),
            process=False,
        )
        assert _room(body, here, south, [0, 1], facing, 0.205) == pytest.approx(
            0.205
        ), f"{label}: the march stopped on a triangle that only corners on it"


def test_a_lap_folds_round_a_convex_corner_it_reaches():
    """Duncan, 2026-08-21: *"F28 does not wrap the corner like before."*

    A low wall runs into a tall one and the lap turns up its face; that face ends
    at the building corner, and the lap folds round onto the return. The check
    that the fold lands on substrate marches from the seam, and the seam lies on
    the offset of the face the lap is *leaving* as well as of the face it is
    turning onto — so it sits `distance` off the arris. Past it at a concave
    corner, which is harmless; short of it at a convex one, where the march
    starts out over the void beyond the corner and reports no room at all. No
    fold was ever placed at a convex corner before this was fixed.

    `drop` is zero here so that the only bands in the skin are the ones this
    tests: with a drip the low wall's own face would carry one too.
    """
    low = substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 1.0))
    tall = substrate.prism((1.0, 0.0, 0.0), (2.0, 1.0, 2.0))
    parts = [low, tall]
    d, out = 0.01, 0.2

    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6)
        & (faces.centres[:, 2] < 1.5),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=0.0, out=out,
    )
    round_it = np.abs(skin.triangles[:, :, 1] - (0.0 - d)).max(axis=1) < 1e-6
    assert round_it.any(), (
        "the upstand stopped at the building corner instead of folding round "
        "onto the tall wall's return face"
    )
    reach = skin.triangles[round_it][:, :, 0].max()
    assert reach == pytest.approx(1.0 - d + out, abs=1e-6), (
        f"the fold ran to x = {reach:.4f} rather than {1.0 - d + out}"
    )
    assert clearance(parts, skin) > d - 1e-6


def test_wall_planes_are_not_snapped_onto_the_tolerance_lattice():
    """`_next_lift` matches one element's vertical planes against another's
    within `TOL`. Rounding both sides onto the `TOL` lattice first turns that
    into **exact equality of a rounded key**, which CLAUDE.md's Tolerances
    section forbids and which `_plane_ids` was rewritten to stop doing: two
    triangles of one face can land either side of a lattice boundary, `flush`
    then finds no shared plane, and `rise` raises `flat top` on a wall that
    plainly has a lift above it.

    Axis-aligned walls hide it, because their `d` is already a whole number of
    micrometres. A wall running diagonally in plan does not, which is what this
    pins. Found by `/code-review high` 2026-08-21; latent on all three
    substrates, every one of which is axis-aligned.
    """
    from build import TOL, _wall_planes

    wedge = substrate.polyhedron(
        [(0, 0, 0), (1, 0, 0), (0.4, 0.7, 0),
         (0, 0, 1), (1, 0, 1), (0.4, 0.7, 1)],
        [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)],
    )
    rows = _wall_planes([wedge])
    assert len(rows) == 3, "three vertical faces on a triangular prism"

    diagonal = rows[np.abs(np.abs(rows[:, :3]).max(axis=1) - 1.0) > 1e-9]
    assert len(diagonal), "the fixture has no plane that is off-axis in plan"
    off = np.abs(diagonal[:, 3] / TOL - np.round(diagonal[:, 3] / TOL))
    assert off.max() > 1e-6, (
        "a diagonal wall's offset came back exactly on the TOL lattice, so it "
        "was rounded: `_next_lift`'s tolerance match is exact equality again"
    )


def test_a_drip_with_no_vertical_face_to_miter_onto_raises():
    """`np.linalg.lstsq` on a zero-row system returns `[0, 0, 0]` rather than
    complaining, so `drip_at` used to hand back the **substrate** vertex where no
    face at it was a skinned vertical one — rooting the drip band on the solid
    instead of `distance` out from it.

    Measured on this fixture with the guard removed: it built, four faces,
    `offset_residual` 4.34e-17, and `clearance` **0.0000 mm** against an 8 mm
    offset. Nothing in the stack reports that, which is the silent-omission
    failure this module is written against. Found by `/code-review high`
    2026-08-21.

    Unreachable through either shipped `lap` predicate — both admit only
    vertical faces, and a drip's receiver is one of them — so the fixture leans
    a face over and laps onto that.
    """
    lean = substrate.polyhedron(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
         (0, 0, 1), (0.7, 0, 1), (0.7, 1, 1), (0, 1, 1)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    sloped = (np.abs(lean.face_normals[:, 2]) > 0.1) & (
        np.abs(lean.face_normals[:, 2]) < 0.9
    )
    assert sloped.any(), "the fixture has no leaning face to lap onto"

    with pytest.raises(ValueError, match=r"no skinned vertical face at vertex"):
        skin_over(
            [lean], 0.01,
            keep=lambda faces: faces.normals[:, 2] > 1 - 1e-6,
            lap=lambda faces: (np.abs(faces.normals[:, 2]) > 0.1)
            & (np.abs(faces.normals[:, 2]) < 0.9),
            drop=0.06, out=0.0,
        )


def test_a_knife_is_only_a_knife_where_the_two_faces_touch():
    """Coplanar and opposed is not enough — they have to share the vertex.

    Caught by `/code-review high` 2026-08-20, and it is the trap this file
    already records twice: a shared plane is not a shared face. Two walls metres
    apart can present one plane facing opposite ways, and pairing them would
    refuse a lap onto one because the skin happened to cover the other.
    """
    from skin.offset import _knives, _plane_ids

    here = substrate.prism((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    for name, other, touching in (
        ("butted", substrate.prism((1.0, 0.0, 0.0), (2.0, 1.0, 1.0)), True),
        ("2.6 m away", substrate.prism((1.0, 3.6, 0.0), (2.0, 4.6, 1.0)), False),
    ):
        body = trimesh.util.concatenate([here, other])
        body.merge_vertices()
        ids, reps = _plane_ids(body)
        assert bool(_knives(body, ids, reps)) is touching, name


def test_a_rule_set_may_decline_to_lap_at_all():
    """`lap: None` is a skin that genuinely stops where it ends, and it has to be
    reachable — the raise for a zero drop *and* a zero out used to recommend it
    while `skins()` would have crashed building it.
    """
    parts = _slotted_wall()
    skin = skin_over(
        parts, 0.01,
        keep=lambda faces: faces.normals[:, 2] > 1e-6,
        lap=None, drop=0.06, out=0.2,
    )
    assert len(skin.faces), "the covered faces are still skinned"
    assert np.abs(skin.face_normals[:, 2]).min() > 1e-6, "no vertical lap panels"


def test_a_rainscreen_stops_at_an_opening_rather_than_lining_it():
    """The floor of a slot cut through a wall is a wall top, and "every wall top"
    claimed it — so the cladding lined the inside of the scupper.

    The test that separates it from a coping is the sign between two opposed
    flanks: a coping's are the faces across its wall's thickness and look *away*
    from each other, an opening's cheeks look *at* each other. Read per body,
    because the slot cuts through the cap plates too and per element their two
    reveals would read as cheeks and take the coping with them.
    """
    from build import _opening, _upward
    from skin.substrate import WALL

    parts = _slotted_wall()
    faces = _faces(parts)
    cheeks, floor = _opening(faces)

    assert cheeks.any(), "the slot's two cheeks"
    for i in np.where(cheeks)[0]:
        assert abs(abs(faces.normals[i][0]) - 1) < 1e-6, "a cheek faces along x here"
    assert floor.any(), "the sill between them"
    for i in np.where(floor)[0]:
        assert faces.normals[i][2] > 0.5 and abs(
            faces.centres[i][2] - 0.8) < 1e-6, "the sill is the top of the low block"

    # the sill *is* a wall top, which is why "every wall top" claimed it and the
    # cladding lined the outlet. `cladding_faces` subtracts `floor` for exactly
    # this; the rule is checked here and the result on the real bake is checked
    # by `tests/test_import.py`
    assert (floor & _upward(faces.normals) & faces.of_role(WALL)).any()

    # the wall's own coping is not a floor, though the same two cheeks touch it:
    # they stop at that level rather than standing over it
    top = (faces.normals[:, 2] > 1e-6) & (faces.centres[:, 2] > 0.9)
    assert top.any() and not (top & floor).any(), "the coping read as its own floor"


def test_a_lap_is_shortened_to_the_face_it_lands_on():
    """`_lap` places whole quads, so a band wider than the face it lands on does
    not overhang — it is cut to fit or refused.

    Without this, covering the scupper cheeks sent a 205 mm upstand onto a 34 mm
    cap-plate reveal: 120 mm above the top of the wall and straight through the
    cladding's coping, 13 crossings. The march is over coplanar *triangles*, not
    one face, because a union triangulates a wall and a lap commonly crosses
    several — a 62 mm drip off a 34 mm cap plate must still run its full depth
    down the parapet's coplanar face below.
    """
    low = substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 1.0))
    tall = substrate.prism((1.0, 0.0, 0.0), (2.0, 0.4, 1.05))
    parts = [low, tall]
    d, out = 0.01, 0.205
    room = 0.05                      # all `tall` presents above `low`'s top

    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6)
        & (faces.centres[:, 2] < 1.02),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=0.06, out=out,
    )
    on = np.abs(skin.triangles[:, :, 0] - (1.0 - d)).max(axis=1) < 1e-6
    assert on.any(), "no upstand against the taller wall"
    top = float(skin.triangles[on][:, :, 2].max())
    assert top == pytest.approx(1.05 + d, abs=1e-6), (
        f"the upstand reached z {top:.4f}: it ran its full {out * 1000:.0f} mm "
        f"instead of stopping at the {room * 1000:.0f} mm the wall offers"
    )


def test_a_run_on_does_not_bridge_a_gap_in_the_plane_it_runs_along():
    """Coplanar is not contiguous.

    Caught by `/code-review high` 2026-08-21: the run-on sampled the tip and the
    far end and nothing between, so a 130 mm void between two bodies presenting
    one plane read as solid and the lap hung four triangles over it. It marches
    now, the same way a round-1 lap is cut to fit.
    """
    parts = [
        substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 1.0)),     # covered top
        substrate.prism((1.0, 0.0, 0.0), (1.02, 0.4, 2.0)),    # a 20 mm stub
        substrate.prism((1.15, 0.0, 0.0), (1.40, 0.4, 2.0)),   # ...then a void
    ]
    d, out = 0.01, 0.2
    skin = skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6) & (faces.centres[:, 2] < 1.5),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=0.06, out=out,
    )
    on = np.abs(skin.triangles[:, :, 1] - (0.0 - d)).max(axis=1) < 1e-6
    reach = float(skin.triangles[on][:, :, 0].max())
    assert reach <= 1.02 + 1e-6, (
        f"the drip ran on to x = {reach:.4f}, out over the void that starts at 1.02"
    )


def test_only_a_lap_already_near_level_is_snapped_to_level():
    """`_across` rounds a lap off a cap plate's own fall onto the vertical, so an
    upstand is a height. It must not round a lap that genuinely rakes.

    Caught by `/code-review high` 2026-08-21: the threshold was 45°, so a lap
    raking 40° *down* was flattened onto the horizontal — and `reach` then read
    its flattened `t_z` and billed it the upstand distance rather than the drip.
    """
    from skin.offset import RAKE, _across

    def direction(arris, third):
        """`_across` over a face on y = 0, across the arris from the origin."""
        v = np.array([[0.0, 0.0, 0.0], arris, third], dtype=float)
        return _across(trimesh.Trimesh(vertices=v, faces=[[0, 1, 2]],
                                       process=False), 0, 1, 0)

    level = [1.0, 0.0, 0.0]
    assert np.allclose(direction(level, [0.5, 0.0, 1.0]), [0, 0, 1]), "a face above laps up"
    assert np.allclose(direction(level, [0.5, 0.0, -1.0]), [0, 0, -1]), "a face below laps down"

    # an arris raking gently — a cap plate's own fall — is rounded off, because
    # an upstand is a height and not a measurement along the fall
    gentle = direction([1.0, 0.0, 0.02], [0.5, 0.0, 1.0])
    assert np.allclose(gentle, [0, 0, 1]), f"{gentle} kept the cap plate's fall"

    # an arris raking hard is not: the lap keeps the direction it really has,
    # and `reach` then bills it the drip it really is
    hard = direction([1.0, 0.0, 0.5], [0.0, 0.0, -1.0])
    assert -1 + RAKE < hard[2] < -RAKE, f"{hard} was rounded onto an axis"
    assert abs(hard[0]) > RAKE, "the in-plane component was discarded"


def test_a_hole_corner_crossing_a_tiling_diagonal_is_tiled_again():
    """`planar_offset` moves vertices and keeps the union's triangulation.
    manifold3d tiles a face with a hole cut in it by fanning across the hole, so
    a hole corner that starts closer to one of those diagonals than the offset
    distance crosses it when it moves, and its triangle comes out inside out —
    covering a sliver of the hole that the offset never placed.

    On the live bake that is the cladding's notch round the scupper cornice:
    `Cornice-Headhouse-E`'s corner sits 4.7 mm from the diagonal of the parapet
    facade it is cut in, and the 85 mm offset takes it clean across, filling in
    the bottom right of the notch. Here it is in miniature: a 4 x 4 wall face
    with a 0.2 x 0.2 band stuck on it, just off the face's own diagonal.
    """
    def box(x0, x1, y0, y1, z0, z1):
        return trimesh.creation.box(bounds=[[x0, y0, z0], [x1, y1, z1]])

    parts = [box(0, 0.4, 0, 4, 0, 4), box(-0.1, 0, 1.8, 2.0, 2.05, 2.25)]
    wall = lambda f: (np.abs(f.normals - [-1, 0, 0]).max(axis=1) < 1e-6) & (f.owner == 0)
    skin = skin_over(parts, D, keep=wall)

    # not one face turned inside out: they all point the way the wall's does
    assert np.allclose(skin.face_normals, [-1, 0, 0])
    # the outline and the hole both grew by the offset, and nothing filled it in
    assert np.isclose(skin.area, (4 + 2 * D) ** 2 - (0.2 + 2 * D) ** 2, atol=1e-6)
    assert len(trimesh.grouping.group_rows(skin.edges_sorted, require_count=1)) == 8
    for corner in [(1.7, 1.95), (2.1, 1.95), (2.1, 2.35), (1.7, 2.35)]:
        assert np.isclose(skin.vertices[:, 1:], corner, atol=1e-6).all(axis=1).any(), (
            f"the hole lost its corner at {corner}"
        )


def _neighbours(gap):
    """A wall, and a taller one standing `gap` away from its face.

    The neighbour runs past the wall at both ends, because what is tested is the
    **miter vertices**, and those sit at the ends of the arris. A neighbour
    flush with the wall in plan leaves them `distance` out past it, in clear
    air, with nothing wrong at either.
    """
    wall = trimesh.creation.box(extents=(1.0, 4.0, 2.0))
    wall.apply_translation([0.5, 2.0, 1.0])
    other = trimesh.creation.box(extents=(2.0, 6.0, 3.0))
    other.apply_translation([1.0 + gap + 1.0, 2.0, 1.5])
    return [wall, other]


def _top_of(parts):
    """The lower wall's top face alone."""
    def keep(faces):
        return (faces.normals[:, 2] > 0.9) & (faces.centres[:, 2] < 2.5)

    return skin_over(parts, D, keep=keep)


def test_a_free_miter_reaches_past_the_face_it_covers():
    """The offset is solved over the whole body, then faces are selected.

    So the edge of a selection keeps the miter it would have had if the
    neighbours were skinned too, and a miter with room around it is left exactly
    where it is — on all four sides, three of which have no neighbour at all.

    Written 2026-08-22 as the guard on `_trim_beside` — *the invariant the trim
    must not reverse*. The trim was backed out on 2026-08-25 and this outlived
    it: what it pins is the "solved over the whole body" invariant itself, which
    is CLAUDE.md's and predates the mechanism by months. Kept for that, and it
    passes unchanged with the trim gone.
    """
    parts = _neighbours(gap=3 * D)
    skin = _top_of(parts)

    assert np.allclose(skin.bounds[0], [-D, -D, 2.0 + D])
    assert np.allclose(skin.bounds[1], [1.0 + D, 4.0 + D, 2.0 + D])
    assert np.isclose(skin.area, (1.0 + 2 * D) * (4.0 + 2 * D))
    assert clearance(parts, skin) > D - 1e-6


def _slotted(x0, x1):
    """A parapet with a slot cut clean through it, the scupper in miniature."""
    return [
        substrate.prism((0.0, 0.0, 0.0), (x0, 0.4, 1.0)),
        substrate.prism((x1, 0.0, 0.0), (2.0, 0.4, 1.0)),
    ]


def _lined(parts, d, drop):
    """Cap the parapet and line the slot's cheeks, with `out` switched off."""
    return skin_over(
        parts, d,
        keep=lambda faces: (faces.normals[:, 2] > 1e-6)
        | (
            (np.abs(faces.normals[:, 0]) > 1 - 1e-6)
            & (np.abs(np.abs(faces.centres[:, 0] - 1.0) - 0.2) < 1e-6)
        ),
        lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
        drop=drop, out=0.0,
    )


def test_a_band_turns_down_the_reveal_it_runs_into():
    """Duncan, 2026-08-22: *"The skirt should turn downwards on each side of the
    scupper."* The scupper in miniature: a slot cut through a parapet whose
    cheeks the skin lines.

    The drip along the coping runs into the lined cheek and does not stop there.
    It turns and runs down the reveal, staying on the very face it was already
    lapping onto — the fourth answer at a free end, after the run-on and the
    fold. The band it continues is a drip, so it stays priced at `drop` and
    stays measured on the substrate, although the direction it now runs in is
    sideways and `out` is switched off. That is Duncan's option B, taken on
    2026-08-25 over the alternative of authoring the skin an `out`.

    So the band spans **`distance + drop`**: across the reveal it laps out of,
    plus its own drip beyond the arris.
    """
    d, drop = 0.05, 0.12
    parts = _slotted(0.8, 1.2)
    skin = _lined(parts, d, drop)

    front = np.abs(skin.triangles[:, :, 1] + d).max(axis=1) < 1e-6
    assert front.any(), "nothing at all on the face the coping's drip hangs down"
    x, z = skin.triangles[front][:, :, 0], skin.triangles[front][:, :, 2]

    # the drip alone reaches z = 1 - drop; anything below that turned down
    turned = z.min(axis=1) < 1.0 - drop - 1e-6
    assert turned.any(), (
        "the skirt stopped at the slot: no surface on the front plane below the "
        f"drip's own reach of z = {1.0 - drop:.4f}"
    )
    assert z[turned].min() == pytest.approx(-d, abs=1e-6), (
        "the turn-down did not run the full depth of the reveal"
    )

    west = turned & (x.mean(axis=1) < 1.0)
    east = turned & (x.mean(axis=1) > 1.0)
    assert west.any() and east.any(), "only one side of the slot turned down"
    for side, near, out_ in ((west, 0.8, -1.0), (east, 1.2, 1.0)):
        span = x[side]
        inner, outer = near + out_ * -d, near + out_ * drop
        assert min(span.min(), span.max()) == pytest.approx(min(inner, outer), abs=1e-6)
        assert max(span.min(), span.max()) == pytest.approx(max(inner, outer), abs=1e-6)


def test_a_turn_is_refused_where_the_skin_already_stands_proud_of_the_arris():
    """A band turns only where there is a gap to close.

    A wall standing out of the face a drip runs along poses the same arris the
    scupper does — a covered face meeting the receiving plane at right angles,
    at the free end of the drip's run — and nothing local to the vertex tells
    them apart. What differs is which way the covered face looks: at the scupper
    it faces back along the turn, so the skin's edge is `distance` on the far
    side of the arris and the band spans the gap; here it faces along the turn,
    the skin already stands `distance` past the arris that way, and the outer
    line falls **behind** the edge it would spring from.

    So the band is not placed at all where `drop` is the shorter of the two, and
    where it is the longer the band is exactly the difference — the part of the
    drip the skin does not already cover. Both wall ends of the live bake are
    the first case, and the attempt this rule replaces put a band 30 mm off the
    substrate at each of them.
    """
    parts = [
        substrate.prism((0.0, 0.0, 0.0), (1.0, 0.4, 1.0)),
        substrate.prism((1.0, -0.3, 0.0), (2.0, 0.4, 1.0)),
    ]
    d = 0.05

    def covered(faces):
        return (faces.normals[:, 2] > 1e-6) | (
            (faces.normals[:, 0] < -1 + 1e-6)
            & (np.abs(faces.centres[:, 0] - 1.0) < 1e-6)
        )
    for drop, width in ((0.03, None), (0.12, 0.12 - d)):
        skin = skin_over(
            parts, d, keep=covered,
            lap=lambda faces: np.abs(faces.normals[:, 2]) < 1e-6,
            drop=drop, out=0.0,
        )
        front = np.abs(skin.triangles[:, :, 1] + d).max(axis=1) < 1e-6
        z = skin.triangles[front][:, :, 2]
        turned = z.min(axis=1) < 1.0 - drop - 1e-6
        if width is None:
            assert not turned.any(), (
                f"a band turned down at drop {drop} where the skin already "
                f"stands {d} past the arris: the outer line is behind the edge "
                "it springs from"
            )
            continue
        assert turned.any(), f"no band turned down at drop {drop}"
        span = skin.triangles[front][:, :, 0][turned]
        assert span.max() - span.min() == pytest.approx(width, abs=1e-6), (
            "the band is not the part of the drip the skin leaves uncovered"
        )
