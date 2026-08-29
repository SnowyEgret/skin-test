#!/usr/bin/env python3
"""Build the geometry headless into build/. Blender only ever loads the result.

This is the rig: the transcribed `PART_N` substrate, the OBJ emission and the
printed report. None of it migrates, and none of it is in the package. What does
is `skinning.rules` — every derivation, and the join from the authored numbers to
it — and `skinning.pipeline`, which runs one over the other and is the seam a
caller integrates against. Everything below is a caller of that seam.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import trimesh

from skinning import pipeline
from skinning.rules import FACADE, RAINSCREEN, RULES, TOL, UNSURVEYED
from skinning.skin import (
    buried, clearance, intersects, parameters, separation, substrate, write_obj,
)

BUILD_DIR = Path(__file__).parent / "build"


# Transcribed from the Blender scene, snapped to 1 um. Both parts have sloped
# tops: high edges at z = 2.053892, low edges at z = 1.953892, both horizontal.
# Part 1 carries the hip — its corner face is coplanar with part 2's top.
PART_1 = (
    [(-3.069769, -3.029931, 0.0), (-3.069769, -3.029931, 1.953892),
     (-3.069769, -1.897401, 0.0), (-3.069769, -1.897401, 2.053892),
     (1.573496, -3.029931, 0.0), (1.573496, -3.029931, 2.053892),
     (1.573496, -1.897401, 0.0), (1.573496, -1.897401, 2.053892),
     (0.740966, -3.029931, 1.953892)],
    [[0, 1, 3, 2], [4, 5, 8, 1, 0], [0, 2, 6, 4], [5, 7, 8],
     [2, 3, 7, 6], [6, 7, 5, 4], [7, 3, 1, 8]],
)
PART_2 = (
    [(0.740966, -7.673195, 0.0), (0.740966, -7.673195, 1.953892),
     (0.740966, -3.029931, 0.0), (0.740966, -3.029931, 1.953892),
     (1.573496, -7.673195, 0.0), (1.573496, -7.673195, 2.053892),
     (1.573496, -3.029931, 0.0), (1.573496, -3.029931, 2.053892)],
    [[0, 1, 3, 2], [4, 5, 1, 0], [0, 2, 6, 4], [5, 7, 3, 1],
     [2, 3, 7, 6], [6, 7, 5, 4]],
)


# Part 3 fills the L's inner quadrant, so the plan becomes a full rectangle. Its
# top is NOT one plane: three corners at z = 1.456084, one at 1.156084, i.e. 300 mm
# out of plane, so it is two triangles meeting on a sloping diagonal. It also sits
# lower than parts 1 and 2, which leaves vertical step faces standing above it.
PART_3 = (
    [(-3.069769, -3.029931, 1.456084), (0.740966, -3.029931, 1.456084),
     (-3.069769, -3.029931, 0.0), (0.740966, -3.029931, 0.0),
     (0.740966, -7.673195, 1.456084), (-3.069769, -7.673195, 0.0),
     (0.740966, -7.673195, 0.0), (-3.069769, -7.673195, 1.156084)],
    [[0, 1, 3, 2], [2, 3, 6, 5], [5, 6, 4, 7], [7, 4, 1],
     [2, 5, 7, 0], [6, 3, 1, 4], [0, 7, 1]],
)


# Part 4 is a tall wall standing along the whole -Y edge, on the far side of it:
# it abuts parts 2 and 3 on the plane y = -7.673195 and overhangs +X past part 2.
# Its top slopes away from the substrate, 4.105916 at the inner edge down to
# 4.045916 at the outer; both those edges are horizontal.
#
# Transcribed from the object named "Cube", which carries a ~4.4e-8 rotation
# skew. That splits what should be one +X coordinate across a 1 um boundary
# (2.321661711 vs 2.321661472), so the value is taken from the local coordinate
# the skew perturbs, not from rounding the two world values independently.
PART_4 = (
    [(-3.069769, -7.673195, 4.105916), (2.321661, -7.673195, 4.105916),
     (-3.069769, -7.673195, 0.0), (2.321661, -7.673195, 0.0),
     (-3.069769, -8.154625, 4.045916), (2.321661, -8.154625, 4.045916),
     (-3.069769, -8.154625, 0.0), (2.321661, -8.154625, 0.0)],
    [[0, 1, 3, 2], [2, 3, 7, 6], [6, 7, 5, 4], [4, 5, 1, 0],
     [2, 6, 4, 0], [7, 3, 1, 5]],
)

def current_substrate() -> list:
    """Four sloped-top parts; stepped in height, with a tall wall on the -Y edge.

    Every facade here is rainscreen — the sample has no street front, and indeed
    no -X-facing facade at all, so it cannot pose the brick condition. The stamp
    is applied anyway so the path that reads it is the one that runs.
    """
    parts = [substrate.polyhedron(*p) for p in (PART_1, PART_2, PART_3, PART_4)]
    for part in parts:
        part.metadata[FACADE] = RAINSCREEN
    return parts


# Walls this rig's bakes cannot yet say the outside of. Duncan, 2026-08-28:
# *"The L0, L2 and L3-internaljoin-S panels and their adjacent panel ends on
# that plane must be left uncovered until a full student-house site model is
# surveyed."* The three panels on that plane are L0, L2 and **L4** — there is no
# `L3-internaljoin-S` in the export, and L3 is the other wing, nowhere near
# `y = 10.3` — so the name is read as the third of the three.
#
# Named here rather than derived, and rather than in `skinning.rules`, because
# it is not a fact about the geometry at all: it is a fact about which
# neighbouring building has been surveyed. This is the reader, which is where
# every authored fact enters — the same place `FACADE` is stamped, and in the
# student-house one read of the IFC instead of a list. Nothing about the shape
# of these panels distinguishes them from a wall whose cap was left off by
# mistake, which is exactly why `rise` raises on both and why this is authored.
UNSURVEYED_OBJECTS = ("L0-internaljoin-S", "L2-internaljoin-S", "L4-internaljoin-S")


def stamped(parts: list) -> list:
    """The bake, with the authored facts the OBJ itself cannot carry.

    An OBJ names its objects and says nothing else, so a bake arrives with one
    `FACADE` for every part and nothing to separate a wall that is skinned from
    one that is not. The `o` name is the only authored handle there is.

    Matched on `metadata["object"]`, which is that name, and **not** on
    `metadata["name"]`, which is only the same thing while a group yields a
    single solid — `from_obj` disambiguates two into `<group>.1` and `<group>.2`,
    and this very bake does it to the taper layers. A join panel exported as two
    disjoint solids, which a rebate detached at a lift boundary would do, would
    then match nothing and be stamped with nothing, silently, and would be clad
    after all. Found on review, 2026-08-28.

    Silent on a substrate that names none of them, which is every bake but the
    whole-building one: the tuple is a property of this rig's exports, not a
    requirement on a substrate.
    """
    for part in parts:
        if part.metadata.get("object") in UNSURVEYED_OBJECTS:
            part.metadata[UNSURVEYED] = True
    return parts


def separation_check(parts=None, params=None):
    """Every skin this substrate poses, plus the smallest distance between any two."""
    parts = current_substrate() if parts is None else parts
    _, results = pipeline.run(parts, parameters.resolve(params))
    built = [r["raw"] for r in results if r["raw"] is not None]
    if len(built) < 2:
        # a `default=` here would hand back `inf`, and a caller asserting
        # `gap > threshold` would pass vacuously on a substrate that built one
        # skin or none. Found on review, 2026-08-26
        raise ValueError(
            f"this substrate poses {len(built)} skin(s), so there is no pair to "
            f"measure — check which rule sets select any of its faces"
        )
    return min(separation(a, b) for a, b in combinations(built, 2)), built


def build(
    parts: list | None = None,
    emit_substrate: bool = False,
    params: dict | None = None,
) -> list[dict]:
    """Build the skins and write them to `build/`.

    `params` defaults to the committed `skin-parameters.yaml`; pass a loaded
    what-if copy to build a variant. See `rules.skins()`.

    The module **reads** the substrate and never writes it. `emit_substrate`
    additionally dumps the parts as OBJ so they can be looked at in Blender; it
    is off by default and must stay off anywhere the substrate is live geometry.
    In the student-house the parts are Bonsai IFC objects carrying semantic data:
    re-emitting them would import a second, semantically dead copy of every part
    alongside the original, leaving two sources of truth in the scene. This rig
    transcribes its substrate from the scene rather than owning it, so a copy
    here is throwaway — but it still duplicates whatever was modelled, which is
    why `Cube` has to be hidden to see `Substrate_4`.
    """
    source = str(parameters.DEFAULT_PATH) if params is None else "(supplied)"
    params = parameters.resolve(params)
    print(f"  params     {source}")
    parts = current_substrate() if parts is None else parts

    named = []
    if emit_substrate:
        # a bake names its own parts, and eighteen anonymous boxes in the
        # outliner are no use for checking a transcription. The prefix stays
        # either way, because the stale-copy sweep below globs on it
        # ...and a name has to be unique, because it is the filename. `from_obj`
        # only disambiguates when *one* `o` group yields several solids, so two
        # groups sharing a name would write one file twice and put two manifest
        # entries on it -- one part silently absent from `reload(substrate=True)`,
        # which is the very check this path exists for. Fall back to the index,
        # which is what the names replaced and is unique by construction
        seen: dict[str, int] = {}
        for i, part in enumerate(parts):
            name = str(part.metadata.get("name", i + 1))
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                print(
                    f"  substrate  two parts are called {name!r}; part {i + 1} is"
                    f" written as Substrate_{i + 1} so neither is lost"
                )
                name = str(i + 1)
            named.append((f"Substrate_{name}", part, "solid", "substrate"))

    def borders(mesh):
        return len(trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1))

    # the substrate as one surface, for the crossing test below. Concatenated
    # rather than unioned: a crossing into any part is a crossing, and a union
    # would drop the very faces where two parts meet
    surface = trimesh.util.concatenate(parts)

    # the seam. Everything below this line is reporting and emission -- what the
    # student-house will not want and this rig exists for
    _, results = pipeline.run(parts, params)

    built = {}
    for result in results:
        name, spec = result["name"], result["spec"]
        # a skin whose rules select nothing on this substrate is skipped, and
        # said out loud. See `pipeline.covered` -- it is a real condition, not a
        # defect: the masonry needs a wall a cornice finishes and two of the
        # three substrates here have none
        if result["mesh"] is None:
            print(
                f"{name:<10} no face of this substrate meets its rules —"
                f" nothing emitted"
            )
            continue
        distance = spec["distance"]
        # measured on the raw emission and written cleaned and thinned. The lap
        # rule legitimately covers part of a plane twice, and `clean` dissolves that
        # — but everything printed below is a property of the *offset*, and
        # `clearance` in particular samples face centroids, so re-triangulating
        # moves the samples and would quietly change the verdict without any
        # surface moving. So the numbers stay on what `skin_over` produced, and
        # the file gets the mesh with the double cover resolved
        #
        # ...so both are kept. The pairwise verdict at the end of the run is a
        # statement about what ships, and is taken on the written mesh as well
        skin, tidy = result["raw"], result["mesh"]
        built[name] = (skin, tidy)
        named.append((name, tidy, spec["display"], "skin"))

        gap = clearance(parts, skin)
        slope = skin.metadata["slope_deviation"]
        border = borders(skin)
        print(
            f"{spec['name']:<10} offset {distance * 1000:.0f} mm"
            f" | lap {spec['drop'] * 1000:.0f}/{spec['out'] * 1000:.0f} mm"
            f" | residual {skin.metadata['offset_residual']:.2e}"
            f" | clearance {gap * 1000:.4f} mm"
            f" | {'closed shell' if skin.is_watertight else f'open, {border} border edges'}"
        )
        # reported whenever the clean changed what gets written: overlap
        # dissolved, or a plane re-triangulated in one piece and needing fewer
        # triangles, which happens with no double cover to dissolve at all. The
        # floor is float noise in a sum of triangle areas — 1e-12 m2 is a
        # millionth of a square millimetre, orders below any real overlap
        if tidy.metadata["overlap_removed"] > 1e-12 or len(tidy.faces) != len(skin.faces):
            thinned = tidy.metadata["vertices_dissolved"]
            # clamped at the same floor the guard uses, because a sum of triangle
            # areas that cancels lands either side of zero and `-0 mm2 of overlap
            # removed` reads as a defect. The masonry prints this line on the
            # triangle count alone, having no overlap at all
            removed = max(tidy.metadata["overlap_removed"], 0.0)
            print(
                f"           cleaned:"
                f" {removed * 1e6:.0f} mm2 of coplanar"
                f" overlap removed,"
                + (f" {thinned} collinear vertices dissolved," if thinned else "")
                + f" {len(skin.faces)} -> {len(tidy.faces)} triangles,"
                f" {border} -> {borders(tidy)} border edges"
            )
        # a gusset is the one face in the written mesh that is not the offset of
        # anything, so it is said out loud for the same reason a fold is: a
        # surface the module invented must not arrive silently
        if tidy.metadata["tears_closed"]:
            print(
                f"           gusseted: {tidy.metadata['tears_closed']} tear(s) closed,"
                f" {tidy.metadata['gusset_area'] * 1e6:.1f} mm2 of face that is not"
                f" the offset of any substrate face"
            )
        if slope > TOL:
            print(f"           sloped planes absorb up to {slope * 1000:.3f} mm")
        # a fold is geometry the solve stopped constraining because no skin
        # covered it. Reported rather than left to the metadata: it is the one
        # place the offset is deliberately not solved, and silence about that is
        # exactly what the runaway guard was written to stop
        folds = skin.metadata.get("folds") or []
        if folds:
            print(
                f"           {len(folds)} fold(s) left unconstrained, at vertex"
                f" {', '.join(str(v) for v in folds)} — surfaces facing opposite"
                f" ways that this skin does not cover"
            )
        # a horizontal edge the solve stopped holding horizontal, for the same
        # reason folds are printed: the ends have to rise by different amounts,
        # so the surface tears along it rather than staying level
        torn = skin.metadata.get("torn") or []
        if torn:
            print(
                f"           {len(torn)} horizontal edge(s) torn, between vertex"
                f" {', '.join(f'{a}-{b}' for a, b in torn)} — the two ends rise by"
                f" different amounts, so the skin has no such edge"
            )
        # the verdict. `clearance` is printed above and asserts nothing —
        # demoted 2026-08-25 on Duncan's decision, because it cannot tell a skin
        # that deliberately stops short of a feature from one folded through
        # itself, and because its answer moves when the surface is
        # re-triangulated. These two cannot: a crossing is a crossing however
        # the sheets are tiled, and containment is signed where a closest-point
        # distance is not. See NOTES, "The clearance verdict".
        # ...and it is taken on **both** meshes. Everything printed above is a
        # property of the offset and so is measured on the raw emission, but a
        # verdict is a statement about what ships: `clean` invents a gusset,
        # which is by its own account "not the offset of any substrate face",
        # and a gusset spanning a tear across a substrate feature would
        # otherwise go out unexamined. The two agree on all three bakes today —
        # this is a gap being closed, not a defect being caught (found on
        # review, 2026-08-25)
        for mesh, where in ((skin, "raw"), (tidy, "written")):
            note = "" if mesh is skin else f" ({where})"
            crossed = intersects(mesh, mesh)
            if crossed:
                print(
                    f"           WARNING: {crossed} self-crossing(s){note} —"
                    f" the skin folds through itself"
                )
            through = intersects(mesh, surface)
            if through:
                print(f"           WARNING: {through} crossing(s) into the substrate{note}")
            inside = buried(parts, mesh)
            if inside:
                print(f"           WARNING: {inside} sample(s) inside a substrate part{note}")

    # every pair, not the two there used to be: a third skin whose separation
    # went unprinted would be a skin nothing measured against anything
    for (one, (a, tidy_a)), (other, (b, tidy_b)) in combinations(built.items(), 2):
        print(
            f"           {one}/{other} separation {separation(a, b) * 1000:.3f} mm"
        )
        # two skins are *designed* to touch — both cap a wall, and they stack
        # outboard by the difference of the offsets — so what is checked is that
        # neither passes through the other, not that they stand apart
        #
        # ...and the verdict is taken on **both** meshes, for the same reason
        # the per-skin one is: `clean` invents a gusset, which is surface no
        # offset placed, and a gusset spanning a tear can reach where the raw
        # emission never did. The membrane carries 3459 mm² of it on the live
        # bake, so this is reachable surface and not a hypothetical. The
        # separation stays on the raw pair, because it is a printed number and
        # every printed number is a property of the offset. Found on review,
        # 2026-08-26; this loop read the raw meshes alone
        for first, second, where in ((a, b, "raw"), (tidy_a, tidy_b, "written")):
            note = "" if where == "raw" else f" ({where})"
            between = intersects(first, second)
            if between:
                print(
                    f"           WARNING: {one} and {other} cross{note},"
                    f" {between} triangle pair(s)"
                )

    manifest = []
    BUILD_DIR.mkdir(exist_ok=True)
    # stale substrate copies from an earlier emit_substrate=True run would
    # otherwise sit in build/ and keep being re-imported
    #
    # ...and so would a **skin** this run skipped. A skin being absent is now
    # routine -- `covered` skips one no face of the substrate meets -- so its
    # file from the previous run survives, holding geometry offset from a
    # different substrate. `display.reload()` is safe either way because it
    # reads the manifest, but the OBJ is what a person opens. Restricted to
    # names this module knows are skins, so nothing else in `build/` is touched
    stale = list(BUILD_DIR.glob("Substrate_*.obj"))
    stale += [BUILD_DIR / f"{name}.obj" for name in RULES]
    for old in stale:
        if old.exists() and not any(name == old.stem for name, _, _, _ in named):
            old.unlink()
    for name, mesh, display, role in named:
        path = write_obj(mesh, BUILD_DIR / f"{name}.obj", name)
        manifest.append(
            {
                "name": name,
                "file": path.name,
                "role": role,
                "display": display,
                "bounds": mesh.bounds.tolist(),
            }
        )
        print(f"  {role:<9} {name:<12} {path}")

    if not emit_substrate:
        print(f"  substrate  {len(parts)} parts read, none written")

    (BUILD_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    # this rig transcribes its substrate, so a copy of it is throwaway and worth
    # seeing next to the skins. Do not pass this where the substrate is live.
    #
    # An OBJ path builds that bake instead of the transcribed rig. It is an
    # argument rather than a parameter-file entry because it names the substrate,
    # not a tunable number, and `skin-parameters.yaml` is the numbers.
    import sys

    if len(sys.argv) > 1:
        bake = substrate.from_obj(sys.argv[1], metadata={FACADE: RAINSCREEN})
        build(parts=stamped(bake), emit_substrate=True)
    else:
        build(emit_substrate=True)
