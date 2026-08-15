import numpy as np
import pytest
import trimesh

from skin import clearance, planar_offset, skin_over, substrate, write_obj

D = 0.1


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
    from skin.substrate import ROOF, WALL, classify, horizontality

    from build import current_substrate

    parts = current_substrate()
    assert [classify(p) for p in parts] == [WALL, WALL, ROOF, WALL]
    # the roof is the only part with more horizontal surface than vertical
    assert [horizontality(p) > 0.5 for p in parts] == [False, False, True, False]


def test_classify_survives_a_wall_that_does_not_run_along_an_axis():
    """The case bounds get wrong.

    An axis-aligned box around a diagonal wall inflates both horizontal extents
    until the height is the smallest of the three, so a bounds test calls it a
    slab. Face normals and the oriented box both still see a wall.
    """
    from skin.substrate import WALL, classify

    wall = trimesh.creation.box(extents=(10.0, 0.3, 3.0))
    wall.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
    )
    assert int(np.argmin(wall.extents)) == 2  # AABB thinks it is thin vertically
    assert classify(wall) == WALL  # and is wrong


def test_classify_raises_rather_than_guessing():
    """A part it cannot read must fail loudly, carrying the numbers.

    Silently mislabelling one part inside a large model is the failure mode that
    made the old module hard to debug.
    """
    from skin.substrate import AmbiguousPart, classify

    for label, solid in (
        ("cube", trimesh.creation.box(extents=(1.0, 1.0, 1.0))),
        ("column", trimesh.creation.box(extents=(0.4, 0.4, 3.0))),
    ):
        with pytest.raises(AmbiguousPart) as raised:
            classify(solid)
        assert "thin direction" in str(raised.value), label
        assert "extents" in str(raised.value), label


def test_exterior_and_interior_are_read_off_each_wall_s_own_slope():
    """The rule that replaced four hand-computed plane coordinates.

    A wall's top falls toward its interior, so the face under the high edge is
    the facade and the one under the low edge is the interior. Nothing names a
    plane or a part index.
    """
    from build import current_substrate, uphill, wall_faces
    from skin.offset import Faces, _owner

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    faces = Faces(body, parts, _owner(body, parts))
    exterior, interior = wall_faces(faces)

    # each wall's top falls toward the interior, so uphill points at the facade
    assert np.allclose(uphill(parts[1]), [1.0, 0.0], atol=1e-3)  # part 2 -> +X
    assert np.allclose(uphill(parts[3]), [0.0, 1.0], atol=1e-3)  # part 4 -> +Y

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
    """A stacked wall panel has no high side, so it cannot name its own facade."""
    from build import uphill

    with pytest.raises(ValueError, match="flat top"):
        uphill(substrate.prism((0, 0, 0), (4.0, 0.3, 3.0)))


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
    from skin.offset import Faces, _owner

    front = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)  # brick, at x = 0
    headhouse = _facing_wall(3.0, 3.4, 1.0, 4.0, 4.0, 3.99)  # rainscreen, set back
    front.metadata[FACADE] = BRICK
    headhouse.metadata[FACADE] = RAINSCREEN

    parts = [front, headhouse]
    body = trimesh.boolean.union(parts)
    faces = Faces(body, parts, _owner(body, parts))

    # both walls face the same way, so direction cannot tell them apart
    assert np.allclose(uphill(front), [-1.0, 0.0], atol=1e-3)
    assert np.allclose(uphill(headhouse), [-1.0, 0.0], atol=1e-3)

    brick = facades_of(faces, BRICK)
    rainscreen = facades_of(faces, RAINSCREEN)
    assert brick.any() and rainscreen.any()
    assert not (brick & rainscreen).any()

    # the brick is the one at x = 0; the rainscreen the one set back at x = 3
    assert np.allclose(body.vertices[body.faces[brick]][:, :, 0], 0.0, atol=1e-6)
    assert np.allclose(body.vertices[body.faces[rainscreen]][:, :, 0], 3.0, atol=1e-6)

    # together they claim every facade, and the check agrees
    check_facades(faces, systems=(BRICK, RAINSCREEN))


def test_an_unclaimed_facade_is_refused():
    """A facade no cladding system claims is a silently bare wall. Fail instead."""
    from build import BRICK, FACADE, RAINSCREEN, check_facades
    from skin.offset import Faces, _owner

    front = _facing_wall(0.0, 0.4, 0.0, 6.0, 3.0, 2.99)
    front.metadata[FACADE] = BRICK  # but only rainscreen is declared below
    parts = [front]
    body = trimesh.boolean.union(parts)
    faces = Faces(body, parts, _owner(body, parts))

    with pytest.raises(ValueError, match="claimed by no cladding system"):
        check_facades(faces, systems=(RAINSCREEN,))


def test_build_does_not_emit_the_substrate_unless_asked():
    """The module reads the substrate and never writes it.

    Where the substrate is live geometry — Bonsai IFC parts carrying semantic
    data — emitting it would put a second, dead copy of every part into the
    scene beside the original. Opting in has to be deliberate.
    """
    import build as build_module
    from build import SKINS, build, current_substrate

    parts = current_substrate()
    before = [(p.vertices.copy(), p.faces.copy()) for p in parts]

    manifest = build(parts)
    roles = {e["name"]: e["role"] for e in manifest}
    assert set(roles) == {s["name"] for s in SKINS}
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

    from build import SKINS, current_substrate

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    membrane = SKINS[0]
    surface = skin_over(parts, D, keep=membrane["keep"])

    assert not surface.is_watertight  # a surface, not a solid
    border = trimesh.grouping.group_rows(surface.edges_sorted, require_count=1)
    assert len(border) and len(set(surface.edges_sorted[border].ravel())) == len(border)

    from skin.offset import Faces, _owner

    owner = _owner(body, parts)
    kept = membrane["keep"](Faces(body, parts, owner))
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

    from build import SKINS, current_substrate, wall_faces
    from skin.offset import Faces, _owner

    membrane = SKINS[0]
    drop = membrane["drop"]
    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    owner = _owner(body, parts)
    faces = Faces(body, parts, owner)
    walls = membrane["turn_down"](faces)

    # the membrane skirts down the walls it carried over, and only those: parts 1
    # and 2, the two whose interior face the roof runs into
    assert set(owner[walls].tolist()) <= {0, 1}
    # every skirted face is a facade -- never an end, never an interior face
    exterior, interior = wall_faces(faces)
    assert (walls & exterior).sum() == walls.sum()
    assert not (walls & interior).any()

    surface = skin_over(parts, D, keep=membrane["keep"],
                        turn_down=membrane["turn_down"], drop=drop)
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

    from build import SKINS, current_substrate, separation_check

    parts = current_substrate()
    body = trimesh.boolean.union(parts)
    from skin.offset import Faces, _owner

    owner = _owner(body, parts)
    faces = Faces(body, parts, owner)

    membrane, cladding = SKINS
    # the membrane climbs the interior walls and skirts the exterior; the
    # cladding does the reverse
    assert (membrane["keep"](faces) & cladding["turn_down"](faces)).any()
    assert (cladding["keep"](faces) & membrane["turn_down"](faces)).any()

    gap, skins = separation_check(parts)
    assert gap > 0.05, f"skins only {gap * 1000:.1f} mm apart"
    for skin in skins:
        assert not skin.is_watertight
        assert skin.metadata["offset_residual"] < 1e-9
