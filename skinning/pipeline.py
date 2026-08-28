#!/usr/bin/env python3
"""Substrate in, skins out — the seam a caller integrates against.

Three layers meet here. `skinning.skin` offsets a body and knows nothing about
buildings; `skinning.rules` says what a wall is and which faces each skin
covers; this module runs the one over the other. It reads no file, writes no
file and prints nothing, so what a caller does with the result — write OBJ,
report on it, hand it to Blender — stays the caller's business. `build.py` at
the root of this repo is one such caller and is not part of the package; in the
student-house the caller is `skin_pipeline.run`.

`prepare` is the half that has to happen before any role is read: the grouping,
the union, and the `Faces` view over it. It is exposed on its own because three
call sites wanted exactly it and each had grown its own copy.

`run` is the whole of it. It returns one result per **authored** skin, in the
order the parameter file names them, rather than only the ones that built —
a skin whose rules select no face of this substrate is a real condition and its
caller has to be able to say so out loud (see `covered`). That is what `mesh is
None` marks, and it is the only shape a result takes with no geometry in it:
nothing here ever hands on an empty mesh, because `clean`, `clearance`,
`buried`, `separation` and `write_obj` all raise on one.

Each result carries **both** meshes, and the split is load-bearing rather than
convenience. `raw` is what the offset produced and is what every measurement is
a property of; `mesh` is what ships, with the coplanar double cover dissolved
and any tear gusseted. `clearance` samples face centroids, so re-triangulating
moves the samples and would quietly change a verdict with no surface moving —
measured 2026-08-21 at 63.9999 -> 84.1503 mm. See CLAUDE.md, "Cleaning a mesh".
"""

from __future__ import annotations

from collections.abc import Iterator

from .rules import check_cladding, check_facades, classifier, group_caps, group_cornices, skins
from .skin import parameters, skin_over, substrate
from .skin.clean import clean
from .skin.offset import Faces, _owner


def _params(params) -> dict:
    """The caller's parameter dict, validated — the guard both entry points take.

    Two failures, and neither says anything useful if it is left to surface on
    its own. A `None` reaches `classifier` as `None["classify"]` and raises a
    `TypeError` naming nothing; on migration that `None` is a missing
    `topo["skin"]`. And an *unvalidated* dict is worse than either, because it
    does not raise at all: `parameters.resolve`'s docstring records `fall: 1.4`
    building and writing both skins with the separation 64.215 -> 558.849 mm and
    `check_facades` passing vacuously, which is the whole reason that layer
    exists. So every entry here validates, and validates a dict — never a path,
    and never `None` to be filled in from the committed file. `parameters.validate`
    rather than `resolve`, because `resolve(None)` reads `skin-parameters.yaml`
    off disk and this module reads no file.
    """
    if not isinstance(params, dict):
        raise TypeError(
            f"pipeline needs a validated parameter dict, not {type(params).__name__} "
            f"— call skinning.skin.parameters.load_validated() (or resolve()) and pass the result"
        )
    return parameters.validate(params)


def prepare(parts: list, params: dict) -> Faces:
    """Group the substrate, union it, and return the `Faces` view of the result.

    Everything that has to happen before a role is read, in the one order that
    works. `parts` is **mutated** — the two grouping passes re-stamp
    `metadata["object"]` — and is otherwise untouched: the union is a throwaway
    used only to find the outer surface, and the substrate stays the substrate.

    Guarded on its own account rather than trusting `run` to have done it: this
    is an advertised entry point and `audit.py` already calls it directly.
    """
    params = _params(params)
    # before anything reads a role: a separately-authored cap plate is not a
    # roof, it is the top of the wall it caps, and a cornice is not a slab, it is
    # the band standing proud of one. Cornices first, because `group_caps`
    # classifies every element up front and a lone cornice is exactly what
    # `classify` refuses. Both are idempotent, so a substrate that already groups
    # them is untouched
    group_cornices(parts)
    group_caps(parts, classifier(params))
    body = substrate.union(parts)
    faces = Faces(body, parts, _owner(body, parts), classifier(params))
    check_facades(faces, params["fall"])
    check_cladding(faces, params["fall"])
    return faces


