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
    assert set(roles) == {s["name"] for s in skins()}
    assert set(roles.values()) == {"skin"}
    assert not list(build_module.BUILD_DIR.glob("Substrate_*.obj"))

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


def test_skirt_hangs_the_right_walls_to_the_right_depth():
    import trimesh

    from build import current_substrate, skins, wall_faces
    from skin.offset import _owner

    membrane = skins()[0]
    drop = membrane["drop"]
    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    owner = _owner(body, parts)
    faces = _faces(parts, body)
    walls = membrane["turn_down"](faces)

    # the membrane skirts down the walls it carried over, and only those: parts 1
    # and 2, the two whose interior face the roof runs into
    assert set(owner[walls].tolist()) <= {0, 1}
    # every skirted face is a facade -- never an end, never an interior face
    exterior, interior = wall_faces(faces, FALL)
    assert (walls & exterior).sum() == walls.sum()
    assert not (walls & interior).any()

    surface = skin_over(parts, D, keep=membrane["keep"],
                        turn_down=membrane["turn_down"], drop=drop,
                        classify=membrane["classify"])
    tops = {round(float(z), 6) for z in body.vertices[:, 2] if z > 1.5}
    hems = {round(float(z), 6) for z in surface.vertices[:, 2]} & {
        round(t - drop, 6) for t in tops
    }
    assert hems, "skirt hem should sit exactly drop below a substrate top edge"

    # a near-level edge must be exactly level, hem included
    e = surface.vertices[surface.edges_unique]
    dz = np.abs(e[:, 0, 2] - e[:, 1, 2])
    assert dz[dz < 1e-3].max() < 1e-12


def test_cladding_and_membrane_cover_complementary_walls_and_never_meet():
    import trimesh

    from build import current_substrate, separation_check, skins

    parts = current_substrate()
    faces = _faces(parts)

    membrane, cladding = skins()
    # the membrane climbs the interior walls and skirts the exterior; the
    # cladding does the reverse
    assert (membrane["keep"](faces) & cladding["turn_down"](faces)).any()
    assert (cladding["keep"](faces) & membrane["turn_down"](faces)).any()

    gap, skins = separation_check(parts)
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
    membrane, cladding = skins()

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
    assert np.isclose(_skin_from(membrane, parts).vertices[:, 2].min(), 1.164, atol=1e-3)
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


def test_a_turn_out_stops_at_the_elected_faces_not_at_their_plane():
    """A wall's outer face and the parapet's above it are the *same plane*.

    A building shares a plane right up a stack, so matching a turn-out on the
    plane alone reaches every coplanar surface in the model. On the Unit8 bake
    that turned the membrane's parapet skirt out 205 mm into thin air 1.5 m
    above the roof whose flange elected it, and put 35 crossings through the
    cladding. The elected faces bound the turn-out, not the plane they lie on.
    """
    from skin.offset import _turn_out

    # two lifts of one wall, both presenting a face on x = 0, with a gap so the
    # union keeps them apart; only the lower one is elected
    lower = trimesh.creation.box(extents=[1, 1, 1], transform=trimesh.transformations.
                                 translation_matrix([0.5, 0.5, 0.5]))
    upper = trimesh.creation.box(extents=[1, 1, 1], transform=trimesh.transformations.
                                 translation_matrix([0.5, 0.5, 1.7]))
    body = trimesh.util.concatenate([lower, upper])
    outer = np.abs(body.face_normals @ [-1, 0, 0] - 1) < 1e-9
    elected = outer & (body.triangles[:, :, 2].max(axis=1) <= 1.0 + 1e-9)
    assert elected.sum() == 2 and outer.sum() == 4, "one lift elected, two present"

    d, out = 0.01, 0.2
    verts, faces = [], []

    def panel(z):  # a horizontal skin panel ending on the offset plane at height z
        n = len(verts)
        verts.extend([np.array(v) for v in
                      ([-d, 0.2, z], [-d, 0.8, z], [-0.5, 0.5, z])])
        faces.append([n, n + 1, n + 2])

    panel(0.5)   # on the elected lift
    panel(1.7)   # on the lift above it, same plane, not elected

    collar = _turn_out(body, verts, faces, elected, d, out)
    assert collar, "the panel that does stop on the elected face still turns out"

    z = np.array([verts[i][2] for tri in collar for i in tri])
    assert z.min() >= 0.5 - out - 1e-9 and z.max() <= 0.5 + out + 1e-9, (
        f"the turn-out reached z {z.min():.3f}..{z.max():.3f}: it followed the "
        "plane up to the lift above instead of stopping at the elected faces"
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
