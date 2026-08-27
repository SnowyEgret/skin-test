"""The build's verdict: `intersects` and `buried`.

`clearance` was the verdict until 2026-08-25 and is now a printed number.
Duncan's decision, and the reason is that it answered a question about the
*sampling* rather than about the geometry: it could not tell a skin that
deliberately stops short of something standing proud of a wall from one folded
through itself, and cleaning a skin moved its answer 63.9999 -> 84.1503 mm
without moving any surface. These two replace it. See NOTES, "The clearance
verdict".
"""

import numpy as np
import trimesh

from skin import buried, intersects


def _box(extents, at=(0.0, 0.0, 0.0)):
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(at)
    return box


def test_two_surfaces_that_pass_through_each_other_are_counted():
    a, b = _box((1, 1, 1)), _box((1, 1, 1), (0.3, 0.37, 0.41))
    assert intersects(a, b) > 0
    # a T, the plainest surface crossing there is
    assert intersects(_box((2, 2, 0.01)), _box((0.01, 2, 2))) > 0


def test_surfaces_that_only_touch_are_not_a_crossing():
    """The condition this has to get right, because it is the *designed* one.

    Both skins cap a wall and a lap lands flush on the face it laps onto, so
    contact between two skins is ordinary. A verdict that fires on the intended
    geometry is exactly what `clearance` was demoted for. Touching along a face,
    an edge and a corner are all contact and none of them is a crossing.
    """
    a = _box((1, 1, 1))
    assert intersects(a, _box((1, 1, 1), (1.0, 0, 0))) == 0     # face to face
    assert intersects(a, _box((1, 1, 1), (1.0, 1.0, 0))) == 0   # along an edge
    assert intersects(a, _box((1, 1, 1), (1.0, 1.0, 1.0))) == 0  # at a corner
    assert intersects(a, _box((1, 1, 1), (5.0, 0, 0))) == 0     # nowhere near
    # one surface resting along the boundary edge of another. The shared segment
    # is interior to one triangle and on the boundary of the other, which is why
    # `_cross` asks for the interior of **both**
    assert intersects(_box((2, 2, 0.01)), _box((0.01, 2, 2), (0, 0, 1.005))) == 0


def test_a_crossing_on_the_lattice_is_not_missed():
    """Axis-aligned surfaces meeting exactly on shared edges.

    The substrate is snapped to 1 µm and almost every face is axis-aligned, so
    a crossing landing exactly on another mesh's triangle boundary is the normal
    case here rather than a curiosity. An earlier edge-piercing test excluded
    the boundary and read **zero** on both of these (found on review,
    2026-08-25); the interval overlap that replaced it has no such choice.
    """
    a = _box((1, 1, 1))
    assert intersects(a, _box((1, 1, 1), (0.5, 0.5, 0.0))) > 0
    assert intersects(a, _box((1, 1, 1), (0.5, 0.5, 0.5))) > 0


def test_coplanar_overlap_is_not_a_crossing():
    """Two sheets in one plane lie on each other rather than through each other.

    The knife condition `clean._sheets` exists for. Decided by **distance**, not
    by the angle between the normals: a sliver's normal is noisy where its
    vertices are not, and the clean pass leaves a 0.13 x 275 mm triangle in the
    membrane whose normal is 1.4e-11 off its plane's. An angle test read three
    bogus self-crossings off exactly that.
    """
    assert intersects(_box((2, 2, 0.01)), _box((1, 1, 0.01))) == 0
    sliver = trimesh.Trimesh(
        vertices=np.array([[0.0, 0, 0], [1e-4, 0, 0], [1e-4, 0, -0.275],
                           [0.0, 0, -0.275]]),
        faces=np.array([[0, 1, 2], [0, 2, 3]]),
        process=False,
    )
    assert intersects(sliver, sliver) == 0


def test_a_sound_surface_does_not_cross_itself():
    assert intersects(_box((1, 1, 1)), _box((1, 1, 1))) == 0
    a = _box((1, 1, 1))
    assert intersects(a, a) == 0                                # `a is b` path


def test_two_triangles_sharing_one_corner_can_still_pierce():
    """A lap folding back through the panel it springs from shares the arris.

    Skipping every pair with a corner in common — rather than only those sharing
    an **edge** — made `intersects(skin, skin)` blind to 553 of the live
    membrane's 1157 candidate pairs. Found on review, 2026-08-25.
    """
    flat = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], float)
    through = np.array([[0, 0, 0], [0.8, 0.5, -0.5], [0.8, 0.5, 0.5]], float)
    mesh = trimesh.Trimesh(
        vertices=np.vstack([flat, through]),
        faces=np.array([[0, 1, 2], [3, 4, 5]]),
        process=False,
    )
    assert intersects(mesh, mesh) > 0

    # ...while two that meet only at that corner are still not a crossing
    aside = np.array([[0, 0, 0], [-1, 0, 1], [-1, 1, 1]], float)
    touching = trimesh.Trimesh(
        vertices=np.vstack([flat, aside]),
        faces=np.array([[0, 1, 2], [3, 4, 5]]),
        process=False,
    )
    assert intersects(touching, touching) == 0


