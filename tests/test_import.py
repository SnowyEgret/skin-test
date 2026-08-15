"""Reading a substrate from OBJ — the import path for geometry too large to
transcribe. Every check here is one the student-house export will actually meet."""

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


def test_a_face_the_fan_cannot_tile_is_refused_by_name(tmp_path):
    """`polyhedron` fan-triangulates, which is faithful only for a loop that is
    star-shaped from its first vertex. A baked wall with a notch is not, and a
    silently inverted triangle inside a substrate is close to undebuggable.

    Signed triangle areas telescope to the true polygon area whatever the shape,
    so area cannot detect this — the test is that no triangle is inverted.
    """
    u = np.array(  # a U in plan: star-shaped from no vertex at all
        [[0, 0, 0], [3, 0, 0], [3, 3, 0], [2, 3, 0],
         [2, 1, 0], [1, 1, 0], [1, 3, 0], [0, 3, 0]], dtype=float,
    )
    assert not substrate._fan_is_valid(u)
    assert substrate._fan_is_valid(u[[0, 1, 2, 7]])  # a convex quad of the same loop

    path = tmp_path / "notched.obj"
    path.write_text(
        "o Notched\n"
        + "".join(f"v {x:g} {y:g} {z:g}\n" for x, y, z in u)
        + "f 1 2 3 4 5 6 7 8\n"
    )
    with pytest.raises(ValueError, match="'Notched' has a 8-sided face"):
        substrate.from_obj(path)


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
    # one part needs no union at all, and is passed straight through
    only = substrate.cube(2.0)
    assert substrate.union([only]) is only


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

    # the wedge itself, transcribed off the union and moved to the origin. A
    # made-up sliver will not do: an acute plan wedge saturates at a bounded
    # displacement, because `_vertex_normals` snaps its near-parallel faces onto
    # the axis and they become an opposing pair the solve simply averages. This
    # one has four mutually skew planes and no such rescue. 254 mm across, 29 mm
    # tall, 5.8e-10 m^3 of volume.
    sliver = trimesh.Trimesh(
        vertices=np.array([[0.005647, 0.248100, 0.000000],
                           [0.000000, 0.253747, 0.011479],
                           [0.253747, 0.000000, 0.000000],
                           [0.253747, 0.000000, 0.028999]]),
        faces=np.array([[1, 0, 3], [2, 3, 0], [1, 2, 0], [1, 3, 2]]),
        process=False,
    )
    assert sliver.is_watertight
    with pytest.raises(ValueError, match="offset is undetermined at vertex"):
        planar_offset(sliver, 0.02)


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
