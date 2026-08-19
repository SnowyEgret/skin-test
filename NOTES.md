# skin-test — state of play

Offsetting a **substrate** (an assembly of solid parts) outward by a fixed distance to
produce **skins**: open surfaces that cover a chosen subset of faces.

Last worked: 2026-08-19.

`CLAUDE.md` has the commands, the architecture and its invariants, and the tolerance
rationale. This file is the running log: what the geometry currently is, what was tried
and rejected, and what is still open.

## Why this exists

A ground-up replacement for the student-house skinning module, which had grown too large
and brittle to refactor. This substrate is **synthetic**: four clipped parts assembled to
pose every condition where facade meets roof, which is where the old module struggled.
Parts 1, 2 and 4 are wall panels, part 3 is a roof. Their end and bottom faces are section
cuts and are never skinned; the real substrate has none. Prefer the general rule over the
one that fits these four parts.

## Where we got to (end of 2026-08-15)

The geometry is right, the rules are **derived rather than listed**, and the numbers are
now **authored rather than coded**. `build.py` holds no plane coordinates, no part-index
sets and no magic constants: exterior/interior comes off each wall's own top slope,
climb-or-flange from which face the roof runs into, wall-vs-roof from
`substrate.classify`, cladding system from `part.metadata`, and every tunable number from
`skin-parameters.yaml`. 46 tests, ~1.9 s.

Agreed order for what remains, from the migration discussion:

1. ~~non-degenerate seeds~~ — done
2. ~~exterior/interior derived from the slope~~ — done
3. ~~per-face offsets in `planar_offset`~~ — **deleted, not deferred.** There is never
   more than one offset in a cladding mesh: a different allowance is a different skin,
   which the `skins:` list already supports. A scalar `distance` is correct, not a
   limitation.
4. ~~YAML + JSON Schema parameters~~ — done 2026-08-15. See below.
5. **Skin the real substrate**, agreed 2026-08-15. Duncan bakes the student-house's
   exterior walls, parapets and roofs to solids, exports one OBJ, and we skin it here.
   If it will not skin, the **first** move is reversing decisions upstream to reduce the
   substrate's complexity — he has two targets in mind — and only if that fails do we
   adapt this side. A condition that does not exist needs no rule, no test and no
   debugging; that lever exists only because he owns both repos.

   The import reader is built and waiting (`substrate.from_obj`). Not yet done: it has
   only been run on round-tripped synthetic parts, never on a bake.

   Rejected on the way: reading `skin_assembly.py` to infer what conditions the real
   substrate poses. The substrate **is** the requirement and the old module is one failed
   attempt at meeting it, so deriving the requirement from the attempt mixes real
   conditions with accumulated workarounds and cannot tell them apart. Do that pass —
   categorising `skin_inputs`' thirteen inputs as dissolved / needs a `Faces` addition /
   needs a new part — only once the whole substrate skins, when there is ground truth to
   check it against.

## The parameter layer (2026-08-15)

Written after reading how the student-house actually does it, so the two match rather
than merely resemble each other:

- **`bim/phase1/parameters.py` is the parser there**, and `topology_yaml.load()` is the
  single public entry — structure YAML + validated params merged into one `topo` dict.
- **Sub-modules never parse.** `skin_pipeline.run(manifest, props, topo)` takes plain
  data; `skin_assembly.py` is 2480 lines with exactly *one* `topo[...]` read
  (`topo["cladding"]["allowance"]`, line 2402). That is what lets the pipeline run and be
  profiled outside Blender, and it is the seam this module has to land on.
- **Five parallel loader modules, no shared helper.** `parameters`, `topology_yaml`,
  `unit_plan_yaml`, `mapping_yaml`, `code_constraints` each repeat the ~15-line
  load/validate pattern, because each owns its own schema and error class. So copying the
  *pattern* here is correct; copying the *parameter file* would not be.

What that dictated:

- `skin/parameters.py` mirrors `bim/phase1/parameters.py` (`load` / `validate` /
  `load_validated`, `ParameterError` naming the field). No `merge` — this rig has no
  separate structure file for numbers to be injected into.
- **The core takes a dict, never a path.** `skins(params)` is where the parameter layer
  stops; below it, nothing has heard of a knob.
- **On migration**: the `classify` / `fall` / `skins` block moves into
  `student-house-parameters.yaml` under `skin:`, the schema fragment is pasted into that
  repo's schema, and the caller passes `topo["skin"]`. `skin/parameters.py` is then dead
  code there and gets deleted, not ported.

Three defaults had to die for STRICT-COMPLETE, all of them the "hidden default masks a
bug" kind:

- `_skin_from`'s `spec.get("out", 0.0)` → `out` is authored for every skin, and `skins()`
  raises if it disagrees with whether the rule set defines `turn_out`.
- `classify(margin=0.05, aspect=0.85)` → both required. `build.classifier(params)` binds
  them once; `Faces` is constructed with the bound callable and `Faces.roles` raises if it
  has none. `skin_over` gained a `classify=` passthrough. It stays optional there because
  a plain closed-shell offset selects no faces and so runs no predicate — the `None` is
  the *absence* of thresholds, raising at the point of use, not a stand-in pair.
- the rule predicates read `FALL` from module scope → they take `(Faces, fall)` and
  `skins()` binds it, so what `skin/` receives still has the `Faces -> bool[nfaces]`
  signature it expects.

`check_seeds` is separate from `validate` on purpose: non-degenerate seeds are a
discipline for a **test rig**, not a code requirement, so a production what-if that
genuinely wants two skins 100 mm apart calls `validate` alone. Zero is exempt — it means a
turn-out is off, and zero is an integer multiple of everything.

The build output is unchanged by the refactor, which is the oracle for it: separation
still 64.215 mm, residuals still ~1e-16.

### What `/code-review high` caught (2026-08-15)

First formal review in either repo. Two findings were real defects in the new layer, and
both were invisible to the 32 tests and to the build:

- **A supplied `params` dict was never validated.** `load_validated() if params is None
  else params` runs the schema only on the default path — and the what-if workflow is
  exactly "hand-edit a copy and pass it". Measured: `build(params=<fall: 1.4>)` wrote both
  skins, separation 64.215 → **558.849 mm**, no error, while `validate` rejects that value.
  `check_facades` missed it too: `fall > 1` empties the exterior set, so "every facade is
  claimed" holds vacuously. Fixed by `parameters.resolve`, which every `params` entry point
  now goes through. It does **not** run `check_seeds` — that stays opt-in.
- **`aspect: 1.0` switched the block-like guard off.** `classify` raises when `extents[0] >
  aspect * extents[1]` with `extents` sorted ascending, so `aspect = 1` is unreachable and a
  1x1x1 cube returns `WALL`. The schema said `"maximum": 1` and its description invited it.
  Now `exclusiveMaximum`. `margin` has a softer version of this at its lower end (`1e-12`
  narrows the ambiguity band to nothing) but no single value is a clean off switch, so it is
  left alone.

Also: the YAML header promised a `--params` CLI that does not exist, and `cladding_skirts`
unpacked `_rules` with `meets`/`climbed` bound to `climbed`/`flanged` (pre-existing, harmless
only because it returns `interior` alone). Both fixed; two regression tests added; 34 tests.

