"""The parameter layer — the tunable numbers, out of the code and into a file
validated against a JSON Schema.

Shaped deliberately after the student-house `bim/phase1/parameters.py`, because
this module is going back into that repo. Three things are copied from it:

* **STRICT-COMPLETE** (Duncan, 2026-06-11): the file specifies *every* knob. No
  built-in defaults, no partial overlay — a hidden default is exactly what masks
  a bug. A what-if is a full, diffable copy of the file.
* **The split of duties.** The JSON Schema enforces per-field validity (types,
  ranges, `required`, `additionalProperties: false`); the cross-field residue a
  schema cannot express stays in Python — `check_seeds` here, and the
  name-to-rule join in `build.py`.
* **Fail at the seam, addressed.** Every raise names the offending field, so an
  error points at the line to edit rather than at the geometry that consumed it.

The file may be JSON or YAML (JSON is valid YAML, so `yaml.safe_load` reads
either). Pure Python — no Blender, and nothing here imports trimesh.

**Nothing under `skin/` other than this module imports `yaml` or `jsonschema`,
and nothing takes a path.** The core takes a params *dict*, the way the
student-house's `skin_pipeline.run` takes a `topo` dict: sub-modules there read
`topo["cladding"]["allowance"]` and never parse anything. That is the whole
integration seam. On migration the `classify`/`fall`/`skins` block moves into
`student-house-parameters.yaml` under a `skin:` key, its schema is pasted into
that repo's schema, and the caller passes `topo["skin"]` where `build.py` passes
`load_validated()`. This module is then dead code there and should be deleted,
not ported — the student-house already owns the read.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = _REPO_ROOT / "skin-parameters.yaml"
SCHEMA_PATH = _REPO_ROOT / "skin-parameters.schema.json"


class ParameterError(ValueError):
    """A malformed or incomplete parameter set — raised at the seam, addressed."""


def load(path=DEFAULT_PATH) -> dict:
    """Parse the parameter file (JSON or YAML) into a plain dict. No validation."""
    with open(path) as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ParameterError(f"parameter file at {str(path)!r} did not parse to a mapping")
    return data


def _schema() -> dict:
    with open(SCHEMA_PATH) as handle:
        return json.load(handle)


def validate(params: dict) -> dict:
    """Validate against the JSON Schema, naming the offending field. Returns
    `params` unchanged, so it composes: `validate(load(path))`."""
    try:
        jsonschema.validate(params, _schema())
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        raise ParameterError(f"parameter {where}: {exc.message}") from None
    return params


def check_seeds(params: dict) -> dict:
    """Every skin distance non-degenerate, or raise. Returns `params` unchanged.

    A hard rule carried over from the student-house: no two of the distances are
    equal and none is an integer multiple of another. `Membrane.drop` and
    `Cladding.distance` were both 0.100 until 2026-08-14, which meant a bug that
    swapped a skirt depth for an offset distance produced *identical* geometry —
    invisible to the tests and to the eye. Degenerate seeds do not make the model
    wrong, they make a whole class of wrongness unobservable.

    A **zero distance** is exempt on both counts, whichever of the three it is.
    It means the feature is switched off rather than a distance being seeded —
    the cladding has no turn-out, the masonry no drip — and zero is an integer
    multiple of everything, so including it would fail every file that has one.
    (This said "a zero `out`" until 2026-08-26, and the loop never distinguished
    them; `Masonry.drop` is authored `0.0` beside `Cladding.out`, so the two
    would collide as equal seeds if it had. Found on review.)

    `base` and `close` are not seeds and are not read here, which is why the keys
    are listed rather than taken from the entry: `base` is a datum in the model
    and `close` a bound on a cleanup, so neither is a distance between two
    surfaces that a bug could swap for another.

    The top-level `reveal` **is** one and is read, because it is exactly that: a
    distance between the skin and a substrate face it dies against. It is what
    the rule above cost something to keep — 0.016 was asked for on 2026-08-27 and
    is refused as 2x `Membrane.distance`, and Duncan authored 0.018 rather than
    move the membrane off 8 mm. Do not exempt it to make a round number fit; the
    exemptions here are for values that are not distances between two surfaces,
    and this one is.

    This is a seeding discipline for a test rig, not a code requirement, so it is
    a named function the caller opts into rather than part of `validate`. A
    production what-if that genuinely wants two skins 100 mm apart calls
    `validate` alone and says so.
    """
    if "reveal" not in params:
        raise ParameterError(
            "parameter reveal: missing — it is a seed like a skin distance, so "
            "`check_seeds` reads it. Add it to the file, or call `validate` alone"
        )
    # No zero exemption, unlike the per-skin distances: `reveal` has no "off"
    # state to mean. A skin either stops at the joint or does not reach one, so
    # zero is a malformed file rather than a feature switched off — and it is
    # refused *here*, by name, rather than left to the schema's
    # `exclusiveMinimum: 0`. This function is documented as a standalone opt-in
    # a caller may run without `validate`, so the schema is not the guard on
    # this path: before the raise, a zero reached the multiples loop below as a
    # divisor and came back `ZeroDivisionError`. Found on review, 2026-08-27
    reveal = float(params["reveal"])
    if reveal <= 0.0:
        raise ParameterError(
            f"parameter reveal={reveal} is not a distance — unlike a skin's `drop` "
            f"or `out` it has no off state, so zero is a malformed file rather "
            f"than a feature switched off"
        )
    seeds = {reveal: "reveal"}
    for skin in params["skins"]:
        for key in ("distance", "drop", "out"):
            value = float(skin[key])
            if value == 0.0:
                continue
            where = f"skins.{skin['name']}.{key}"
            if value in seeds:
                raise ParameterError(
                    f"parameter {where}={value} equals {seeds[value]} — skin distances "
                    f"must be non-degenerate seeds, or a bug that swaps one for the "
                    f"other produces identical geometry and is invisible"
                )
            seeds[value] = where

    for value, where in seeds.items():
        for other, other_where in seeds.items():
            if other >= value:
                continue
            ratio = value / other
            if abs(ratio - round(ratio)) < 1e-9:
                raise ParameterError(
                    f"parameter {where}={value} is {round(ratio)}x {other_where}"
                    f"={other} — skin distances must be non-degenerate seeds, or a bug "
                    f"that scales one into the other is invisible"
                )
    return params


def resolve(params: dict | None = None, path=DEFAULT_PATH) -> dict:
    """A **validated** params dict, from the caller's dict or from the file.

    Every entry point that accepts a `params` argument goes through this, because
    a caller-supplied dict is exactly where an unchecked knob arrives: the
    what-if workflow is "hand-edit a copy and pass it", and a dict that skipped
    the schema is a dict that skipped the whole layer. Measured before this
    existed: `build(params=...)` with `fall: 1.4` — a value `validate` rejects —
    built and wrote both skins, separation 64.215 mm → 558.849 mm, no error.
    `check_facades` did not catch it either, because `fall > 1` empties the
    exterior set and "every facade is claimed" then holds vacuously.

    `check_seeds` is deliberately *not* run here: it is a discipline for this rig
    rather than a requirement, so a caller who wants two skins 100 mm apart can
    pass a dict that fails it. Reading the file still applies it — see
    `load_validated`, which is what the default path uses.
    """
    return load_validated(path) if params is None else validate(params)


def load_validated(path=DEFAULT_PATH, seeds: bool = True) -> dict:
    """Load, validate and (by default) seed-check the file at `path`.

    The single entry `build.py` calls, and the analogue of the student-house's
    `parameters.load_merged` — minus the merge, because this rig has no separate
    structure file for the numbers to be injected into. The parameter block *is*
    the whole layer here.
    """
    params = validate(load(path))
    return check_seeds(params) if seeds else params
