# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `NOTES.md` first.** It is the running handoff doc: current state, the constraint-priority
rationale, hard-won facts about the geometry stack, and open items awaiting Duncan's decisions.
This file covers commands and structure; `NOTES.md` covers why the code is the way it is. Keep
`NOTES.md` current when the state of play changes.

## Commands

```bash
python3 build.py              # headless build: writes build/*.obj + build/manifest.json
python3 build.py <bake.obj>   # ...over a baked substrate instead of the transcribed rig
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

Substrate parts emitted from a bake keep their own names (`Substrate_Parapet-Headhouse-N`),
because eighteen boxes called `Substrate_7` are no use for checking one. The `Substrate_` prefix
stays regardless: the stale-copy sweep in `build()` globs on it.

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
  It is now a backstop rather than the front line — a fold is caught first, structurally, by the
  rule below.
- **A fold is reconciled against what the skin covers, or refused.** Where the surface turns back
  on itself a vertex lies on two planes facing opposite ways, and no offset exists for it: it
  would have to move `distance` both ways at once. `_reconcile` re-reads that vertex's planes
  from the **covered** faces alone — the ones `keep`/`turn_down`/`turn_out` selected, which is
  why `skin_over` evaluates its predicates *before* the solve and passes the mask down. If the
  contradiction survives among those, it raises naming the vertex and the two normals. Applies at
  contradictory vertices and nowhere else, so no model that solves today changes by a bit; a
  hash of the rig and both parapet exports pins that. The reconciled vertices are reported in
  `metadata["folds"]` and printed by `build.py`, because a constraint the solve deliberately
  dropped must not be silent. Consequence, accepted by Duncan 2026-08-16: a degenerate sliver
  **no skin covers** is now tolerated rather than refused.
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
  base: m | null   # trim: cut here and keep what is above; null for none
  display: solid | wire
```

```python
# build.py RULES — the predicates, keyed by the same name
"...": {"keep": fn, "turn_down": fn, "turn_out": fn or None}
```

`out` and `turn_out` must agree: a non-zero `out` with `turn_out: None`, or the reverse, raises.
`base` pairs with no rule — it is a datum rather than a face selection — and `null` is **not**
`0.0`: zero is a real height to cut at, where a zero `drop` or `out` is the feature switched off.
It is also not a seed, so `check_seeds` ignores it.
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

`_trim_below` (`base`) runs **after** both, so it means "no part of this skin goes below the
datum" rather than "the offset stops there". It is a **cut**, not a clamp: triangles straddling
the plane are re-cut against it and everything above keeps the plane the solve gave it. Pushing
the low vertices up instead would look identical in outline while tilting the bottom of every
sloped panel off its offset plane — and the residual is computed before the trim, so nothing
would report it. Crossings are cached per edge so the two triangles sharing one get the same
vertex and the cut does not crack.

`_turn_out` chains those boundary edges and **miters** the outer edges where neighbouring panels
meet, rather than extruding each edge alone. Extruding independently is wrong in both directions:
adjacent panels turning along different axes leave a gap at one corner and interpenetrate at the
next. The miter is just the intersection of the two outer lines, so it extends or trims as
needed. Segments that continue the same panel are parallel and are left unmitered.