**Still open, Duncan's call:** nothing declares dependencies. `skin/parameters.py` adds `yaml`
and `jsonschema`, and `build.py` imports it at module scope, so a fresh checkout now fails at
test collection rather than at first use. Consistent with the already-undeclared trimesh and
numpy, so it is a repo-wide gap rather than a fault in this change — a `requirements.txt`
would close it.

The lesson worth keeping: tests and the build both exercise the happy path, so a knob that is
only wrong when *supplied* passes both. And a docstring asserting a property the code lacks
cannot fail a test by construction. Those are the two things review reaches and the rest of
the stack does not.

Blender's python needs neither PyYAML nor jsonschema here — `blender/display.py` imports
only `bpy`, `json` and `pathlib`. The student-house had to install both into Blender's
python; this rig does not, because nothing on the bpy side touches `skin/`.

## The OBJ import path (2026-08-15)

`substrate.from_obj(path, metadata=...)` — one part per `o` group, snapped to 1 µm on the
way in, which is where transcription used to do it. Built ahead of the bake so it is
waiting; **only exercised on round-tripped synthetic parts so far.**

Three things it refuses, each naming the object, and each for a measured reason:

- **`trimesh.load` is not used.** In trimesh 5.0.0 it merges every `o` group into one mesh
  named after the *first*: a two-object file comes back as one geometry called `Wall_A`
  holding both bodies. Object identity is load bearing — `_owner` maps union faces back to
  parts and `classify` runs per part — so `_parse_obj` reads `o`/`v`/`f` itself. A test
  pins the merging behaviour so we notice if a trimesh upgrade changes it.
- **An open shell.** `skin_over` unions the parts, and a union over an open shell produces
  nonsense rather than raising, so it has to stop here.
- **A face the fan cannot tile.** `polyhedron` fan-triangulates, which is faithful only
  when the loop is star-shaped from its first vertex; a baked wall with a notch is not.
  Area does **not** detect this — signed triangle areas telescope to the true polygon area
  whatever the shape, which is why the first check written was wrong — so the test is that
  no triangle is inverted relative to the loop's own normal. Fix on the Blender side by
  exporting that object triangulated; there is no earcut available to do it here.

Decisions made with Duncan before the bake:

- The `.blend` cannot be the input — it needs `bpy`, and geometry is headless. One OBJ
  export is the handoff.
- The four `PART_N` parts **stay**. They are the synthetic worst case the tests run on,
  and the brick condition belongs there where it can be posed deliberately.
- The bake carries no IFC metadata, and it does not need to: the reader stamps one
  cladding system across every part, exactly as `current_substrate()` does. `skin/` still
  never learns what a facade is — `metadata` is a plain dict the caller fills.
- Roof layer stacks (`Roof_Deck9_CLT` / `_InsulationFlat` / `_InsulationTaper`) can all
  come across. The union discards the internal faces and skins the composite outer surface.

Expected to bite first, both by design and both wanting a decision rather than a fallback:
`uphill` raises on a flat top (real walls are stacked panels — the parapet in the bake is
what finally makes that rule writable), and `classify` raises `AmbiguousPart` on anything
block-like.

## Skinning the real substrate (2026-08-15)

Three exports from the student-house, each simpler than the last. The reader took two
fixes to read the first one and has been unchanged since; the geometry took longer.

**What the reader needed** (both were bugs here, not in the exports — every object in every
export is a closed polygonal solid, every edge exactly twice):

- **A group is not a part; a body is.** A baked wall arrives as inner leaf, outer leaf and
  cap plate, modelled as separate solids inside one Blender object and *touching*. Their
  shared corners are distinct indices at identical coordinates, so merging the group fuses
  them into edges with four incident faces — non-manifold, and refused as an open shell
  though every solid in it is closed. `_bodies` splits over the OBJ's own indices, before
  snapping, so coincident-but-distinct corners keep the bodies apart.
- **Degenerate faces.** The insulation taper writes triangles as six-sided loops with every
  corner doubled, and zero-area slivers as quads with two — 11 faces, boolean residue.
  `_collapsed` fuses them; unlike a concave loop there is nothing for a person to decide.

**What the geometry needed.** Failures were all *self-contact*: a vertex carrying a plane and
its exact opposite, `n·t = d` and `−n·t = d`, which the solve can only split, leaving a
residual of the whole offset distance. Three sources, measured:

1. **A knife corner** — `Headhouse-E` and `Headhouse-N` are diagonal neighbours meeting only
   along a vertical line, with E's bottom landing partway up N's uncut corner edge. Fixed by
   extending the Tail bodies down to cover the wall end. **Costs no design decisions** — the
   Tail's job is to cap that end and it merely stopped short. The split-level bottoms can stay.
2. **The scupper**, modelled by decomposing the parapet around a void rather than punching a
   hole (which is why the union came back genus 0). The one change that unblocks skinning, on
   both exports. Duncan's plan is to punch it later from IFC opening data, as windows and
   doors already are.
3. **A detached sliver** — see below.

**Measured, so it is not re-argued:**

| | residual | note |
|---|---|---|
| walls+parapets as exported | 2.00e-02 | 5 self-contacts |
| leaves and caps merged | 2.00e-02 | *unchanged* — union is associative |
| tails cover the wall end | 2.00e-02 | knife corner gone |
| \+ scupper punched later | 7.40e-12 | **solves**, bottoms untouched |
| parapets+CLT, no scupper | 7.63e-17 | **solves**, skin exactly 20 mm out |

**Merging objects buys nothing.** `skin_over` unions the parts, and union is associative, so
regrouping can never change the body being offset. Every simplification has to be a
*re-modelling*. This caught out two of the three candidate targets.

**So of the three simplifications, only the scupper is needed to skin.** Eliminating the
leaf/cap split is a *rules* problem — it is what makes cap plates classify `ROOF` and denies
parapets a readable `uphill` — and should be decided on those merits.

**The detached sliver was float32, not the model.** Asked where it came from, the answer is
neither the export nor a bug in the reader: `trimesh.boolean.union` produced it. Three
measurements settle it. The wedge is 359 mm long with a mean thickness of **0.04 µm** —
an order of magnitude below the ~5e-7 m accuracy floor manifold3d's float32 arithmetic
gives at metre scale, so it is thinner than the arithmetic that made it can resolve.
Unioning the identical parts **centred on the origin** returns one clean body. And the
two overlapping corner caps alone (`N.5` + `N.7`) union to one body — it takes the whole
assembly, 15 m from the origin, to produce it.

The mechanism: float32 resolution scales with magnitude, so at ~15 m a coordinate resolves
to roughly 1 µm; where the mitred caps meet nearly coplanar, that error is amplified by the
shallow angle between the faces into millimetres of in-plane displacement. Hence
`substrate.union` now shifts to the origin, unions, and shifts back, with the shift snapped
to the 1 µm lattice. `skin_over` and `build.build` both go through it. The synthetic build is
unchanged to 1e-16, and the headhouse parapets now skin through `skin_over` directly:
120 faces, watertight, residual 2.26e-16, clearance 19.702 mm.

Leave-one-out was misleading here and is recorded so it is not repeated: dropping any of
seven parts, at all four corners, collapsed the union to one body. That looks like a
modelling defect with many contributors; it is actually the signature of a result sitting
on a numerical knife edge.

