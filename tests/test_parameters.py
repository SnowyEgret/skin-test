"""The parameter layer: the file is the source, and it fails loudly at the seam."""

import copy

import numpy as np
import pytest
import trimesh

from skin import parameters, skin_over, substrate


def _params():
    return parameters.load_validated()


def test_the_committed_file_is_valid_and_non_degenerate():
    """The regression check on the file itself, not on a fixture."""
    params = _params()
    assert {"classify", "fall", "skins"} == set(params)
    assert [s["name"] for s in params["skins"]] == ["Membrane", "Cladding"]


def test_a_missing_knob_is_refused_by_name():
    """STRICT-COMPLETE: no built-in defaults, so an absent knob is an error and
    never a quietly-supplied value."""
    params = _params()
    del params["classify"]["aspect"]
    with pytest.raises(parameters.ParameterError) as raised:
        parameters.validate(params)
    assert "classify" in str(raised.value) and "aspect" in str(raised.value)


def test_a_misspelt_knob_is_refused_rather_than_ignored():
    """`additionalProperties: false` everywhere. A typo that merely fell through
    would leave the real knob at whatever the code happened to do."""
    params = _params()
    params["skins"][0]["distence"] = 0.02
    with pytest.raises(parameters.ParameterError, match="skins/0"):
        parameters.validate(params)


def test_an_out_of_range_knob_is_refused():
    params = _params()
    params["fall"] = 1.4  # not a direction cosine, so no face could ever match
    with pytest.raises(parameters.ParameterError, match="fall"):
        parameters.validate(params)


def test_equal_distances_are_refused_as_degenerate_seeds():
    """The 2026-08-14 bug class: `Membrane.drop` and `Cladding.distance` were both
    0.100, so swapping a skirt depth for an offset produced identical geometry."""
    params = _params()
    params["skins"][0]["drop"] = params["skins"][1]["distance"]
    with pytest.raises(parameters.ParameterError, match="non-degenerate"):
        parameters.check_seeds(params)


def test_an_integer_multiple_is_refused_as_a_degenerate_seed():
    params = _params()
    params["skins"][1]["distance"] = 2 * params["skins"][0]["distance"]
    with pytest.raises(parameters.ParameterError) as raised:
        parameters.check_seeds(params)
    assert "2x" in str(raised.value)


def test_a_zero_out_is_exempt_from_the_seed_rule():
    """Zero is an integer multiple of everything, and means the turn-out is off
    rather than seeded — so the committed file, which has one, must pass."""
    params = _params()
    assert params["skins"][1]["out"] == 0.0
    parameters.check_seeds(params)  # does not raise


def test_a_skin_without_a_base_is_refused_rather_than_left_untrimmed():
    """STRICT-COMPLETE reaches the trim datum too. `null` says "this skin is not
    trimmed" out loud, and an omitted `base` must not be allowed to mean the
    same thing quietly — that is the hidden default the rule exists to abolish."""
    params = _params()
    del params["skins"][1]["base"]
    with pytest.raises(parameters.ParameterError, match="skins/1"):
        parameters.validate(params)


def test_a_base_is_a_datum_and_not_a_seed():
    """`base` is a height in the model rather than a distance between two
    surfaces, so the non-degenerate rule does not reach it: trimming the cladding
    at the same number some skin is offset by makes no bug invisible. The
    committed 0.0 also has to survive, and would not if `base` were seeded."""
    params = _params()
    assert params["skins"][1]["base"] == 0.0
    parameters.check_seeds(params)

    params["skins"][1]["base"] = params["skins"][0]["distance"]
    parameters.check_seeds(parameters.validate(params))  # neither raises


def test_a_skin_with_no_rule_set_cannot_be_built():
    from build import skins

    params = _params()
    params["skins"][0]["name"] = "Parapet"
    with pytest.raises(parameters.ParameterError, match="no rule set"):
        skins(params)


def test_a_rule_set_no_skin_names_is_refused():
    """Otherwise it sits there looking maintained while emitting nothing."""
    from build import skins

    params = _params()
    params["skins"] = params["skins"][:1]
    with pytest.raises(parameters.ParameterError, match="Cladding"):
        skins(params)


