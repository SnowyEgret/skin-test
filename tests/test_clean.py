"""`skin.clean` — coplanar overlap dissolved, and nothing else touched.

Mesh in, mesh out, so most of this is hand-made geometry with no substrate
behind it. The two rig tests are there because the condition the pass exists for
— a lap emitting whole quads that overlap — is produced by the rules and not by
hand.
"""

import numpy as np
import pytest
import trimesh

from skin import substrate
from skin.clean import clean


def _sheet(corners, flip=False):
    """A quad as two triangles, wound about its own outward normal."""
    faces = [[0, 1, 2], [0, 2, 3]]
    return np.asarray(corners), [f[::-1] for f in faces] if flip else faces


def _mesh(*sheets):
    verts, faces = [], []
    for points, tris in sheets:
        faces += [[i + len(verts) for i in tri] for tri in tris]
        verts += list(points)
    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=False)


def _nonmanifold(mesh):
    return [
        g
        for g in trimesh.grouping.group_rows(mesh.edges_sorted, require_count=None)
        if len(g) > 2
    ]


def _borders(mesh):
    return len(trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1))


def test_two_overlapping_coplanar_quads_become_one_covering():
    """The condition the pass exists for: a band lying inside another band."""
    big = _sheet([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)])
    small = _sheet([(1, 1, 0), (3, 1, 0), (3, 3, 0), (1, 3, 0)])
    mesh = _mesh(big, small)
    assert np.isclose(mesh.area, 16 + 4)  # the summed area double-counts

    out = clean(mesh)

    assert np.isclose(out.area, 16.0)
    assert np.isclose(out.metadata["overlap_removed"], 4.0)
    assert np.allclose(out.face_normals, [0, 0, 1])


def test_a_bowtie_quad_is_resolved_and_comes_out_facing_one_way():
    """A quad whose outline crosses itself: its two triangles overlap and are
    wound opposite ways, which is why planes are grouped either way up."""
    verts = np.array([(0, 0, 0), (4, 0, 0), (1, 3, 0), (3, 3, 0)])
    mesh = trimesh.Trimesh(
        vertices=verts, faces=np.array([[0, 1, 2], [0, 2, 3]]), process=False
    )
    assert (mesh.face_normals[0] @ mesh.face_normals[1]) < 0, "not a bowtie"
    assert np.isclose(mesh.area, 9.0)  # 6 and 3, and they overlap

    out = clean(mesh)

    assert len(np.unique(np.round(out.face_normals, 9), axis=0)) == 1
    assert out.area < mesh.area - 1e-9, "the two halves still double-count"
    assert np.isclose(clean(out).area, out.area)


