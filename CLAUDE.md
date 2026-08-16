# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `NOTES.md` first.** It is the running handoff doc: current state, the constraint-priority
rationale, hard-won facts about the geometry stack, and open items awaiting Duncan's decisions.
This file covers commands and structure; `NOTES.md` covers why the code is the way it is. Keep
`NOTES.md` current when the state of play changes.

## Commands

```bash
python3 build.py              # headless build: writes build/*.obj + build/manifest.json
python3 -m pytest tests -q    # ~1.5 s
python3 -m pytest tests -q -k skirt        # single test by name
```

Every tunable number is in `skin-parameters.yaml`, validated against
`skin-parameters.schema.json`. `build.py` reads it and prints which file it used. A what-if is a
full copy of the file passed as `build(params=parameters.load_validated(path))` — never an
override of individual knobs. See **Parameters** below.

Run pytest from the repo root — `tests/test_offset.py` imports `build` as a top-level module.

`build.py` prints a per-skin line (residual, clearance, slope deviation, open/closed) and the
skin-to-skin separation. Those numbers are the regression check: a residual above ~1e-9, or a
clearance below `distance - slope_deviation`, means something broke.

To view the result, in Blender's Python console:

```python
exec(open("/home/duncan/skin-test/blender/display.py").read())
reload()                    # skins only
reload(substrate=True)      # and the transcribed substrate, to check transcription
```

**The module reads the substrate and never writes it.** `build()` emits skins only;
`build(emit_substrate=True)` additionally dumps the parts as OBJ, and `python3 build.py`
opts in because this rig transcribes its substrate rather than owning it. Do not opt in
where the substrate is live geometry — in the student-house the parts are Bonsai IFC
objects carrying semantic data, and a second dead copy of each beside the original would
leave two sources of truth in the scene. Manifest entries carry a `role` (`skin` /
`substrate`) and `display.reload()` skips `substrate` unless asked. The backstop is that
`clear()` removes only objects tagged `skin_generated`, so nothing here can delete or
overwrite geometry it did not itself import.

## Code review

Run `/code-review high` before a meaningful chunk of work lands — not per commit, and `high`
rather than the default because the changes here introduce seams rather than tweak lines. It
reviews the **current diff** by default, and also takes a path or branch target: use
`/code-review high skin/` to reach code that is committed and therefore outside any diff.

`git diff` does not see untracked files, so **`git add -N` any new file first** or it is invisible
to the review. A whole new module went unreviewed this way once before it was caught.

Two things that review catches and the rest of the stack cannot. The tests and the build both
exercise the happy path, so a knob that is only wrong when *supplied* passes everything —
`build(params=...)` skipped schema validation entirely and separation went 64.215 → 558.849 mm
(the figures the synthetic rig gave before its parameters were re-tuned on 2026-08-15)
with no error. And documentation that asserts a property the code does not have is invisible to a
test by construction. Both were found by an independent reader checking claims against code.

`--fix` applies findings to the working tree; omit it to see them first. Findings are a starting
point, not a verdict — verify each against the code before acting, because some are wrong.

## Architecture

The problem: offset a **substrate** (an assembly of solid parts) outward by a fixed distance to
produce **skins** — open surfaces covering a chosen subset of faces. Nothing in the Python
geometry stack ships a planar (mitered) offset, so `skin/offset.py` is ours.

Data flows one way:

```
skin-parameters.yaml                    every tunable number, JSON-Schema validated
   → skin/parameters.load_validated()   → dict; the ONLY file that reads it
   → build.skins(params)                joins the numbers to the RULES by name

build.py  PART_N vertex/face literals   (transcribed from Blender, snapped to 1 µm)
   → substrate.polyhedron()             list[Trimesh], one per part
     ...or substrate.from_obj()         a baked export, one part per `o` group
   → skin_over()                        union → planar_offset → keep() → skirt
   → write_obj()                        build/*.obj as n-gons + manifest.json
   → blender/display.py                 imports, tags, displays
```

Key invariants, each of which spans several files:

- **Geometry is headless.** `blender/display.py` is the only file that imports `bpy`, and it only
  loads — it never authors geometry. Everything else is trimesh/numpy and runs without Blender.