Not reproduced in the suite. It needs sloped faces mitring at a shallow angle 15 m out, and
the synthetic substrate cannot pose that; an attempt to build the fixture produced a
non-volume. `test_the_union_is_computed_about_the_origin` pins the mechanism — that the
shift is undone and the lattice preserved — and says so in its docstring.

**The runaway guard.** The no-scupper export still leaves one
four-vertex wedge orphaned at a mitred parapet corner, by about 6 mm of overshoot past the
leaf boundary. Offset 20 mm, it landed **20 km out**, while the 120-face body it came from
offset exactly. `offset_residual` stayed at 7e-12 — the hard constraints *were* all satisfied
— so nothing in the stack noticed; it surfaced as a crash in the OBJ writer. Hence the runaway
check in `planar_offset` (see CLAUDE.md). Its test transcribes the real wedge as a literal: a
made-up sliver will not reproduce it, because an acute plan wedge saturates at a bounded
displacement once `_vertex_normals` snaps its faces onto the axis.

Two corrections that came out of the same fragment, recorded because both were reported to
Duncan before being caught: the 44.8 mm slope deviation and the 19.70 mm clearance were **the
chip**, not the mitred corners over-determining the offset. Without it, 0.298 mm and a clean
20 mm. The mitred corner caps are fine — and removing them makes things far worse (residual
2.69e-02), because they are what covers the corners.

**Also corrected:** parapet caps fall **inward**, toward the roof, high edge outboard. An
earlier note here said outward; that was `uphill` (the *rise* direction) misread as fall. The
consequence matters — the exterior/interior rule reads the outboard face as the facade, which
is right. It does not misfire on parapets.

**The flat-top rule, closed 2026-08-15.** The open item this file carried from the start —
"a stacked wall panel must take its direction from the parapet above it" — is done, and the
answer was a change of *unit* rather than a search.

`uphill` now takes the **element** (`Faces.elements`, grouped by `metadata["object"]`), not a
part. The insight: `_bodies` established that the **body** is the right unit for solidity,
because the boolean must keep touching solids apart. It is the wrong unit for what a wall
*is*. An inner leaf and an outer leaf are not two walls with two directions; they are one
wall, and only the cap carries its slope.

Duncan's question was whether this commits the module to the student-house leaf/cap
geometry. It does not, and that is the point of the shape chosen. "Find the sloped part
sitting on top" would commit us — it needs a separate cap body to exist. Summing the
element's upward faces does not: leaves split, the cap in the group supplies the direction;
leaves merged upstream, each element is one part with a sloped top and the same sum gives
the same answer. A test asserts both readings agree. So target 1 stays an optimisation
rather than becoming a prerequisite.

It works because a flat face contributes `(0, 0)` to the area-weighted sum — it dilutes
magnitude, never direction. On the real parapets the cap covers both leaves exactly, so
*half* the upward surface of each wall is hidden flat top, and the direction is still clean.
Where absent, `metadata["object"]` falls back to one element per part — the identity
grouping, not a guess, and exactly the transcribed `PART_N` case.

**Both skins now build on the real substrate** (headhouse parapets, no scupper):

| | faces | residual | clearance |
|---|---|---|---|
| Membrane | 24 | 2.26e-16 | 19.702 mm |
| Cladding | 41 | 9.58e-16 | 85.000 mm |

7 elements from 25 parts; `wall_faces` finds 41 exterior and 9 interior of 120 faces.
Separation 81.691 mm — larger than the synthetic rig's, because the two skins here
cover disjoint substrate faces, so their closest approach is corner-to-corner rather than
across a shared face.

**Role moved to the element too** (same day). `Faces.roles` classifies the element as built —
its bodies unioned — and every body reports its element's role, so a parapet's 29 mm cap plate
stops reading `ROOF`. The climb/flange election in `_rules` moved with it: the face that
touches the roof is on the inner leaf while the top the membrane carries over is on the cap,
so electing per body climbed a leaf and stopped at its flat top, leaving the cap bare.

Measured on the headhouse parapets: per body each parapet came back as mixed `wall` leaves and
`roof` caps; per element all four are `wall`, the roof layers stay `roof`, no ambiguity.

A leftover from that move, caught by review on 2026-08-16: `wall_faces` still filtered its
members per body (`[i for i in members if roles[i] == WALL]`), and both its comment and
CLAUDE.md said the face selection was still decided per body. It cannot be — `roles` returns
the element's value for every member, so the filter admits all of `members` or none. Verified
on all three substrates: no element is mixed. The filter now reads the element's role once and
says so, and `wall_faces` returns byte-identical masks on the rig and both parapet exports. The
membrane's face set is *identical* either way — so the old answer was accidentally right, for
the wrong reason. The membrane skirt goes 8 → 62 faces, covering all four parapets rather than
the single leaf body that happened to touch the roof, which is a fix.

**Who caps the parapet: both, decided 2026-08-16.** With role on the element, `cladding_faces`'
"every wall top" claims the coping the membrane is already carrying over — **12 faces belong to
both skins** (4 + 4 + 2 + 2 across N/S/W/E). That was this file's long-standing "which skin caps
a wall?" question arriving for real. It was never a geometry failure: after Duncan re-tuned the
parameters on 2026-08-15 the two skins sit 77.000 mm apart, exactly their offset difference, so
nothing collides. It was a modelling decision, and the answer is the third of the three readings
that were on the table:

1. ~~membrane caps it~~ — `facades | (up & of_role(WALL) & ~climbed)`, smallest change, would
   have kept the two skins disjoint;
2. ~~cladding caps it~~ — the membrane stops at the top and turns out, using the existing flange;
3. **both, deliberately** — which is what real parapet construction does (membrane upstand, metal
   coping over) and what the rig already did on the sloped tops of parts 1 and 2.

**So no predicate changed; what changed is that the overlap is now asserted rather than merely
occurring.** `test_both_skins_cover_the_coping_and_stack_rather_than_collide` pins three things,
because "the skins overlap" is otherwise indistinguishable from a bug:

- the shared set is non-empty, so narrowing either predicate to reading 1 or 2 fails the test —
  verified by patching `cladding_faces` to reading 1 and watching it go red;
- the shared set is **only** sloped wall tops. A facade or a roof face in there would be two
  skins covering one surface for no reason, which is not what was decided;
- the two copings **stack in the right order** — cladding outboard of membrane, by the offset
  difference. That, not separation, is the property worth pinning: the skins are *supposed* to
  be close there.

The gap is the offset difference only to within what the sloped planes absorbed, so the test
reads each patch's own `slope_deviation` rather than a constant. A coping is sloped, hence
least-squares, hence not exactly parallel-offset. On the real parapets that is a tight bound —
77.000 mm ± 1 µm, deviations 0.119 and 1.266 mm. On the synthetic rig it is loose: 80.0 and
81.9 mm against 77, because the rig's tops are steep (1:8 and 1:11, against the parapets' 1.36°)
and the 85 mm cladding absorbs up to 6.036 mm there. The rig is the harsher case, as intended.

The open item this leaves is the brick one below, and it is narrower than it was: with "both"
settled, a coping comes from the cladding skin regardless of which system clads the wall beneath
it, so a brick wall gets a rainscreen coping unless Duncan says otherwise.