def test_a_skin_that_cannot_lap_in_any_direction_is_refused():
    """`drop` and `out` are the two directions a lap can take. With both zero a
    skin would stop dead on every arris it reaches, which is a skin nobody asked
    for and almost certainly a parameter file with a hole in it.

    This replaces the old `out` vs `turn_out` cross-check, which asked whether
    the rule set defined a turn-out. There is no turn-out any more: `_lap` reads
    the direction off the substrate, so a skin no longer declares which way it
    continues -- only how far, and a distance of zero switches that way off.
    """
    from build import skins

    params = _params()
    params["skins"][0]["drop"] = 0.0
    params["skins"][0]["out"] = 0.0
    with pytest.raises(parameters.ParameterError, match="no lap in any direction"):
        skins(params)

    # either one alone is fine: the cladding has no turn-out and never did
    params = _params()
    params["skins"][1]["out"] = 0.0
    assert skins(params)



def test_a_supplied_params_dict_is_validated_too():
    """The what-if path is *where* an unchecked knob arrives — someone hand-edits
    a copy and passes it. Before `parameters.resolve`, `build(params=...)` with
    `fall: 1.4` built and wrote both skins with no error: separation 64.215 mm →
    558.849 mm. `check_facades` missed it as well, because `fall > 1` empties the
    exterior set and "every facade is claimed" then holds vacuously.
    """
    from build import build, current_substrate, skins

    params = _params()
    params["fall"] = 1.4  # rejected by the schema; must be rejected here too
    for call in (
        lambda: skins(params),
        lambda: build(current_substrate(), params=params),
    ):
        with pytest.raises(parameters.ParameterError, match="fall"):
            call()


def test_an_aspect_of_one_cannot_switch_the_block_like_guard_off():
    """`classify` raises when `extents[0] > aspect * extents[1]` and `extents` is
    sorted ascending, so `aspect = 1` makes that test unreachable — a 1x1x1 cube
    classifies as a wall. CLAUDE.md: do not add a fallback that picks a side.
    """
    from skin.substrate import AmbiguousPart, classify

    params = _params()
    params["classify"]["aspect"] = 1.0
    with pytest.raises(parameters.ParameterError, match="aspect"):
        parameters.validate(params)

    # and the value really is the off switch the schema now excludes
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    assert classify(cube, margin=0.05, aspect=1.0) == substrate.WALL  # wrong
    with pytest.raises(AmbiguousPart):
        classify(cube, margin=0.05, aspect=0.85)  # right


def test_the_authored_numbers_actually_reach_the_geometry():
    """A parameter file nothing reads is worse than a constant. Change the offset
    in a copy and the built skin has to move by exactly that much."""
    from build import _skin_from, current_substrate, skins

    parts = current_substrate()
    params = _params()
    membrane = skins(params)[0]

    louder = copy.deepcopy(params)
    louder["skins"][0]["distance"] = 0.037  # still a non-degenerate seed
    parameters.check_seeds(louder)
    moved = skins(louder)[0]

    assert moved["distance"] == 0.037
    a = _skin_from(membrane, parts)
    b = _skin_from(moved, parts)
    # the vertical planes are offset exactly, so their extents differ by 2 x delta
    delta = 0.037 - membrane["distance"]
    assert np.isclose(b.extents[0] - a.extents[0], 2 * delta, atol=1e-9)


def test_faces_has_no_default_classifier():
    """The thresholds are authored, so `Faces` cannot supply a pair of its own —
    it raises at the first predicate that asks what a part is."""
    from skin.offset import Faces, _owner

    parts = [substrate.cube(2.0)]
    body = trimesh.boolean.union(parts)
    faces = Faces(body, parts, _owner(body, parts))

    with pytest.raises(ValueError, match="no classifier"):
        faces.of_role(substrate.WALL)


def test_skin_over_needs_no_classifier_when_nothing_asks_for_a_role():
    """A plain closed-shell offset selects no faces, so no predicate runs."""
    parts = [substrate.cube(2.0)]
    assert skin_over(parts, 0.1).is_watertight