- **The union is computed about the origin.** `substrate.union` shifts the parts to the origin,
  unions, and shifts back — manifold3d is float32, whose resolution scales with magnitude, and
  where two nearly-coplanar faces meet that error is amplified by the shallow angle between them.
  Measured: the headhouse parapets at 15 m out unioned into **two** bodies, the second a 359 mm
  sliver of mean thickness 0.04 µm, well under manifold3d's own accuracy floor. Centred, one clean
  body. The shift is snapped to the same 1 µm lattice so coordinates do not drift off it.
- **The union is a throwaway.** `skin_over` unions the parts solely to find the outer surface
  (faces where parts touch vanish, so no skin is generated between them), then discards it.
  `parts` is never mutated and stays the substrate. Tests assert this.
- **`_owner()` maps union faces back to parts.** The union merges coplanar faces across parts, so
  a perimeter plane carries faces from several parts that are *not* interchangeable — face
  selection filters on `owner`, not on the plane.
- **The offset is solved over the whole body, then faces are selected.** Vertices on the edge of
  a selection therefore sit on the miter they would have had if the neighbours were skinned too.
- **A runaway vertex is refused.** `planar_offset` places each vertex where its offset planes
  intersect; if that lands further out than the body's own diagonal, those planes are effectively
  parallel and the intersection means nothing. It raises, naming the vertex. Not a tolerance to
  tune — it says the result is not a skin of this mesh. The cause is always a degenerate sliver,
  in practice a fragment a boolean left detached: the residual stays clean (the hard constraints
  *are* satisfied), so nothing else notices. `metadata["max_displacement"]` reports the worst.
- **Vertical/horizontal exact, sloped absorbs the error.** A sloped top over a concave plan
  over-determines the offset. `planar_offset` splits the plane equations into hard (|n_z| ≈ 0 or
  ≈ 1) and least-squares (sloped), plus hard equations keeping substrate-horizontal edges
  horizontal, and solves one KKT system over all vertex displacements. The test is on `|n_z|`,
  **not** axis-alignment: a wall at any plan angle must still come out exact.

## Parameters

`skin-parameters.yaml` holds every tunable number: `classify`'s two thresholds, `fall`, and the
five skin distances. `skin/parameters.py` is the **only** module that imports `yaml` or
`jsonschema`, and nothing else takes a path — the core takes a params *dict*. That is the
student-house seam exactly: `skin_pipeline.run(manifest, props, topo)` takes plain data and its
sub-modules read `topo["cladding"]["allowance"]` without parsing anything. Keep it that way, or
integration means writing an adapter.

Three rules carried over from student-house `bim/phase1/parameters.py`:

- **STRICT-COMPLETE.** The file specifies *every* knob. No built-in defaults, no partial overlay
  — a hidden default is what masks a bug. `substrate.classify` therefore **requires** `margin`
  and `aspect`, `_skin_from` uses no `.get`, and `Faces` has no default classifier: `Faces.roles`
  raises if none was passed. Do not "fix" any of those by restoring a default.
- **Schema does per-field, Python does cross-field.** Types, ranges, `required` and
  `additionalProperties: false` are in the JSON Schema. What a schema cannot express stays in
  Python: `parameters.check_seeds` (non-degenerate distances) and `build.skins`'s name join.
- **Fail at the seam, addressed.** Every raise names the field to edit, not the geometry that
  consumed it.

`parameters.check_seeds` enforces the **non-degenerate seed** rule: no two distances equal, none
an integer multiple of another. A zero `out` is exempt — it means the turn-out is off, and zero
is an integer multiple of everything. It is a named function the caller opts into, not part of
`validate`, because it is a discipline for a test rig rather than a code requirement.

Blender's python needs neither PyYAML nor jsonschema: `blender/display.py` imports only `bpy`,
`json` and `pathlib`, and never touches `skin/`.

**On migration** the `classify` / `fall` / `skins` block moves into
`student-house-parameters.yaml` under a `skin:` key, its schema is pasted into that repo's
schema, and the caller passes `topo["skin"]` where `build.py` passes `load_validated()`.
`skin/parameters.py` is then dead code there and should be deleted rather than ported — the
student-house already owns the read, via `topology_yaml.load` → `parameters.load_merged`.

## Adding a skin

A skin is an entry in `skins:` in `skin-parameters.yaml` plus a rule set in `RULES` in
`build.py`, not a new code path. `build.skins()` joins them by name, and raises if either side
names something the other does not — a skin with no rules cannot be built, and a rule set no
skin names would sit there looking maintained while emitting nothing.

```yaml
# skin-parameters.yaml — the numbers
- name: ...
  distance: m
  drop: m          # skirt: hangs below the wall's top edge
  out: m           # collar: folds outward where it stops; 0.0 for none
  display: solid | wire
```