**The cladding stops at the ground, decided 2026-08-16.** The other open item Duncan had been
sitting on. Untrimmed, the facades mitre with the substrate's unskinned underside and hang the
full offset below it — z = −0.085 on the rig. Correct as offset geometry, wrong as building.

It is authored, not hardcoded: a new per-skin `base` in `skin-parameters.yaml` (`0.0` for the
cladding, `null` for the membrane, which never reaches the ground), a `base` argument on
`skin_over`, and `_trim_below` in `skin/offset.py`. Three things that were decided while
building it, none of them obvious from the outside:

- **A cut, not a clamp.** Pushing the low vertices up to z = 0 gives the same outline and
  silently tilts the bottom of every sloped panel off its offset plane. Nothing would report it
  either — `offset_residual` is computed in `planar_offset`, long before any trim. So the
  straddling triangles are re-cut against the plane instead, and a test asserts that every
  surviving vertex is *exactly* where the offset put it (measured: max movement 0.0) and that
  every remaining face plane still matches one the offset produced (worst 6e-16).
- **Crossings are cached per edge.** Two triangles sharing a cut edge would otherwise each
  compute their own intersection, agreeing to a rounding rather than being one vertex, and the
  seam between them would crack. The 9 datum vertices on the cladding are 9 distinct points.
- **`null` is not `0.0`.** For `drop` and `out`, zero is the feature switched off; for `base`,
  zero is a real height to cut at. So no-trim had to be spelled `null`, and STRICT-COMPLETE
  still applies — the key is required, and an omitted `base` is refused rather than read as
  "not trimmed". `check_seeds` ignores it: a datum in the model is not a distance between two
  surfaces, so it cannot make a swap invisible the way two equal offsets can.

The trim runs last, after the hems and the turn-outs, so it means "no part of this skin goes
below the datum" and not "the offset stops there". Cladding border edges go 19 → 23; residual,
clearance and separation are all unchanged.

Two bugs in the first cut of it, both found by `/code-review` the same day and both fixed:

- **A tolerance band on the side test extrapolates.** `above` was `z > base - PLANE_TOL` while
  `crossing` interpolates to exactly `z == base`. A vertex inside the band but below the plane
  is then called above, and the interpolation — solving for a plane that vertex is already past
  — runs its parameter negative and puts the cut vertex *outside* the edge it was cutting. A
  near-horizontal triangle 1 mm across, half a micron under the datum, came out 333 mm across.
  The side test is now exact; the tolerance belongs on the positions, where the duplicate-corner
  drop already applies it. A band was the obvious thing to write and it is the wrong instinct
  here — worth remembering if a tolerance is ever added back.
- **A datum above the whole skin returned no faces at all**, and the empty mesh crashed inside
  trimesh with `IndexError: too many indices` from `is_watertight`. Authoring `base` in the
  wrong datum — site elevation where the model is building-local — is an ordinary mistake, so
  it now raises naming `skins.<name>.base`. **On the real substrate `base: 0.0` currently cuts
nothing** — the headhouse parapets sit at z = 14.02–14.75 — so the number to author there is a
real ground level, and it only starts to bite once walls that reach the ground are in the bake.

## Layout

| file | what |
|---|---|
| `skin/offset.py` | the solver. `planar_offset` (one constrained system), `skin_over` (union → offset → select faces → skirt → flange → trim), `Faces` (what a predicate may ask) |
| `skin/measure.py` | `clearance` (skin to substrate), `separation` (skin to skin) |
| `skin/substrate.py` | `polyhedron` (from vertex/face lists), `from_obj` (a baked export, one part per `o` group), `snapped`, `prism`, `cube`, `l_block`, `u_block`, and `classify` / `horizontality` (WALL vs ROOF from shape) |
| `skin/export.py` | OBJ writer that emits n-gons, not triangles. `write_obj` one per file for `build/`, `write_objs` many as `o` groups for a whole substrate |
| `skin/parameters.py` | the parameter layer. `load` / `validate` / `check_seeds` / `load_validated`. The only module that imports yaml or jsonschema |
| `skin-parameters.yaml` | every tunable number: `classify`'s thresholds, `fall`, the five distances |
| `skin-parameters.schema.json` | the JSON Schema it is validated against |
| `build.py` | the substrate as transcribed data, the `RULES` table, `skins()`, and the build |
| `blender/display.py` | the only file that imports bpy. Loads, never authors |
| `tests/test_offset.py` | the geometry suite |
| `tests/test_parameters.py` | the parameter-layer suite |
| `tests/test_import.py` | the OBJ import suite |

## The two skins

Numbers in `skin-parameters.yaml`, face rules in `build.py`'s `RULES`, joined by name by
`skins()`. Adding a third is a YAML entry plus a rule set, not a code path.

**The numbers are tuned for the student-house substrate now** (2026-08-15). The synthetic
rig was built slightly off scale, and when the parapet export arrived Duncan re-tuned
`skin-parameters.yaml` to it; the rig inherits the same file. It still builds clean —
residuals ~1e-16, no self-intersection warning — so the figures below are the rig's
*current* output, not its original one. **The rig has served its purpose and is unlikely
to be needed again; if it is, the smaller `drop` and `out` values suffice** (Duncan's call,
in preference to giving the headhouse its own parameter file).

| | Membrane (8 mm) | Cladding (85 mm) |
|---|---|---|
| part 3's roof | covers | — |
| interior (step) walls | climbs | skirts 30 mm |
| sloped tops of parts 1 & 2 | covers | covers |
| exterior walls | skirts 62 mm | climbs |
| part 4's exterior face | stops against it; every panel turns out 205 mm | climbs |
| part 4's sloped top | bare (membrane stops on the wall) | wraps over |
| part 4's interior face | — | skirts 30 mm |
| part 4's ends and bottom | bare | bare |

Measured separation **76.071 mm** — the offsets differ by 77 mm, less the opposing slope
deviations. Checked on every build; clearances 7.7760 mm and 84.6091 mm. It dropped to
20.4 mm while part 4's exterior face was skinned by the membrane alone; giving the cladding
the same face restored it. (It read 64.215 mm under the pre-2026-08-15 numbers, which is
what the earlier entries in this file quote.)

**Skin distances are non-degenerate seeds** (student-house CLAUDE.md, hard rule): no two
of the five are equal and none is an integer multiple of another. `Membrane.drop` and
`Cladding.distance` were both 0.100 until 2026-08-14, which meant a bug swapping a skirt
depth for an offset distance produced identical geometry — invisible to the tests and to
the eye. Keep them distinct when tuning.

**Exterior and interior are named off the slope on the part's own top**: the wall under
the high edge is the exterior face, the wall under the low edge is the interior. Parts 1
and 2 already followed this; part 4 does too, which puts its *exterior* face at
y = -7.673195, facing back into the substrate. Ends and bottoms are neither.

**That rule is now derived rather than listed** (2026-08-14). `uphill` reads each wall's
fall off its own top and `wall_faces` sorts its vertical faces by it, which retired
`STEP_X`, `STEP_Y`, `FACE_4_EXTERIOR`, `FACE_4_INTERIOR`, `NOT_OUTSIDE`, `_part_face` and
every `owner`-index set — all of them this rule worked out by hand. Verified by comparing
all five face masks against the hand-fitted predicates: identical, face for face.

