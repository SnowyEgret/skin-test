# skin-test — state of play

Offsetting a **substrate** (an assembly of solid parts) outward by a fixed distance to
produce **skins**: open surfaces that cover a chosen subset of faces.

Last worked: 2026-08-15.

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
`skin-parameters.yaml`. 42 tests, ~1.6 s.

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

**The detached sliver, and the guard it produced.** The no-scupper export still leaves one
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

**Next wall.** Every leaf reports `uphill: flat top`; only the caps have a fall. So the
exterior/interior rule still cannot run on the leaves — it needs to take its direction from
the cap above, which is the open item this file has carried from the start. The no-scupper
parapet export is a good dataset to build it against.

## Layout

| file | what |
|---|---|
| `skin/offset.py` | the solver. `planar_offset` (one constrained system), `skin_over` (union → offset → select faces → skirt → flange), `Faces` (what a predicate may ask) |
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

| | Membrane (20 mm) | Cladding (85 mm) |
|---|---|---|
| part 3's roof | covers | — |
| interior (step) walls | climbs | skirts 225 mm |
| sloped tops of parts 1 & 2 | covers | covers |
| exterior walls | skirts 145 mm | climbs |
| part 4's exterior face | stops against it; every panel turns out 310 mm | climbs |
| part 4's sloped top | bare (membrane stops on the wall) | wraps over |
| part 4's interior face | — | skirts 225 mm |
| part 4's ends and bottom | bare | bare |

Measured separation 64.215 mm — the offsets differ by 65 mm, less the opposing slope
deviations. Checked on every build. It dropped to 20.4 mm while part 4's exterior face
was skinned by the membrane alone; giving the cladding the same face restored it.

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
rather than on a substrate feature. All four turns are therefore exactly 310 mm.

**The turn-out rule.** Where the membrane stops against part 4's exterior face, every
panel that ends there turns out 310 mm along the axis it faces, so the whole termination
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
  metal cap is normal — but it is an assumption, not a rule Duncan gave.
- **A flat-topped wall panel cannot name its own facade.** `uphill` raises on one, by
  design. In the student-house a flat top always has another panel stacked on it, so the
  top is occluded and only parapets are exposed — but the *panel* still needs its
  exterior/interior for cladding, and must inherit the direction from the parapet above
  it. That propagation is unbuilt; the error message says so.
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
  the z = −0.1 item below — every skin edge does this against an unskinned neighbour.
- **Cladding hangs to z = −0.1**, below the substrate's base, because the exterior wall
  faces mitre with the unskinned underside. Consistent with how every skin edge behaves,
  but Duncan may want it trimmed to z = 0. **Awaiting his call.**
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