```python
# build.py RULES — the predicates, keyed by the same name
"...": {"keep": fn, "turn_down": fn, "turn_out": fn or None}
```

`out` and `turn_out` must agree: a non-zero `out` with `turn_out: None`, or the reverse, raises.
The rules take `(Faces, fall)`; `skins()` binds `fall` from the file, so what `skin/` receives
still has the `Faces -> bool[nfaces]` signature it expects. A built spec is *exactly*
`skin_over`'s argument list plus `name` and `display`.

`keep`, `turn_down` and `turn_out` are predicates `Faces -> bool[nfaces]` over the union's
faces. `Faces` (in `skin/offset.py`) carries `body`, `parts`, `owner`, `normals`, `centres`, plus
`roles` (WALL/ROOF per part), `of_role(role)` and `touching(mask)`. Predicates get the whole thing
because rules that read the substrate need to ask what a face *adjoins*, not just where it sits.
Compose `_upward`, `wall_faces` and `_rules` rather than writing new plane tests. `keep` selects
what the surface covers; `turn_down` selects walls it hangs a skirt down; `turn_out` selects walls
it **stops against**.

The two continuations work on different things, and that distinction matters:

- `_hem` (skirt) works on the **union's** wall/roof adjacencies, and its drop is measured from
  the **substrate** edge — a test pins this, so do not "fix" it to measure from the skin.
- `_turn_out` works on the **assembled skin's** own boundary edges, after the hems are added, so
  a skirt that ends on the wall turns out along with everything else. Every panel ending on the
  wall is extruded by `out` along the **dominant axis of its own normal** — roof panels turn up,
  a panel facing -X turns -X. Snapping to the axis keeps a turn off a shallow slope exactly
  vertical. Its distance is measured from the skin edge, so all turns are exactly `out`.

`_turn_out` chains those boundary edges and **miters** the outer edges where neighbouring panels
meet, rather than extruding each edge alone. Extruding independently is wrong in both directions:
adjacent panels turning along different axes leave a gap at one corner and interpenetrate at the
next. The miter is just the intersection of the two outer lines, so it extends or trims as
needed. Segments that continue the same panel are parallel and are left unmitered.

## Classifying parts

`substrate.classify(part, margin, aspect)` returns `WALL` or `ROOF` **from geometry alone** — no
IFC, no part indices — so the rules survive a substrate with hundreds of parts. The two thresholds
are authored (`classify` in the parameter file) and **required**; `build.classifier(params)` binds
them once and the bound callable is what `Faces` and `skin_over` are handed. It is deliberately not
derived from bounds: an axis-aligned box around a wall running diagonally in plan inflates both
horizontal extents until the height is the smallest of the three, and the wall reads as a slab.
Two independent measures must agree instead:

- `horizontality(part)` — area-weighted `|n_z|`; 0 for a pure wall, 1 for a pure slab
- the thinnest side of the **oriented** bounding box: a slab is thin vertically, a wall is thin
  horizontally

Disagreement, a horizontality near the halfway mark, or a block-like part with no clear thin
direction all raise `AmbiguousPart` with the numbers. **Do not add a fallback that picks a
side.** A misclassified part skins silently and wrongly somewhere inside a large model, which is
precisely the failure the loud version exists to prevent.

`Faces.roles` caches the per-part result for the substrate being skinned, so a predicate reads
the classification of the parts actually passed to `skin_over` rather than of a module-level
default. It calls the classifier `Faces` was constructed with, and raises if there is none —
there is deliberately no fallback pair of thresholds.

## The face rules

`build.py` holds them; `skin/` never learns what a wall or a membrane is. They are derived, not
listed — there are no plane coordinates and no part indices in them:

- **exterior / interior** — a wall's top falls toward its interior, so the face under the high
  edge is the facade and the one under the low edge is the interior (`uphill` + `wall_faces`).
  `uphill` takes the **element**, `Faces.elements` — every body of one wall — not a single part.
  A baked wall arrives as an inner leaf, an outer leaf and a cap plate; the leaves are
  flat-topped boxes and only the cap is sloped, so a per-body reading raises on two thirds of a
  wall that plainly has a high side. A flat face contributes `(0, 0)` to the area-weighted sum,
  so hidden leaf tops dilute the magnitude and never the direction — even where, as on a real
  parapet, they match the cap in area. Which faces then get classified is still decided per body,
  by role. This is deliberately *not* "find the cap part above": that would require a separate cap
  body to exist, whereas summing over the element gives the same answer whether the leaves are
  split or merged upstream. A
  vertical face across the fall is an **end** and is neither, which is how section cuts drop out
  without being enumerated. `fall` is the authored direction cosine that separates the two from an
  end (0.707 = 45°); every rule below takes it as an argument and `skins()` binds it. The
  exception is a facade wrapping a corner: an end coplanar with and joined to a neighbour's facade
  is grown into the exterior set.