def test_a_crossing_survives_re_triangulation():
    """The whole reason this replaced `clearance`.

    `clearance` samples face centroids, so subdividing a surface moves its
    samples and can move its verdict with nothing else changed. A crossing is a
    property of the surfaces, so subdividing must not change whether there is
    one.
    """
    a, b = _box((1, 1, 1)), _box((1, 1, 1), (0.3, 0.37, 0.41))
    before = intersects(a, b)
    fine = a.subdivide().subdivide()
    assert intersects(fine, b) > 0 and before > 0
    apart = _box((1, 1, 1), (5.0, 0, 0))
    assert intersects(a, apart) == intersects(a.subdivide(), apart) == 0


def test_buried_is_signed_where_a_distance_is_not():
    """A vertex inside a part reads as a small positive gap to `clearance`.

    `closest_point` returns an unsigned distance, so a skin driven *into* the
    substrate can read a perfectly healthy clearance. This is the half of the
    verdict that catches it, and it is why the substrate case does not lean on
    `intersects`' boundary handling.
    """
    big = _box((4, 4, 4))
    assert buried([big], _box((1, 1, 1))) > 0          # wholly swallowed
    assert buried([big], _box((1, 1, 1), (10, 0, 0))) == 0
    assert buried(big, _box((1, 1, 1))) > 0            # a bare mesh, not a list


def test_buried_samples_centroids_as_well_as_vertices():
    """A panel driven through a part with both ends outside it.

    Sampling vertices alone misses this, and it is not a contrived shape: it is
    a lap crossing a wall it should have been cut to.
    """
    part = _box((1.0, 4, 4))     # x in [-0.5, 0.5]; the quad's corners sit at x = +-1
    panel = trimesh.Trimesh(
        vertices=np.array([[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0],
                           [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0]]),
        faces=np.array([[0, 1, 2], [0, 2, 3]]),
    )
    assert not part.contains(panel.vertices).any()      # no vertex is inside
    assert buried([part], panel) > 0                    # a centroid is


def test_a_sample_on_a_part_surface_is_not_buried_in_it():
    """A skin that dies *on* the substrate is where it was asked to be.

    `build.facade_offsets`' "the outer system owns the corner" branch offsets a
    facade by **zero**, which puts the skin's vertices in a substrate face
    deliberately — so this is an ordinary reading and not an edge case.
    `trimesh.contains` cannot answer it: it casts a ray in a random direction,
    and where the sample sits on a plane two parts share, the ray resolves
    whichever way it happens to leave. The fixture below reads 6 and 0 in
    alternate runs without it, and the build's own verdict came back 3 and 4
    over one fixed cladding mesh. A verdict that moves without the geometry
    moving is exactly what `clearance` was demoted for.

    The tolerance is the **union's** accuracy floor, not a weld radius: a skin
    vertex is placed off a face of the union, which manifold3d computes in
    float32, so one meant to lie exactly in a substrate plane arrives up to
    ~5e-7 m either side of it. The sample that flapped on the live deck sat
    6.390e-07 m from `CapPlate-Deck9-N`, on the plane its cornice shares.
    """
    lower = _box((2.0, 2.0, 2.0))                       # z in [-1, 1]
    upper = _box((2.0, 2.0, 0.6), (0.0, 0.0, 1.3))      # z in [1, 1.6]
    parts = [lower, upper]                              # sharing the plane z = 1
    on = trimesh.Trimesh(                               # a quad lying on it
        vertices=np.array([[-0.5, -0.5, 1.0], [0.5, -0.5, 1.0],
                           [0.5, 0.5, 1.0], [-0.5, 0.5, 1.0]]),
        faces=np.array([[0, 1, 2], [0, 2, 3]]),
    )
    assert buried(parts, on) == 0

    # ...and so is one 0.64 µm under it, which is the reading that flapped
    noise = on.copy()
    noise.apply_translation((0.0, 0.0, -6.39e-7))
    assert len({buried(parts, noise) for _ in range(12)}) == 1, "the verdict flaps"
    assert buried(parts, noise) == 0

    # ...while a sample a millimetre under still is buried. This narrows the
    # reading to the surface itself; it does not blunt it
    under = on.copy()
    under.apply_translation((0.0, 0.0, -0.001))
    assert buried(parts, under) == len(under.vertices) + len(under.faces)