**A separately-authored cap plate joins the wall it caps.** `build.group_caps` runs before
anything reads a role, and re-stamps `metadata["object"]` so the plate and its parapet are one
element. The rule is derived, not a name match: **a lift that classifies `ROOF` while the element
it rests on classifies `WALL` is that wall's cap** — `_next_lift` already computes "rests on and
continues", the same relation `rise` walks. It groups the cap and **not** the parapet under it,
which is why the lift's own classification is the test: a parapet reads `WALL` alone and stays
separate. Do not extend it to merge a whole stack into one element. That would read `WALL` too
and would break something else — the climb-or-flange election is per wall, so a wall merged with
its parapet has the membrane climb its full height instead of stopping at the parapet the roof
runs into. It is inert on a bake whose plates already sit inside their parapet objects, and
idempotent.

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
  edge is the facade and the one under the low edge is the interior (`rise` + `wall_faces`).
  `uphill` takes the **element**, `Faces.elements` — every body of one wall — not a single part.
  A baked wall arrives as an inner leaf, an outer leaf and a cap plate; the leaves are
  flat-topped boxes and only the cap is sloped, so a per-body reading raises on two thirds of a
  wall that plainly has a high side. A flat face contributes `(0, 0)` to the area-weighted sum,
  so hidden leaf tops dilute the magnitude and never the direction — even where, as on a real
  parapet, they match the cap in area. Which faces then get classified is decided per **element**
  too, not per body: role is one value shared by all of an element's bodies, so a wall admits the
  vertical faces of its leaves and its cap together. (This line claimed a per-body decision until
  2026-08-16. It was true when written, and stopped being true the day `Faces.roles` moved to the
  element — the filter it described could no longer discriminate.)
  Summing over the element is deliberately *not* "find the cap part above": it gives the same
  answer whether the leaves are split or merged upstream, without requiring a separate cap body
  to exist. Where the cap is separate *from the element too* — its own object, as in the current
  bake — the element genuinely has no slope of its own, and `rise` looks up the stack for it; see
  the flat-top rule below for what it will and will not accept as the lift above. The two are not
  in tension: the sum is what reads an element that has a slope somewhere in it, and the walk is
  what runs only when that sum comes back flat. A
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
- **both skins cap a wall, deliberately.** A top the membrane carries over is also claimed by
  `cladding_faces`' "every wall top", so a parapet coping belongs to two skins at once — a
  membrane upstand with a metal coping over it, which is what a parapet is built as. Decided
  2026-08-16 after the alternatives (give the top to one skin or the other) were rejected, and
  reaffirmed 2026-08-19 when a bake that authored its cap plates as **separate objects** reversed
  it by accident: each plate became its own element, a 29 mm plate classifies `ROOF` alone, and
  "every wall top" stopped reaching any coping. `build.group_caps` restores it — see below. They
  stack rather than collide: the cladding sits outboard by the difference of the two offsets, to
  within what the sloped planes absorbed, and a test pins that ordering. **Do not narrow either
  predicate to make the skins disjoint** — an overlap here is the design, not a bug.
- **which cladding system a facade takes** — read off the part, not derived. `facades_of(faces,
  system, fall)` intersects the geometric facade set with `Faces.tagged(FACADE, system)`. No property
  of a wall's shape implies brick, and neither a compass direction nor a named plane separates a
  brick street front from a rainscreen headhouse facing the same way at a different setback. A
  substrate reader stamps `part.metadata["facade"]`; in the student-house that is one read of the
  IFC material. `check_facades` raises if any facade is claimed by no declared system, so an
  unstamped part cannot silently vanish from every skin.
- **A flat-topped wall takes its direction from the lift above it.** `uphill` reads one
  element's own top and raises where it is flat; `rise` walks the stack to the element that
  carries the fall, and is what `wall_faces` calls. A wall built in lifts is flat-topped all the
  way up — panel, parapet, and only the cap plate laid to fall — so the walk is recursive, not
  one step. `_next_lift` decides what counts as the next lift, and takes three conditions: it
  rests on this element's top, it overlaps it in plan, and it is **flush on both faces across
  this element's thickness**. Both faces, not one: a roof deck bears on every wall it lands on
  and is flush with none, while a neighbour's cap plate runs over a wall's *end* and is flush
  with the building's outer plane there — one face of two. Requiring the opposed pair separates
  them exactly, with no threshold to author. Do not relax it to a single plane and weight the
  strays down by area: that leaves the answer tilted a few degrees and dependent on how long the
  walls happen to be. Where the stack ends with no slope anywhere it still raises, naming the
  element. Do not add a fallback that guesses a side.

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
on a group with no faces, a loop it cannot triangulate, and a part that is not a closed solid.
That last one matters because `skin_over` unions the parts: a union over an open shell produces
nonsense rather than an error.

**A loop the fan cannot tile is ear-clipped, not refused.** `polyhedron`'s fan is faithful only
for a loop star-shaped from its first vertex, and a bake is full of loops that are not: a wall
with a rebate, a parapet with a scupper slot cut through the middle of an edge. Rotating the loop
to start elsewhere does not save it — a slot leaves a face star-shaped from no vertex at all, and
6 of the 14 notched faces in the current bake are that shape. So `from_obj` ear-clips them in the
loop's own plane and hands `polyhedron` triangles, which fan to themselves. It is written here
because nothing installed will do it: `mapbox_earcut` and `triangle` are both absent, and
trimesh's remaining engine routes through manifold3d, whose float32 is what `substrate.union`
already shifts to the origin to work around. The clip runs on the snapped float64 coordinates.
What it still refuses is a loop that is **not simple** — the tiled area is checked against the
loop's own and disagreement raises, because ear clipping a self-crossing loop returns well-formed
triangles covering the wrong region. A corner with no area is clipped away contributing nothing,
which settles the old asymmetry where `_fan_is_valid` read a collinear vertex as concavity only
when it sat next to vertex 0: either way no zero-area triangle now reaches the mesh.

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