Two things the naive form got wrong, both now handled:

- **A facade wraps a corner.** Part 1's +X face is an *end* by its own fall, but it is
  coplanar with and joins part 2's +X facade, so it is a return of that facade and is
  grown into the exterior set. Its -X face has no such neighbour and stays bare.
- **Climb-or-flange is per wall, not per face.** Only one triangle of a step wall shares
  an edge with the roof, but the membrane climbs the whole face. Touching faces elect the
  wall; the wall then carries all of its own faces. Testing per face skinned half a step
  wall and left the flange plane too small to miter the skirt against — which read as a
  0.0001 mm clearance.

The skirt's drop is measured from the **substrate** edge, not from the skin surface —
the pre-existing convention, pinned by a test. The turn-out is different: it is measured
from the **skin** edge it springs off, because it is defined on the skin's own panels
rather than on a substrate feature. All four turns are therefore exactly `out`.

**The turn-out rule.** Where the membrane stops against part 4's exterior face, every
panel that ends there turns out `out` along the axis it faces, so the whole termination
folds outward as one collar rather than the roof alone climbing:

| panel | normal | turns |
|---|---|---|
| part 3's roof | (-0.078, 0, 0.997) | +Z |
| part 2's top | (-0.119, 0, 0.993) | +Z |
| the step-wall climb | (-1, 0, 0) | -X |
| the exterior-wall skirt | (+1, 0, 0) | +X |

The direction is the **dominant axis** of the panel's own normal, not the normal
verbatim: that keeps a turn off a shallow slope exactly vertical, matching the priority
the solver gives level planes.

Those four panels form one chain around the wall, and their outer edges are **mitered**
where they meet — the intersection of the two outer lines, exactly as `planar_offset`
treats a corner, but in the wall's plane. The miter cuts both ways: two of the joints
were gaps that it extends, one was an overlap that it trims.

| joint | miter (x, z) | before |
|---|---|---|
| roof \| step wall | (0.420966, 1.751187) | panels overlapped ~276 mm |
| step wall \| top | (0.420966, 2.236081) | open corner |
| top \| skirt | (1.893496, 2.411995) | open corner |

**Cladding system is authored, not derived** (2026-08-14). Geometry says which faces
are facades; the *part* says which system clads them, via `part.metadata["facade"]` and
`Faces.tagged`. This is a different kind of fact from the plane coordinates that were
just retired: those encoded a rule the slope could derive, whereas no property of a
wall's shape implies brick. The student-house has a brick street front at X = 0 and a
rainscreen headhouse set well back — **both facing -X** — so neither a compass direction
nor "the frontmost plane" can separate them. Material can, and it is authored anyway.

`check_facades` refuses any facade claimed by no declared system, which is the failure
that would otherwise be silent: an unstamped part drops out of every skin and leaves a
bare wall, or a whole system emits as an empty mesh. The sample cannot pose the brick
condition at all — it has no -X-facing facade — so a purpose-built two-facade fixture in
the tests carries it.

## Why the offset is over-determined

A sloped top over a concave plan puts **four planes at a corner**, and four offset planes
are not generally concurrent. Worse, the two ends of a hip impose contradictory demands:

    0.9929·o₁ − 0.9961·o₂ = ∓0.003148

Offsetting the walls moves the hip's endpoints in plan, but two planes parallel to their
originals can only intersect along a line parallel to the original hip. **No choice of
offset distances resolves it** — hence the constraint priority in `CLAUDE.md`, which
lands the error on the sloped planes.

Solved as one KKT system. A nullspace basis was tried first and leaked ~2 mm of
constraint violation through near-null directions; KKT holds them to ~1e-16. `RIDGE`
keeps it non-singular where the soft equations underdetermine a vertex.

## Hard-won facts

- **manifold3d computes in float32.** Every vertex it returns survives a float32
  round-trip bit-for-bit, so a union's faces sit up to ~5e-7 m off their true planes at
  metre-scale coordinates. Don't set tolerances tighter than the boolean kernel can
  deliver — an earlier 1 nm threshold produced a bogus self-intersection warning.
- **Booleans do not repair a self-intersecting offset.** `trimesh.boolean.union([bad])`
  is a no-op: the mesh is topologically manifold, only *geometrically* self-intersecting,
  so manifold3d has nothing to resolve. `clearance()` detects the condition; nothing
  fixes it yet.
- **Nothing in the stack ships a planar offset.** Not trimesh, not manifold3d (it has
  `minkowski_sum`/`minkowski_difference` — rounded, not mitered). The solver is ours.
- **`trimesh.util.concatenate` + `closest_point` crashes** when parts share a face —
  coincident duplicate triangles produce ties. `clearance` queries per part instead.
- **`clearance()` cannot see a skin buried inside a part.** `closest_point` returns an
  unsigned distance, so a panel sitting *within* a solid still reports its distance to the
  nearest surface — a healthy-looking gap. An upstand extension that ran back into part 2
  read 19.4399 mm with no warning; only `part.contains()` caught it. Anything that
  generates geometry sideways rather than outward must test containment itself.
- **`separation()` cannot prove two skins are apart.** It samples vertices and face
  centroids only, so a surface can pass clean through another between samples and still
  read positive. An earlier out-of-plane version of the membrane's return pierced the
  cladding in 12 places while `separation()` reported a reassuring 4.126 mm — the fault
  was found by segment-vs-triangle, not by this. Its docstring always said it was an
  upper bound; treat
  it as a smoke alarm, not a proof. A real test is segment-vs-triangle (Möller-Trumbore)
  over both edge sets — see the open item.
- **Bounds cannot tell a wall from a roof.** A 10 × 0.3 × 3 wall rotated 45° in plan has
  AABB extents `[7.283, 7.283, 3.0]` — thinnest vertically, so a bounds test calls it a
  slab. Face normals and the *oriented* box both still read it correctly.
  `substrate.classify` uses both and raises when they disagree. Measured horizontality:
  parts 1/2/4 (walls) 0.311 / 0.260 / 0.098, part 3 (roof) 0.602. The roof's margin is
  the thinnest of the set, and only because it is a section-cut fragment — 1.456 m of cut
  face is posing as slab edge. A real slab of that plan at 300 mm scores about 0.94, so
  the sample understates the separation.
- **A "top" is a face that points up, not one that is off-axis.** `_upward` tests the
  sign of `n_z`. Testing `abs(n_z)` asks a different question and is wrong twice: a
  sloped soffit reads as a top, a flat top is missed. This substrate can prove neither —
  every top here slopes, every underside is exactly horizontal — so a purpose-built part
  in the tests carries it. Both cases are ordinary in the student-house.
- **`polyhedron()` cannot re-wind an inconsistent face list here.** Its docstring
  promises any winding works, but `trimesh.repair.fix_winding` needs **networkx, which is
  not installed**. It returns early when `is_winding_consistent`, so the four transcribed
  parts never reach it and the gap stays hidden. The first inconsistently-wound part
  raises `ModuleNotFoundError`. Either install networkx or wind transcribed lists
  outward — this will bite when parts start arriving from IFC.