def test_two_coplanar_regions_facing_opposite_ways_keep_their_directions():
    """A knife — a roof butting a wall on the wall's own plane leaves both sides
    of the contact exposed — is an ordinary condition, not an overlap.

    Grouping either way up puts the two in one group, so orientation is decided
    per region. Flipping them to a plane-wide majority would turn a solid inside
    out there, which is exactly what it did before this was pinned.
    """
    up = _sheet([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    down = _sheet([(3, 0, 0), (5, 0, 0), (5, 2, 0), (3, 2, 0)], flip=True)
    out = clean(_mesh(up, down))

    assert np.isclose(out.area, 8.0)
    facing = out.face_normals[:, 2]
    left = out.triangles.mean(axis=1)[:, 0] < 2.5
    assert (facing[left] > 0).all() and (facing[~left] < 0).all()


def test_two_touching_regions_facing_opposite_ways_keep_their_directions():
    """The same knife with no gap in it, which is the ordinary case: `unary_union`
    merges two touching regions into one polygon, so the two ways up have to be
    separated **before** it runs. Deciding orientation afterwards — per plane or
    per region — cannot recover the boundary it dissolved."""
    up = _sheet([(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)])
    down = _sheet([(0, 1, 0), (0, 2, 0), (0, 2, 1), (0, 1, 1)], flip=True)
    out = clean(_mesh(up, down))

    assert np.isclose(out.area, 2.0)
    lower = out.triangles.mean(axis=1)[:, 1] < 1
    assert (out.face_normals[lower, 0] > 0).all()
    assert (out.face_normals[~lower, 0] < 0).all()


def test_two_solids_meeting_along_an_edge_keep_their_volume():
    """The same condition as a whole mesh, where getting it wrong is loud: two
    cubes touching along one edge share a plane, facing opposite ways across it."""
    a = substrate.cube(1.0, center=(0.5, 0.5, 0.5))
    b = substrate.cube(1.0, center=(1.5, 1.5, 0.5))
    both = trimesh.util.concatenate([a, b])
    out = clean(both)

    assert np.isclose(out.volume, 2.0), "a flipped face on the shared plane"
    assert np.isclose(out.area, 12.0)
    assert out.is_winding_consistent


def test_two_points_one_micron_apart_are_two_points():
    """The weld radius must stay well inside the 1 µm lattice every substrate
    coordinate is snapped to. At `PLANE_TOL` two neighbouring lattice points are
    9.9999999925e-07 apart and weld into one, which silently eats a 1 µm strip
    and reports the loss as overlap that never existed."""
    x = round(12.345678 / 1e-6) * 1e-6
    y = round(12.345679 / 1e-6) * 1e-6
    strip = _sheet([(x, 0, 0), (y, 0, 0), (y, 0, 1), (x, 0, 1)])
    beside = _sheet([(y, 0, 0), (y + 0.5, 0, 0), (y + 0.5, 0, 1), (y, 0, 1)])
    mesh = _mesh(strip, beside)
    out = clean(mesh)

    assert np.isclose(out.area, mesh.area), "the 1 µm strip was welded away"
    assert np.isclose(out.metadata["overlap_removed"], 0.0)


def test_a_closed_solid_comes_back_the_same_solid():
    """Nothing here overlaps, so the only thing cleaning can do to a box is
    break it. Volume is the test that catches a flipped face; area alone does not."""
    box = substrate.cube(2.0)
    out = clean(box)

    assert out.is_watertight and out.is_winding_consistent
    assert np.isclose(out.volume, box.volume)
    assert np.isclose(out.area, box.area)
    assert len(out.faces) == 12  # each face still tiled, not merged into one n-gon


def test_a_hole_is_not_closed():
    """It resolves overlap and says nothing about a hole: a plane's union keeps
    its interior rings, and `manifold3d.triangulate` takes them as holes."""
    outer = [(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)]
    inner = [(1, 1, 0), (3, 1, 0), (3, 3, 0), (1, 3, 0)]
    # a square annulus, tiled as four quads round the hole
    sheets = [
        _sheet([outer[i], outer[(i + 1) % 4], inner[(i + 1) % 4], inner[i]])
        for i in range(4)
    ]
    out = clean(_mesh(*sheets))

    assert np.isclose(out.area, 16 - 4)
    assert _borders(out) == 8, "the hole and the perimeter, four edges each"


def test_faces_on_different_planes_are_left_to_each_other():
    """Two sheets that intersect but are not coplanar: a 2D boolean has nothing
    to say about them, and must not invent anything."""
    a = _sheet([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    b = _sheet([(1, 0, -1), (1, 0, 1), (1, 2, 1), (1, 2, -1)])
    mesh = _mesh(a, b)
    out = clean(mesh)

    assert np.isclose(out.area, mesh.area)
    assert np.isclose(out.metadata["overlap_removed"], 0.0)


def test_a_preserved_vertex_is_bit_identical_and_the_input_is_untouched():
    """shapely is bit-exact on the points its union keeps, and that is worth
    keeping through the projection: a vertex that survives is the same vertex."""
    big = _sheet([(0, 0, 0.5), (4, 0, 0.5), (4, 4, 0.5), (0, 4, 0.5)])
    small = _sheet([(1, 1, 0.5), (3, 1, 0.5), (3, 3, 0.5), (1, 3, 0.5)])
    mesh = _mesh(big, small)
    before = mesh.vertices.copy(), mesh.faces.copy()

    out = clean(mesh)

    kept = {tuple(v) for v in out.vertices} & {tuple(v) for v in mesh.vertices}
    assert len(kept) == 4, "the outer corners, to the bit"
    assert np.array_equal(mesh.vertices, before[0])
    assert np.array_equal(mesh.faces, before[1])


def test_a_face_with_no_area_is_dropped_rather_than_given_a_plane():
    """A degenerate triangle has no normal to group on and covers nothing."""
    quad = _sheet([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    verts = np.vstack([quad[0], [(3, 0, 0), (4, 0, 0), (5, 0, 0)]])
    mesh = trimesh.Trimesh(
        vertices=verts, faces=np.array(quad[1] + [[4, 5, 6]]), process=False
    )
    out = clean(mesh)

    assert np.isclose(out.area, 4.0)
    assert len(out.faces) == 2


def test_a_mesh_with_nothing_to_dissolve_keeps_its_area_and_its_border():
    tilted = _sheet([(0, 0, 0), (2, 0, 1), (2, 2, 1), (0, 2, 0)])
    mesh = _mesh(tilted)
    out = clean(mesh)

    assert np.isclose(out.area, mesh.area)
    assert _borders(out) == _borders(mesh) == 4


def _rig_skins():
    from build import _skin_from, classifier, current_substrate, group_caps, group_cornices, skins
    from skin import parameters

    params = parameters.load_validated()
    parts = current_substrate()
    group_cornices(parts)
    group_caps(parts, classifier(params))
    return parts, {s["name"]: _skin_from(s, parts) for s in skins(params)}


def test_the_rig_membrane_overlaps_itself_and_the_pass_dissolves_it():
    """The real condition, on the substrate the tests own: the membrane's laps
    cover 53.6 cm2 of it twice, so its summed area is not the area it covers."""
    from skin.clean import _basis, _groups
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    _, built = _rig_skins()
    membrane = built["Membrane"]

    covered = 0.0
    for rep, group in _groups(membrane):
        u, v = _basis(rep[:3])
        origin = rep[:3] * rep[3]
        covered += unary_union(
            [
                Polygon(np.column_stack([(p - origin) @ u, (p - origin) @ v]))
                for p in membrane.vertices[membrane.faces[group]]
            ]
        ).area

    out = clean(membrane)
    assert membrane.area - covered > 0.005, "the rig should pose the condition"
    assert np.isclose(out.area, covered), "cleaned area is the area covered"
    assert np.isclose(clean(out).area, out.area), "and cleaning is idempotent"


def test_cleaning_a_skin_leaves_it_where_the_offset_put_it():
    """The pass moves nothing off its plane and nothing towards the substrate:
    it only decides which parts of each plane are covered."""
    from skin import clearance
    from skin.offset import _plane_rows

    parts, built = _rig_skins()
    for name, skin in built.items():
        out = clean(skin)
        rows = np.unique(np.round(_plane_rows(skin), 9), axis=0)
        off = max(
            min(abs(row[:3] @ point - row[3]) for row in rows) for point in out.vertices
        )
        assert off < 1e-6, f"{name}: a vertex sits {off:.2e} m off every original plane"
        assert np.isclose(clearance(parts, out), clearance(parts, skin), atol=1e-9)
        assert not _nonmanifold(out), f"{name}: cleaning left a non-manifold edge"


def _split_quad(z=0.0):
    """A 2x2 square tiled so that (1, 0) is a vertex on its bottom edge."""
    v = [(0, 0, z), (1, 0, z), (2, 0, z), (2, 2, z), (0, 2, z)]
    return np.array(v, float), [[0, 1, 3], [1, 2, 3], [0, 3, 4]]


def test_dissolve_drops_a_vertex_that_no_ring_turns_at():
    """The opted-in second operation: a vertex lying straight between its
    neighbours on every ring that holds it says nothing about the shape."""
    mesh = _mesh(_split_quad())
    assert any(np.allclose(v, (1, 0, 0)) for v in mesh.vertices)

    out = clean(mesh, dissolve=True)

    assert np.isclose(out.area, 4.0)
    assert not any(np.allclose(v, (1, 0, 0)) for v in out.vertices)
    assert out.metadata["vertices_dissolved"] == 1
    assert _borders(out) == 4, "the outline is a plain rectangle again"


def test_dissolve_is_off_unless_asked():
    """It is a separate operation, not part of resolving overlap: the outlines
    it thins are correct either way."""
    out = clean(_mesh(_split_quad()))

    assert any(np.allclose(v, (1, 0, 0)) for v in out.vertices)
    assert out.metadata["vertices_dissolved"] == 0


def test_dissolve_keeps_a_vertex_the_facet_next_to_it_turns_at():
    """The whole reason `skin/export.py` keeps collinear vertices: drop one that
    a neighbouring facet corners on and the join becomes a T-junction. So the
    question is asked over every ring of the mesh at once, not per plane."""
    flat = _split_quad()
    upstand = _sheet([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)])
    mesh = _mesh(flat, upstand)

    out = clean(mesh, dissolve=True)

    assert np.isclose(out.area, 5.0)
    assert any(np.allclose(v, (1, 0, 0)) for v in out.vertices), (
        "the upstand turns at (1, 0, 0); dissolving it there tears the join"
    )
    assert out.metadata["vertices_dissolved"] == 0


def test_dissolve_leaves_a_solid_alone():
    """A box turns at every vertex it has, so there is nothing to thin."""
    box = substrate.cube(2.0)
    out = clean(box, dissolve=True)

    assert out.metadata["vertices_dissolved"] == 0
    assert np.isclose(out.volume, box.volume) and out.is_watertight


def test_metadata_keyed_on_an_index_does_not_ride_along():
    """`folds` is a list of vertex indices and `plane_ids` one id per face, and
    cleaning rebuilds both indexings. Carried over they name the wrong geometry:
    on the live bake the raw skin's fold vertex 33 and the cleaned mesh's are
    2.6 m apart. Dropped rather than remapped, so a reader gets nothing rather
    than something wrong."""
    quad = _mesh(_sheet([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]))
    quad.metadata.update(
        {"offset_distance": 0.008, "folds": [3], "plane_ids": "cache"}
    )
    out = clean(quad)

    assert out.metadata["offset_distance"] == 0.008
    assert "folds" not in out.metadata and "plane_ids" not in out.metadata


def test_an_empty_mesh_cleans_to_an_empty_mesh():
    """A skin whose rules select nothing is a real case — the brick skin would
    be exactly that until a part is stamped brick — and it must not be an error."""
    empty = trimesh.Trimesh(
        vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64), process=False
    )
    out = clean(empty)

    assert out.vertices.shape == (0, 3) and out.faces.shape == (0, 3)
    assert out.metadata["overlap_removed"] == 0.0