- **climb or flange** — whichever face of a wall the roof runs into decides it. Into the interior
  face and the membrane climbs and carries over the top; into the exterior face and it stops and
  flanges. Tested per **wall**, not per face: only one triangle of a step wall touches the roof,
  but the membrane climbs the whole face, so touching faces elect the wall and the wall carries
  all of its own faces.
- **which cladding system a facade takes** — read off the part, not derived. `facades_of(faces,
  system, fall)` intersects the geometric facade set with `Faces.tagged(FACADE, system)`. No property
  of a wall's shape implies brick, and neither a compass direction nor a named plane separates a
  brick street front from a rainscreen headhouse facing the same way at a different setback. A
  substrate reader stamps `part.metadata["facade"]`; in the student-house that is one read of the
  IFC material. `check_facades` raises if any facade is claimed by no declared system, so an
  unstamped part cannot silently vanish from every skin.
- **`uphill` raises on a flat top.** A stacked wall panel has no high side and must take its
  direction from the parapet above it — not yet built. Do not add a fallback that guesses a side.

## Substrate changes

Duncan models in Blender and asks for it to be skinned. The routine: read the scene out, snap
coordinates to 1 µm, transcribe into `build.py` as `PART_N` vertex/face lists, rebuild. Faces may
be given in any winding — `polyhedron()` fan-triangulates and calls `fix_normals()`.

**Transcription is for small substrates only.** Four parts as literals is reviewable; the
student-house's exterior walls, parapets and roof layers run to roughly eighty. Those arrive
through `substrate.from_obj(path, metadata=...)` instead — one OBJ export out of Blender, one part
per `o` group, snapped to 1 µm on the way in. Blender cannot be the reader: a `.blend` needs
`bpy`, and geometry here is headless. The `PART_N` parts stay regardless — they are the synthetic
worst case the tests run on, not a stand-in for a real substrate.

`from_obj` parses the OBJ itself rather than calling `trimesh.load`, which in trimesh 5.0.0
silently merges every `o` group into one mesh named after the first. It raises, naming the object,
on a group with no faces, a face loop the fan triangulation would tile wrongly (concave from its
first vertex — export that object triangulated), and a part that is not a closed solid. That last
one matters because `skin_over` unions the parts: a union over an open shell produces nonsense
rather than an error.

**Hand-modelled objects survive `reload()`.** `clear()` removes only objects carrying the
`skin_generated` key, so anything Duncan models is untouched — that is the same safety property
that protects lights, cameras and live Bonsai IFC parts, and it is why `build.py`'s docstring
notes that `Cube` has to be *hidden* to see `Substrate_4`. (This paragraph replaces a line
claiming the opposite, which was wrong and had Duncan saving `skin-test.blend` defensively.)

**The substrate cannot be lost, and the `.blend` is not what protects it.** It lives in `build.py`
as the `PART_N` literals, in git. `python3 build.py` opts into `emit_substrate=True`, so
`build/Substrate_*.obj` are always current; `reload(substrate=True)` brings them back into the
scene. To add a part: `reload(substrate=True)` for reference, model the new part as **its own new
object**, then transcribe. Never model into an imported `Substrate_N` — those *are* tagged, so the
next `reload()` deletes them.

Snapping is not optional. Blender meshes are float32 and modelled faces miss each other by tens
to hundreds of nanometres, which become sliver faces in a union and near-parallel plane pairs in
the solve.

## Tolerances

manifold3d computes in **float32**, so a union's faces sit up to ~5e-7 m off their true planes at
metre-scale coordinates. That is the accuracy floor for everything downstream: `TOL = 1e-6`
(`build.py`) and `PLANE_TOL = 1e-6` (`skin/offset.py`) exist for it. Do not tighten them — an
earlier 1 nm threshold produced a bogus self-intersection warning. `RIDGE = 1e-9` keeps the KKT
system non-singular where the soft equations leave a vertex free; it is not a tolerance to tune.