def run(parts: list, params: dict) -> tuple[Faces, Iterator[dict]]:
    """Every skin this substrate poses: `(faces, results)`.

    One result per authored skin, in parameter-file order:

        {"name": str, "spec": dict, "raw": Trimesh | None, "mesh": Trimesh | None}

    `raw` is the offset as `skin_over` emitted it and `mesh` is that cleaned —
    see the module docstring for why both survive. Both are `None` where this
    substrate poses no face the skin's rules select; the caller decides what to
    say about that.

    `results` is an **iterator**, and lazily so on purpose. The rig's loudest
    failures are raises from inside the solve — `_reconcile` refusing a fold,
    `planar_offset` refusing a runaway vertex — and building the whole set before
    handing any of it back means a caller that reports per skin prints nothing at
    all when the second one raises. Streaming, it has already printed the first
    skin's residual, clearance and folds, which is the reading that says what the
    substrate did differently. `faces` is returned eagerly beside it, because
    `prepare` has to have run before the first skin can be built anyway.

    `params` is a validated params dict, never a path. `build.py` passes
    `parameters.load_validated()`; the student-house passes `topo["skin"]`.
    """
    params = _params(params)
    # the name join before any geometry: `skins` is where a parameter file and
    # `RULES` are checked against each other, and it must fail before `prepare`
    # re-stamps `metadata["object"]` on the caller's parts
    specs = skins(params)
    faces = prepare(parts, params)
    return faces, _each(specs, faces, parts)


def _each(specs, faces, parts):
    """The per-skin half of `run`, split out only so that `run` itself is eager.

    A generator function runs no line of its body until it is iterated, so with
    this inlined the guard and the name join above would not fire until the
    caller asked for the first skin — and a bad parameter dict would be reported
    from wherever that happened to be rather than from the call.
    """
    for spec in specs:
        # a skin whose rules select nothing on this substrate is skipped rather
        # than built. See `covered` -- it is a real condition, not a defect: the
        # masonry needs a wall a cornice finishes and two of the three
        # substrates here have none
        if not covered(spec, faces):
            yield {"name": spec["name"], "spec": spec, "raw": None, "mesh": None}
            continue
        raw = _skin_from(spec, parts)
        # the lap rule legitimately covers part of a plane twice, and `clean`
        # dissolves that. Kept beside the raw emission rather than replacing it,
        # because a measurement is a property of the offset and a verdict is a
        # statement about what ships
        mesh = clean(raw, dissolve=True, close=spec["close"])
        yield {"name": spec["name"], "spec": spec, "raw": raw, "mesh": mesh}


def _skin_from(spec, parts):
    """Build one skin from its spec — every `skin_over` argument, none defaulted.

    There is deliberately no `distance` override: a spec now carries `offsets`
    as well, and `planar_offset` reads that in preference for every plane, so an
    override would have moved the laps and the reported distance while leaving
    the surface where the spec put it. A what-if is a different spec —
    `dict(spec, distance=...)` — which is how every caller already writes one.
    Found on review, 2026-08-26; nothing passed it.
    """
    return skin_over(
        parts,
        spec["distance"],
        keep=spec["keep"],
        lap=spec["lap"],
        drop=spec["drop"],
        out=spec["out"],
        base=spec["base"],
        classify=spec["classify"],
        offsets=spec["offsets"],
    )


def covered(spec, faces) -> bool:
    """Does this skin's rule set select any face of this substrate?

    A skin whose `keep` selects nothing cannot be built: `skin_over` offsets an
    empty selection to an empty mesh, and every measurement downstream of it
    then fails on a shape of `(0,)` — `clean`, `clearance`, `buried`,
    `separation` and `write_obj` were all tried and all raise. With `base` set
    it does not even get that far; the trim raises first, saying the datum is
    wrong when the datum is fine.

    This is a real condition and not a defect. The masonry skin needs a wall a
    cornice finishes, and only one of the three substrates here has one — the
    rig and `headhouse-walls-parapets-caps-clt-insulation.obj` carry no cornice
    at all, and must still build. So `run` asks first and hands the caller a
    result with no mesh in it, rather than crashing on two of three substrates
    or, worse, dropping a skin quietly. The name is still joined to `RULES` and
    still seed-checked; what it does not do is emit an empty file. Saying so out
    loud is then the caller's job — `build.py` prints a line naming the skin.
    """
    return bool(spec["keep"](faces).any())