- **Occlusion needs no code.** Where one part stands against another's face, that region
  is interior to the union and never reaches a skin, so a face predicate that selects a
  whole plane still yields only the exposed remainder. Part 4's exterior face is selected
  in full and comes back trimmed to the profile above parts 2 and 3's tops, plus the
  full-height +X overhang. Do not write occluder lists.
- **Reflex corners miter exactly.** Three planes always meet at a point; an outward
  offset at a concave corner is sharp and correct. The real failure mode is a concave
  *pocket* narrower than 2× the offset, where opposing walls cross.
- **trimesh is triangles-only.** `skin/export.py` regroups coplanar triangles via
  `mesh.facets` and writes boundary loops, so Blender shows quads. Collinear vertices
  on a loop are kept deliberately: dropping one that a neighbouring facet corners on
  would leave a T-junction.
- **Face indices quoted in conversation** ("face 0 of 1") have so far matched between
  Blender's polygon order and the transcribed lists — but check both before acting on
  one.
- **A near-identity rotation can split one coordinate across the snap grid.** Part 4
  ("Cube") carries a ~4.4e-8 skew in `matrix_world`, which spread what is a single local
  coordinate over 2.4e-7 m of world values — straddling a 1 µm boundary, so rounding the
  world values independently gave 2.321662 and 2.321661 for the same plane. Read
  `matrix_world` and the local `co` when transcribed coordinates disagree in the last
  digit; cluster before snapping rather than rounding each vertex on its own.

## The scupper, and folds (2026-08-16)

`headhouse-parapets-clt-insulation.obj` would not skin; the no-scupper export would. Chased to
the end, and worth recording in full because almost every intuition along the way was wrong.

**The defect.** Two vertices of the union, at (8.5, 4.885, 14.499309) and (8.5, 5.085, 14.499309),
each lie on a **+X and a −X plane at once**. The insulation taper's edge lands on exactly the
plane the parapet's inner leaf ends on, x = 8.5. Along most of that contact the two coincident
faces cancel as interior, but the scupper is a hole through the parapet, so through the opening
the taper's end face is genuinely exposed. The pinch is the boundary between cancelled and
exposed, and it sits on the taper's own top edge. Neither object has a vertex there — the boolean
creates it, where the scupper jamb plane y = 4.885 cuts the taper's sloping top edge.

Offsetting asks that one point to move +85 mm and −85 mm in x simultaneously. The hard system is
inconsistent by exactly `distance`; `|Ht − h|` = 0.085.

**What the old error said, and why it was useless.** It named vertex 74 — on the *S* parapet, 5 m
away, with a single incident plane and no level-edge rows, i.e. the least constrained vertex in
the system, where the contradiction's Lagrange multipliers pooled. Re-run on a slightly edited
scene it named vertex 49 instead. It also fired on *displacement magnitude*, which scales linearly
with the offset (765 × distance here), so the guard tripped above ~9.8 mm and **at the membrane's
8 mm the file "succeeded" with a vertex flung 6.12 m**. Silently.

**Ruled out, each by measurement, not argument:**

- *Nudging the taper 1 mm in x* fixes it completely (verified from 1 µm to 10 mm; 1 µm is only
  2× manifold3d's float32 floor, so 1 mm is the number to use). Not available: the taper is
  generated by the student-house pipeline.
- *Lowering the scupper sill 1 mm* — Duncan tried it in the scene. No effect whatever: the pinch
  is at the **apex** of the exposed wedge, fixed by the taper's own slope, and the sill only sets
  its base.
- *Opening the scupper to the sky* — no effect on the fold either, for the same reason.
- *Raising the sill clear of the taper* removes the fold, but ponds water at the drain and turns
  the sill into an exposed wall top that `cladding_faces` then clads: separation 77 mm → 3.7 mm.
- *Splitting the folded vertex* is not available. Its six (resp. seven) faces form a **single**
  edge-connected fan wrapping from the parapet's inner face round to the taper's end, so there is
  no two-sided partition to tear along. Splitting by owning part solves the system but tears the
  membrane's own corner apart. This is the "self-intersection repair" open item arriving for real.

**The fix that landed: `_reconcile`.** The face that creates the contradiction — the exposed
−X wedge — is covered by *no* skin. It contributes a constraint only because `planar_offset`
solves over every face of the union. So: at a contradictory vertex, and only there, re-read the
planes from the covered faces alone; raise if the contradiction survives among them. See
CLAUDE.md for the invariant. The rig and both parapet exports come back byte-identical.

**What it cost, and what it revealed.** The scupper file now solves — but the cladding came back
with clearance 0.000 mm, and `build.py`'s own check flagged it: *85.000 mm inside the requested
offset — self-intersecting*. Independent of the fold, and previously invisible because the solve
failed first: `cladding_faces`' "every wall top" claims the five upward faces of the scupper's
**sill**, and an 85 mm offset cannot fit inside a 76 mm tall opening. Not a rule to fix — see the
slot decision below, which makes the sill genuinely sky-facing and the claim correct.

**Decisions, Duncan, 2026-08-16.**

- **The uncovered sliver is acceptable.** A degenerate sliver no skin covers is now tolerated
  rather than refused. `build.py` prints the folds so it is not silent. Note the sliver is a
  *historical* case: all three committed exports union to one component, smallest part 2.264e-3 m³,
  thinnest 29 mm. It survives only as literals in `tests/test_import.py`.
- **The scupper becomes a slot, and much bigger** — built upstream, not here. Verified: a slot
  open to the sky restores cladding clearance to a clean 85.000 mm at both 200 mm and 600 mm
  width, because with no soffit the sill and soffit stop offsetting into each other. The
  geometric floor is 2 × the cladding offset = **170 mm** of width; above that the geometry has
  no opinion, so size it for debris and for the roofer. **The fold survives all of it** — it is
  the x = 8.5 flush contact, orthogonal to slot-vs-hole and to size — so `_reconcile` is needed
  regardless.

**Waiting on the slotted substrate.** Two things to check when it arrives, both Duncan's:

- The membrane should **turn up** where it now stops flat at the scupper cheeks. In the current
  build those are the horizontal edges at z = 14.502 running x = 8.072 → 8.492, at y = 4.893 and
  y = 5.077 (the jambs offset in by the 8 mm allowance). Edge indices will not survive a new
  substrate; the coordinates are the record.
- Two membrane edges at x = 8.508 climbing from the fold vertices are **7.655 mm off vertical**
  over 55 mm. That is the fold's own fingerprint: the jamb plane is one of the planes
  `_reconcile` drops, because the membrane does not currently cover the jamb, so the fold vertex
  gets no y displacement while the vertex above it gets the full 8 mm. Duncan's expectation that
  the turn-up will fix them is **confirmed by measurement**: add the jamb faces to `covered` and
  the fold vertex keeps 3 planes instead of 2 and moves exactly 8.000 mm in y, making the edge
  vertical. Cover more, and the constraint comes back — which is the rule behaving as designed.

## The walls-and-caps bake (2026-08-19)

`headhouse-walls-parapets-caps-clt-insulation.obj`: leaves removed from walls and parapets, cap
plates separated into their own objects, the scupper built as a slot. 18 parts, 16 elements. It
skins, and the numbers are the best yet:

| | faces | residual | clearance | slope absorbed |
|---|---|---|---|---|
| Membrane (8 mm) | 30 | 3.82e-17 | 7.8808 mm | 0.158 mm |
| Cladding (85 mm) | 47 | 8.60e-16 | 85.0000 mm | 1.683 mm |

Separation **77.000 mm** — exactly the offset difference. No self-intersection warning; neither
skin has a vertex inside a part; a Möller-Trumbore pass over both edge sets against both
triangle sets finds **zero** crossings, skin-to-skin or self. `python3 build.py <bake.obj>`
builds it, and `tests/test_import.py` now reads it, which closes the "nothing reads these
exports" item for this one.

Two things had to be built to get there, and both were open items rather than surprises.

### Ear clipping, because the fan is not enough (was Duncan's call, now settled)

The reader refused the file outright: 14 of its faces are notched, and **6 are star-shaped from
no vertex at all**, so no rotation of the loop would let a fan tile them. The slot is the clearest
case — a rectangle with a bite out of the middle of one edge is never star-shaped.

`_triangulated` ear-clips in the loop's own plane. Written rather than imported because nothing
here will do it: `mapbox_earcut` and `triangle` are both absent, and trimesh's remaining engine
routes through manifold3d, whose float32 is the thing `substrate.union` already shifts to the
origin to avoid. Verified against that engine anyway — every clipped loop's area agrees to
**2.4e-16 relative**, and rebuilding each part with the two tilings gives volumes agreeing to
< 1e-12 m³.

What it still refuses is a loop that is **not simple**: ear clipping a self-crossing loop returns
perfectly well-formed triangles covering the wrong region, so the check is that the tiled area
equals the loop's own. A symmetric bowtie does not even reach it — its Newell normal cancels to
zero and it raises for having no plane — so the test uses a skewed one.

This also settles the standing `_fan_is_valid` collinear question, and in the direction of
accepting both readings. A corner with no area is used as an ordinary triangle vertex where an
ear is available there and dropped contributing nothing where one is not; either way no zero-area
triangle reaches the mesh. Duncan's framing was "refuse both or accept both"; the clip accepts
both *faithfully*, which neither option on the table quite was.

### `rise`, because every wall is now flat-topped

With the caps separated, **no wall element has a slope of its own**. `uphill` raised on all eight
— four walls and four parapets — and the only sloped elements left are the cap plates (1.364°,
classifying `roof` on their own) and the insulation taper. That is this file's oldest open item
arriving in full: a stacked panel must take its direction from the parapet above it.

`rise(faces, members)` tries `uphill` and, on a flat top, walks up. Recursive, because the stack
is three deep here: wall → parapet → cap, and only the third has the fall.

**What counts as the lift above** took two attempts, and the failed one is worth keeping.

*First attempt — rests on it, and shares any vertical plane.* Every wall came back "carried by"
all four parapets, because the walls' **end** planes are shared right round the perimeter: the
E parapet's x = 8.08 face is the same plane as the N wall's end. `Headhouse-N` resolved to
(+1, 0) — flatly wrong, and its −Y facade would have read as an end.

*What landed — rests on it, overlaps it in plan, and is flush on **both** faces across its
thickness.* Both, not one, because the caps of this bake overlap at the corners rather than
mitring: `CapPlate-Headhouse-W` runs over the end of `Parapet-Headhouse-S` and is flush with its
y = 7.54 face, the building's outer plane, which everything at that corner shares. It is not
flush with y = 7.12, so it is not another lift of that parapet. The opposed pair separates them
exactly, with nothing to author.

Weighting the strays down by area instead was tried and rejected: it gave `Parapet-Headhouse-N`
(+0.0794, −0.9968) rather than (0, −1). That still classifies correctly against `fall = 0.707`,
which is exactly why it is the wrong thing to ship — a few degrees of tilt that depends on how
long the walls are and passes anyway.

With it, all eight walls resolve to **exact** axis directions: N (0, −1), S (0, +1), E (−1, 0),
W (+1, 0), each panel agreeing with its parapet. `Roof_Headhouse_CLT` still raises, and does not
matter: it is a `roof`, and `wall_faces` never asks.

The plan-overlap test is the one bounds test in it, and it is only a necessary condition on two
elements already known to be flush and in contact — it separates the lift above from a distant
one in the same plane. Nothing turns on where its box came from, so the `classify` objection to
bounds does not apply.

**Nothing else moved.** The synthetic rig's build output and both skin OBJs are byte-identical,
and both parapet exports skin to identical vertex hashes. `headhouse-walls-parapets-insulation.obj`
still raises `AmbiguousPart` on a 0.42 × 0.42 × 1.675 block, unchanged and pre-existing.

### The three folds are all x = 8.5

Vertex 9 at (8.5, 2.85, 12.595) is the knife corner where the E and N walls meet — this file's
failure 1 from 2026-08-15, still there in a milder form. Vertices 23 and 34 at (8.5, 4.785,
14.5036) and (8.5, 5.185, 14.5036) are the two jambs of the scupper slot. Exactly as predicted
on 2026-08-16: the fold is the x = 8.5 flush contact between the parapet's inner face and the
insulation taper's edge, orthogonal to slot-versus-hole and to slot size. `_reconcile` handles
all three and the cladding's clearance is a clean 85.000 mm, which is the slot doing its job —
the hole version still reads 0.000 mm.

### What `/code-review high` caught (2026-08-19)

Four findings, one of them a defect in code that has been committed since 2026-08-16 and that
nothing would ever have reported.

- **`_opposed` compared un-normalised normals.** `_vertex_normals` quantises to the `PLANE_TOL`
  lattice, so a *sloped* normal comes back with `|n|` up to ~8e-7 short of 1, and an exactly
  antiparallel pair dots to `-|n|^2` rather than -1 — which can sit above `-1 + PLANE_TOL`.
  Measured over 20 000 random sloped normals: **3.65% of genuine contradictions went
  undetected**. That is the worst failure available here — `_reconcile` never runs, nothing
  appears in `metadata["folds"]`, and the solve silently splits the difference, which is exactly
  what the fold work was written to make structural. Axis-aligned normals are snapped to exact
  units upstream and were always fine, which is the only reason it had not bitten: every fold
  met so far has been axis-aligned, including all three in this bake. Now compared as unit
  vectors, with a test over 4 000 sloped normals.
- **`rise` let one dead-end lift cost the whole wall its direction.** The recursive call was
  unguarded, so a flat branch raised out of the loop instead of contributing nothing — a parapet
  over part of a panel with a plinth over the rest raised, though the parapet named the sides
  perfectly well, and the area weighting the docstring promised never ran. Fixed, and only a
  wall with no direction anywhere above it raises now.
- `seen` was a global visited set rather than a per-path cycle guard, so a cap spanning two
  parapets of one wall was counted under the first and skipped under the second. Fixed while the
  review was still running.
- The coping (below) — which is a modelling decision, not a defect, and is Duncan's.

The review also fuzzed the ear clip against 4 000 random simple polygons with no failures,
independently of the 45 awkward ones (combs, stars, spirals) checked against shapely here.

### Who caps the parapet: both, again — Duncan, 2026-08-19

Separating the cap plates reversed the 2026-08-16 "both skins cap the coping" decision **by
accident**, and the reversal was in the substrate rather than in the code. With each plate its
own element, a 29 mm slab classifies `ROOF`, so `cladding_faces`' "every wall top" stopped
reaching any coping and the membrane covered the plate as roof instead. Measured before the fix:
cladding stopped at z = 14.718, *under* the cap, while the membrane ran over the top of it at
14.755 — the parapet head built upside down.

Duncan's answer: the cap plates are skinned by both skins, exactly as they were when integrated
with the parapet. `group_caps` does it, and the rule is derived rather than a name match on
`CapPlate-`: **a lift that classifies `ROOF` while the element it rests on classifies `WALL` is
that wall's cap**, joined to it by re-stamping `metadata["object"]`. `_next_lift` already
computes "rests on and continues", so nothing new is measured — it is the relation `rise` walks,
used a second time.

It groups the cap and **not** the parapet below it, and testing the lift's *own* classification
is what makes that fall out: a parapet reads `WALL` alone and stays a separate element. Merging
the whole stack was considered and is wrong for an independent reason — the climb-or-flange
election is per wall, so a wall merged with its parapet would have the membrane climb its full
height rather than stopping at the parapet the roof runs into. Occlusion would not save it: the
wall's inner face below z = 14.025 is the inside of the building and genuinely exposed.

| | before grouping | after |
|---|---|---|
| elements | 16 | 11 |
| Membrane | 30 faces, z ..14.7552 | 50 faces, z ..14.7552 |
| Cladding | 47 faces, z ..14.7180 | 81 faces, z ..**14.8340** |
| shared faces | 3 | **13** |
| separation | 77.000 mm | 77.000 mm |

The 13 are the 10 sloped plate tops (five plates, two triangles each) plus the 3 exactly
horizontal faces of `Parapet-Headhouse-E` beside the scupper slot, which no plate covers and
which are a genuinely exposed flat wall top. Cladding over membrane over plate, in that order,
and the Möller-Trumbore pass still finds zero crossings.

`group_caps` is **inert** on both earlier parapet exports — their plates already sit inside the
parapet objects, 7 elements before and after — and idempotent, so `build()` may run it
unconditionally.

### Still not fixed here

The membrane still **stops flat at the scupper cheeks** rather than turning up — the jamb faces
at y = 4.785 and y = 5.185 are covered by neither skin, and the fold vertices are exactly the
ones `_reconcile` drops planes at. The 2026-08-16 measurement stands: add the jambs to `covered`
and those vertices move the full 8 mm and the edges come vertical. Unchanged, and still Duncan's.

## Open items

- **The brick skin is not built.** Everything it needs exists — `BRICK`,
  `facades_of(faces, BRICK, fall)`, `CLADDING_SYSTEMS` — but no part in the sample is
  stamped brick, so adding the `skins:` entry and its rule set would emit an empty mesh
  and test nothing. It needs a
  substrate that poses the condition: two walls whose tops fall +X, one at the front
  plane and one set well back, only the front one brick. The two-facade fixture in
  `tests/test_offset.py` is that condition in miniature.
- **Which skin caps a brick wall?** `cladding_faces` takes *every* wall top regardless of
  facade system, so a brick wall would get a rainscreen coping. Plausible — brick with a
  metal cap is normal — but it is an assumption, not a rule Duncan gave. The 2026-08-16
  "both cap it" decision settles who caps a wall and not which *system* does, so this
  survives it unchanged; it only becomes testable once the brick skin exists.
- ~~**A flat-topped wall panel cannot name its own facade.**~~ Built 2026-08-19 as `rise` +
  `_next_lift`; see above. What is left of it: the walk needs the lift above to be **in
  contact**, so two lifts of one wall with a floor slab between them do not resolve. It raises
  naming the element rather than guessing, which is right, but the student-house will meet it.
- **The substrate reader for the student-house side does not exist yet.**
  `current_substrate()` returns transcribed literals. Its replacement must pull evaluated
  meshes in world space off the Bonsai IFC objects, snap to 1 µm **clustering before
  rounding** (see the `Cube` rotation-skew entry — real IFC parts nearly all carry
  placement transforms), and write nothing back. Emission is already safe: `build()`
  emits skins only unless `emit_substrate=True`, and `display.reload()` skips substrate
  entries unless asked.
- **No exact skin-vs-skin intersection test exists.** `separation()` missed a genuine
  12-place intersection during the turn-out work. Worth promoting the Möller-Trumbore
  check from the scratch script into `skin/measure.py` as `intersects(a, b)` and asserting
  it in the build.
- **The cladding overhangs part 4's bare ends by the offset**, reaching x = -3.169769 and
  x = 2.421661 where the wrapped top mitres with the unskinned end planes. Same family as
  the z = −0.085 hang that `base` now trims — every skin edge does this against an
  unskinned neighbour — but the trim does not reach it: `base` is a horizontal datum, and
  a bare end is not a datum the model shares, so there is nothing in plan to author. Still
  open, and a different thing to specify.
- ~~**`_fan_is_valid` treats a redundant collinear vertex as concavity, but only next to
  vertex 0.**~~ Settled 2026-08-19 by ear clipping, which accepts both readings faithfully —
  the corner is an ordinary triangle vertex where an ear is available there and is dropped
  contributing nothing where one is not. `_fan_is_valid` itself is unchanged; it is now a
  *routing* test ("can the fan have this one?") rather than a refusal.
- **Three of the four headhouse OBJ exports are committed and nothing reads them** —
  `headhouse-parapets-clt-insulation{,-no-scupper}.obj` and
  `headhouse-walls-parapets-insulation.obj`. The current bake is read by
  `tests/test_import.py` as of 2026-08-19, so its figures are a regression check; the older
  three are still unfalsifiable notes. The last of them does not even load —
  `AmbiguousPart` on a 0.42 x 0.42 x 1.675 block — so it cannot become one without work.
  They are superseded rather than useful; propose deleting them.
- **Part 3's top is not planar** — three corners at z = 1.456084 and one at 1.156084,
  300 mm out of plane, held as two triangles. Skinned faithfully as two planes. He
  described it as "prismatic with a sloped top", so this may be unintended.
- **Sparse solver.** The dense KKT is roughly cubic: 0.195 s at 128 verts, 2.33 s at
  256, 19.65 s at 512. Substrate expected to reach hundreds, not thousands. Plan:
  build rows as COO triplets rather than dense `np.zeros(3V)` vectors (that alone is
  O(V²)), assemble with `scipy.sparse.bmat`, solve with `spsolve`, and regularise the
  zero block with `−δI` so redundant constraint rows don't make it singular. ~20–30
  lines. Verify against the residual, don't assume.
- **Shapely refactor is on hold.** The idea was that vertical faces are exactly a 2D
  mitred buffer (`buffer(d, join_style="mitre")` — verified sharp, exact). It fails
  because the substrate is not a single extruded polygon but a **2.5D stepped solid**:
  the step walls above part 3's roof are vertical faces *interior* to the plan, which
  a buffer of the outer outline cannot see. Would need per-height-region buffering plus
  reconciliation, and the over-determination reappears at the reconciliation.
- **Self-intersection repair** is unsolved. Detection works; the likely construction is
  offsetting each face into its own half-space solid and unioning those.
- **T-vertices** appear where a skirt stops beside a fully-covered neighbouring face.
  Currently none, since the two walls that caused it were excluded — but it returns if
  a skirt again abuts a full-height face.
