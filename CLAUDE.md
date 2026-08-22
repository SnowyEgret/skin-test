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
python3 -m pytest tests -q -k lap          # single test by name
```

Every tunable number is in `skin-parameters.yaml`, validated against
`skin-parameters.schema.json`. `build.py` reads it and prints which file it used. A what-if is a
full copy of the file passed as `build(params=parameters.load_validated(path))` — never an
override of individual knobs. See **Parameters** below.

Run pytest from the repo root — `tests/test_offset.py` imports `build` as a top-level module.

**Running the tests overwrites `build/`.** `tests/test_offset.py` calls `build(parts)` on the
synthetic rig, so a pytest run replaces whatever bake was last built — manifest included, which is
what `blender/display.py` reads. Build the bake you want *after* the tests, not before, or
`reload()` quietly shows you the rig. Caught once, after a reload displayed four `Substrate_N`
boxes instead of a 36-part bake.

`build.py` prints a per-skin line (residual, clearance, slope deviation, open/closed), what
`clean` removed from that skin, and the skin-to-skin separation. Every number but the clean line
is measured on the **raw** emission, before cleaning — see **Cleaning a mesh**. Those numbers are
the regression check: a residual above ~1e-9, or a clearance below `distance - slope_deviation`,
means something broke — **except where a skin deliberately stops short of something standing
proud of the wall.** `measure.clearance` samples vertices and centroids against every part and
cannot tell that from a fold. It is a weaker check still than that implies: its answer depends on
how the surface happens to be triangulated. It is not, however, a crier of wolf — the warning it
printed on the cornices bake for weeks was **right**, and named a real defect that four other
checks all missed because the surface was mis-tiled rather than self-intersecting. See NOTES.

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
   → skin_over()                        union → planar_offset → keep() → lap
   → clean()                            coplanar overlap dissolved, after the fact
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
  from the **covered** faces alone — the ones `keep` selected plus the faces a lap reaches,
  which is
  why `skin_over` evaluates its predicates *before* the solve and passes the mask down. If the
  contradiction survives among those, it raises naming the vertex and the two normals. Applies at
  contradictory vertices and nowhere else, so no model that solves today changes by a bit; a
  hash of the rig and both parapet exports pins that. The reconciled vertices are reported in
  `metadata["folds"]` and printed by `build.py`, because a constraint the solve deliberately
  dropped must not be silent. Consequence, accepted by Duncan 2026-08-16: a degenerate sliver
  **no skin covers** is now tolerated rather than refused.
- **A tiling the offset turned inside out is tiled again.** `planar_offset` moves vertices and
  keeps the union's triangulation, and manifold3d tiles a face with a hole cut in it by fanning
  across the hole. A hole corner that starts closer to one of those diagonals than `distance`
  crosses it when it moves, and its triangle comes out **inside out**, covering a sliver of the
  hole that the offset never placed. The outline and the holes are offset correctly and an
  inversion moves no boundary edge, so `_tiling` re-tiles the patch from its own loops.
  Detection is exact and wants no threshold — the body's own normal says which way each face is
  meant to face — and it applies to a patch that inverted and **nowhere else**, so nothing that
  tiles correctly changes by a bit. Measured: two faces on one substrate of the three.
  `_retiled` checks the tiled area against the area its loops enclose and raises if they
  disagree, the same check the ear clipper makes, because an outline that crossed itself would
  otherwise tile to well-formed triangles covering the wrong region.
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
  drop: m          # a lap that hangs below its arris; 0.0 switches that way off
  out: m           # a lap that rises or runs sideways; 0.0 switches that way off
  base: m | null   # trim: cut here and keep what is above; null for none
  close: m         # widest tear `clean` may gusset; 0.0 switches that off
  display: solid | wire
```

```python
# build.py RULES — the predicates, keyed by the same name
"...": {"keep": fn, "lap": fn}
```

`drop` and `out` are the two directions a lap can take, and a skin with both zero would stop dead
on every arris it reaches — `skins()` raises. Either alone is fine: the cladding has no upstand
and never did. `base` pairs with no rule — it is a datum rather than a face selection — and `null`
is **not** `0.0`: zero is a real height to cut at, where a zero `drop` or `out` is that direction
switched off. It is also not a seed, so `check_seeds` ignores it. Nor is `close`, which bounds a
cleanup rather than any surface — see **Cleaning a mesh**.
The rules take `(Faces, fall)`; `skins()` binds `fall` from the file, so what `skin/` receives
still has the `Faces -> bool[nfaces]` signature it expects. A built spec is *exactly*
`skin_over`'s argument list plus `name`, `display` and `close` — the last two are read by
`build()` and never reach the offset: one says how Blender shows the skin, the other how wide a
tear `skin/clean.py` may gusset.

`keep` and `lap` are predicates `Faces -> bool[nfaces]` over the union's faces. `Faces` (in
`skin/offset.py`) carries `body`, `parts`, `owner`, `normals`, `centres`, plus `roles` (WALL/ROOF
per part), `of_role(role)` and `touching(mask)`. Predicates get the whole thing because rules that
read the substrate need to ask what a face *adjoins*, not just where it sits. Compose `_upward`,
`wall_faces` and `_rules` rather than writing new plane tests. `keep` selects what the surface
**covers**; `lap` selects what it may **continue onto**.

## The lap: one rule, not a skirt and a flange

Duncan, 2026-08-20: *"When membrane meets an exterior vertical surface it never terminates at that
edge. It always flanges onto the vertical face. It can flange up, down, horizontally, or around a
corner."* He was right, and `_hem` / `_turn_out` / `turn_down` / `turn_out` are gone. Where a
covered face meets a face the skin does not cover, the skin turns and laps across the face
beyond, and everything else follows from geometry:

- **Direction** — `_across`: in the receiving face's plane, perpendicular to the arris, pointing
  into that face, read off the receiving triangle's own third vertex. A skirt goes down because
  the wall is below the coping's arris; an upstand goes up because the wall is above the roof's;
  a collar runs sideways because the face it turns onto lies to the side. A centroid will not do
  — a receiving plane very often has surface on *both* sides of an arris.
- **Level, and only level, is snapped.** A lap springing off a *sloped* arris — a cap plate laid
  to fall — comes out perpendicular to it and so tilted by the fall, and a 205 mm upstand means a
  height, measured vertically. So a lap that mostly rises or falls is made exactly vertical and
  one that mostly runs sideways exactly horizontal, the same priority the solver gives level
  planes. Nothing else is snapped: a wall at any plan angle laps along its own direction. This
  replaces `_turn_out`'s dominant-axis snap, which was needed only because it extruded along the
  *departing* panel's normal.
- **Distance** follows the direction. Down is a drip (`drop`); up or sideways is an upstand
  (`out`). There is nothing left to elect.
- **Datum** is the one thing that did **not** unify, and it is deliberate. A drip is measured on
  the **substrate**, from the arris itself mitered onto the offset planes of every skinned
  vertical face at that vertex; an upstand is measured from the **skin's own edge**. That is how a
  drip is set out from the edge of the coping it drips off and an upstand from the finished
  surface it rises out of, and it is why two distances are still authored. Tests pin both.
- **Which faces get one** — `_receivers`: `lap`-allowed, uncovered, and **adjacent to a covered
  face**. That adjacency is what bounds a lap to the faces it actually reaches, and it is what
  now stops the old plane-following bug structurally. A building shares a plane right up a stack —
  a parapet's outer face is the very plane its wall's is, a storey higher — and matching on the
  plane once turned the membrane's parapet skirt out into thin air 1.5 m above the roof. The lift
  above is simply not a candidate. `_meets_region` is retired with the mechanism that needed it.
- **A knife is refused.** Where a candidate is coplanar with and opposed to something the skin
  already claims, the shared vertex has no offset at all. A covered face outranks a lap; between
  two candidates the lap takes the **concave** arris and stops at the convex one, because an
  internal corner is where the surface must be continuous while at an external one the two offset
  surfaces have already parted by twice the distance. The scupper poses both — its drip is exactly
  as wide as its slot.
- **Chained and mitered within each receiving plane.** A run that changes direction along one face
  closes at the turn; the miter is the intersection of the two outer lines. Across planes there is
  nothing to miter — two outer lines on different faces do not meet, and asking anyway gets a
  least-squares answer from out in space, which threw a 400 mm triangle across the scupper's
  mouth. Two drips at a wall corner need no miter: `drip_at` already solves their shared arris on
  both planes at once.

**A lap is cut to the face it lands on** — `_room` marches along the lap direction over the
coplanar triangles and shortens it, or drops it where there is no room. Marching rather than
testing the far end, because a union triangulates a wall and a lap commonly crosses several of its
triangles: a 62 mm drip off a 34 mm cap plate must still run its full depth down the parapet's
coplanar face below. Without it, covering the scupper cheeks sent a 205 mm upstand onto a 34 mm
reveal, 120 mm above the wall and through the cladding's coping.

Each step of that march reads **every** coplanar triangle holding the probe, not the first one
found. A lap starts on an arris, so the probe sits on a shared edge or a shared corner every
single time, and a triangle that merely *corners* on it exits at once and reports no room at all.
Reading the first in index order made the answer depend on how manifold3d happened to triangulate
the face, which is mirrored by nothing: the scupper's two sides are one detail mirrored, and the
march ran the full 205 mm off the cornice's north end and stopped dead at its south end. Do not
put the `next(...)` back.

**A continuation runs only where the whole of it lands on substrate**, and never onto a knife — `_knifed`
is shared by the seam receivers and by the faces a continuation may fold onto, because being a
knife is a property of the face and not of how the lap arrived at it. Filtering only the receivers
put two 205 mm panels across the mouth of the scupper, on the roof taper's end face.

**A lap does not stop where the face it laps onto stops.** At the free end of a run it asks what
the substrate presents there, and there are three answers: *the same plane carries on* (an in-line
butt — the lap runs on), *another face meets it at an arris* (the lap folds round the corner, its
direction the departing face's normal signed by whether that arris is convex or concave), or
*nothing* (it ends — Duncan's stop condition).

**A run-on runs `out`.** It runs sideways, along the surface, so it is an upstand and never a
drip — `drop` is for a lap that hangs *below its arris*, which a run-on never does. It used to be
priced by `reach`, which answers "which way does this lap leave its arris" and is the wrong
question about the direction of a *run*: a seam raking down a coping laid to fall then read as a
drip at one end and an upstand at the other, purely because the two ends face opposite ways along
the same fall, and one straight arris ran on 62 mm one way and 205 mm the other. A skin whose
`out` is zero has nowhere to run on.

**The fold's probe starts on the arris.** The seam it springs from lies on the offset of the face
the lap is *leaving* as well as of the face it is turning onto, so it sits `distance` off the
arris along the fold direction — past it at a concave corner, which is harmless, and short of it
at a convex one, where the march starts out over the void beyond the corner and reports no room at
all. Until that was fixed no fold was ever placed at a convex corner, which is why the Unit8
coping's upstand stopped dead at the building corner instead of wrapping onto `Headhouse-N`.

Two guards on all of it, both learned the hard way:

- A run is only free at its end if **nothing else turns the same way there**. Two drips meeting at
  a building corner are one band turning through 90°, and treating either as free folded it onto
  the other and left a hole where the drip had been. An upstand meeting a drip at the same vertex
  is different — they turn opposite ways and the corner between them is genuinely open, which is
  the whole of the north junction.
- A continuation runs **only where the whole of it lands on substrate**. There is no cutting here,
  only whole quads, so a lap that would overhang is not placed at all. The scupper is why: the
  parapet's inner face meets the cheek 8.6 mm above the sill, and a 62 mm drip run on down from
  there goes straight into the parapet.

`_trim_below` (`base`) runs **after** the laps, so it means "no part of this skin goes below the
datum" rather than "the offset stops there". It is a **cut**, not a clamp: triangles straddling
the plane are re-cut against it and everything above keeps the plane the solve gave it. Pushing
the low vertices up instead would look identical in outline while tilting the bottom of every
sloped panel off its offset plane — and the residual is computed before the trim, so nothing
would report it. Crossings are cached per edge so the two triangles sharing one get the same
vertex and the cut does not crack.

**A cornice joins the wall it projects from.** `build.group_cornices` runs before
`group_caps` — which classifies every element up front and would raise on a lone cornice first.
It cannot ask a part's role and does not need to: **a body is a cornice of one it touches when it
sits within that body's height, is strictly shorter than it, lies wholly outside its plan
footprint, and projects less far than that body is thick.** The last two conditions do the work.
`Cornice-Unit8-E` reads `ROOF` at horizontality 0.704 and the 400 mm scupper drip reads 0.533 —
dead on the halfway mark, where `classify` refuses and the build stops. A cap plate is held off by
resting *on* the top rather than standing proud of the face; a neighbouring parapet butting a
taller wall is inside its height, shorter than it and outside its footprint, and is held off only
by the thickness test — it stands metres proud of a 420 mm wall. Nothing is authored: the wall's
own thickness is the measure, the same move `_next_lift` makes.

The membrane needs nothing further — a cornice joined to a climbed parapet has its exposed top
picked up by "every upward face of a climbed wall", and the lap then hangs a drip down the face
below it, which is the scupper drip exactly. At `Cornice-Unit8-E` neither happens, because its top
is buried under the cap plate and its face is coplanar with the cap's. **The cladding stops below a cornice** rather than wrapping
it (Duncan, 2026-08-19) — `cladding_faces` excludes `tagged(CORNICE, True)`, and since the facade
face below already ends at the cornice, that exclusion is the whole of it. The coping above is a
separate face and is still claimed by both skins.

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

## Cleaning a mesh

`skin/clean.py` is `clean(mesh) -> mesh`, and that is its whole interface. The lap rule
legitimately emits **whole quads**, so where one band lies inside another on the same plane the
two overlap: the summed triangle area is not the area covered — 0.180% of the membrane on the
live bake — and the four bowtie quads left in it are what that looks like from outside. A miter
between two overlapping bands cannot un-overlap them, and two source-level attempts are measured
and rejected in NOTES, so it is resolved afterwards, plane by plane, with a 2D boolean. (The
cladding's two bowties had a different cause — a tiling the offset inverted — and are fixed at
source by `_tiling`, above. Its summed area is now exactly its covered area.)

**Nothing in `skin/offset.py` or `RULES` knows it exists**, and it is named for a mesh rather than
for a skin because overlapping itself in a plane is a property of a mesh, not of a skin. It is
testable on a hand-made overlapping pair with no substrate at all, which is most of
`tests/test_clean.py`.

**It is not part of `skin_over`, deliberately.** The union inserts a vertex wherever two bands'
boundaries cross, so a cleaned mesh no longer satisfies *"every vertex that survived is exactly
where the offset put it"* — the `base` trim test's assertion, and the property that makes
`_trim_below` a cut rather than a clamp. `build()` therefore **measures the raw emission and
writes the cleaned mesh**: residual, clearance, folds and the separation are properties of the
offset and stay on what `skin_over` produced, and a printed line says what the clean removed.
That split is not fussiness. `clearance` samples face centroids, so re-triangulating moves the
samples: cleaning alone took the cornices cladding from 63.9999 mm to 84.1503 mm without moving
any surface, purely because the centroid that found the low reading no longer existed. A verdict
that changes with the triangulation is not a verdict about the geometry — and the low reading was
real, see the `_tiling` invariant above.

- **shapely (GEOS) unions, `manifold3d.triangulate` re-triangulates.** Nothing to install here —
  shapely arrives with `trimesh[easy]`, and it joins yaml and jsonschema on the undeclared-
  dependency list. Both engines were measured against the alternatives. shapely is bit-exact on every point its union preserves
  and it **keeps collinear vertices**, which `skin/export.py` keeps on purpose so a neighbouring
  facet cornering there leaves no T-junction; `manifold3d.CrossSection` moves preserved points
  ~4.7 nm and drops those vertices. `skin/clean.py` is the **only** module that imports shapely
  and it is deliberately not re-exported from `skin/__init__.py`, so `import skin` does not
  require it — the same containment `skin/parameters.py` gives yaml and jsonschema.
- **Planes are grouped either way up** — `min(|rep - row|, |rep + row|)`, and matched against the
  representatives already found rather than by equality of a rounded key, for the reason
  `_plane_ids` is. A bowtie's two halves face opposite ways, so a group keyed on `(n, d)` alone
  puts them in different groups and misses the very overlap the pass exists for.
- **Each way up is unioned separately, and overlap — not adjacency — decides what is one sheet.**
  Two coplanar sheets facing opposite ways are an ordinary condition: a knife, where a roof butts
  a wall on the wall's own plane and both sides of the contact are exposed, or simply two solids
  meeting along an edge. A bowtie's two halves, by contrast, *overlap*, and their opposed winding
  is an artefact of the self-crossing quad rather than two surfaces. So `_sheets` connects faces
  that intersect with positive **area**, gives each component the direction of the greater area in
  it, and the two directions are then unioned apart. Getting this wrong is silent and severe, and
  both wrong answers were measured: a plane-wide vote costs the substrate union its volume
  (84.294 → 104.688 m³), and a vote taken *after* the union — per region — costs two cubes meeting
  along an edge theirs (2.0 → 4.0), because `unary_union` has by then dissolved the boundary
  between the two sheets and no later vote can recover it. **Separate the ways up before the
  union, never orient after it.** Four tests pin it.
- **Every ring is oriented before triangulating** (`orient(poly, 1.0)`, exteriors CCW, holes CW,
  `allow_convex=False`). Fed shapely's raw rings, `manifold3d.triangulate` silently returns
  overlapping triangles and *more* area than it was given.
- **A whole plane is triangulated in one call** — both ways up together — so two sheets meeting
  along a line share the vertices they meet at. Re-triangulating region by region and welding
  afterwards left two non-manifold edges in the membrane. A triangle never spans the two ways up:
  they are disjoint in area, so each triangle lies inside exactly one of them.
- **The weld radius is `WELD_TOL = 1e-9`, not `PLANE_TOL`.** The only points needing a weld at all
  are the ones the union *computed*, where two planes reached one crossing through different 2D
  bases and differ in the last bits (~1e-14 m); a point the union preserved comes back
  bit-identical. At `PLANE_TOL` the radius reaches the **1 µm lattice every substrate coordinate
  is snapped to** — two neighbouring lattice points are 9.9999999925e-07 apart — so a 1 µm strip
  welds away silently and is reported as overlap that never existed.
- **Metadata keyed on an index does not survive**, because the indexing does not: `folds` is a
  list of vertex indices and `plane_ids` one id per face. Both are dropped rather than remapped,
  so a reader gets nothing instead of the wrong vertex. `build.py` prints folds off the raw skin.

`clean(mesh, dissolve=True)` runs a **second, opted-in operation** on top: it drops every vertex
that lies straight between its neighbours on every ring holding it **and that no ring turns at**.
That last clause is the whole of it, and it is asked once over the entire mesh rather than per
plane — `skin/export.py` keeps collinear vertices precisely because dropping one that a
neighbouring facet corners on leaves a T-junction, and a vertex can be straight through on one
facet and a corner on the one beside it. It is a tidy-up, so it is allowed the authored
`STRAIGHT_TOL` (1e-9 m off the line) where a derivation would not be; it changes no outline, and
the measurements say so — area equals the covered area to 0.000000 mm² on all three substrates,
with no vertex more than 2.5 nm off a plane the offset produced. `build()` opts in: on the live
bake the membrane goes 153 → 115 triangles and 67 → 35 border edges, the cladding 134 → 81 and
54 → 45, and T-junctions fall (membrane 3 → 0) because a vertex no ring turns at **is** the
T-junction anchor. Pass `dissolve=False` — the default — to keep every vertex.

What it does **not** do: it says nothing about two *different* planes intersecting. Closing a hole
is a wholly separate mechanism, because nothing about a hole falls out of a coplanar union — the
scupper outlet is coplanar with nothing — and it is the third operation below.

`clean(mesh, close=m)` closes a **tear**: a hole the offset could not span, gusseted shut. Off at
zero, authored per skin as `close` in the parameter file, and built 2026-08-22 on Duncan's
decision. Where the substrate has no thickness — a roof knifing into a wall on the wall's own
plane — the two offset surfaces part by twice the distance and the skin opens along the contact,
which is `_reconcile` declining to move one vertex two ways at once. A **gusset** is the one face
in a written skin that is not the offset of anything; `build.py` prints how many and how much,
for the same reason it prints folds. It bridges vertices the offset already placed, so it invents
no point — only the surface between them is new.

Three conditions, and they do different jobs:

- **flat**, to `PLANE_TOL`. A loop that does not lie in a plane offers a *choice* of filling
  surfaces, and choosing is not a cleanup's business. Not a close call: the membrane's tear is
  flat to 1.5e-15 m, and every legitimate free edge in either skin on all three substrates stands
  at least 94 mm off its own best-fit plane, because a skin's perimeter wraps a building.
- **narrow**, to the authored `close`. Deliberately **not** derived as twice the offset: the tear
  is 16 mm across in plan but 18.016 mm along its own plane, because the roof it opens on falls,
  so `2 x distance` would miss the very tear it was reasoned from. Authored at 0.025 against a
  248.268 mm narrowest-free-edge-that-must-stay-open.
- **not already covered**, which is derived and does the load-bearing safety work. The worst case
  is otherwise silent and severe: the perimeter of *any* flat sheet narrower than `close` is a
  flat narrow loop, so a 20 mm cover flashing would have its own outline "closed" and come back
  doubled — two coincident surfaces, reported as a tidy-up. A tear is by construction where the
  surface is **missing**. This is what lets the authored bound stay a bound on size rather than a
  guess about what a loop means.

The border is read as **half-edges**, in their own faces' directions, and split into connected
pieces rather than walked. Both matter. A gusset shares every border edge with the face already
on it, so it must traverse that edge the other way — which orients it off the mesh instead of off
a guess about a normal. And the membrane's tear **pinches to a point**: two triangles meeting at
one vertex of degree four, which no ring walk can turn at without guessing. `shapely.polygonize`
reads the piece as the planar graph it is and returns both regions, which is why one tear reports
as two.

The three run in the order union → dissolve → close, each reading the outline the one before left:
a gusset is fitted to the border of the *finished* surface, and a border edge a bowtie left is an
artefact rather than a tear.

`clearance` is untouched by any of this, and that is the point of where the gusset lives. A gusset
is a chord across a fold, so it does read 7.8808 → 5.8793 mm **on the written mesh** — but
`build()` measures the raw emission and writes the cleaned one, so the verdict stays a property of
the offset. Putting the gusset inside `skin_over` instead, as was costed on 2026-08-21, is what
would have made `build.py`'s verdict change with it.

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
  face and the membrane climbs the whole of it and carries over the top; into the exterior face
  and it stops, and the lap turns it up there. Tested per **wall**, not per face: only one
  triangle of a step wall touches the roof, but the membrane climbs the whole face, so touching
  faces elect the wall and the wall carries all of its own faces. Only the *climb* is elected now
  — the upstand where the membrane stops is not, because the lap reads that off the substrate. So
  `_rules` returns `climbed` and no longer computes `flanged`, which existed only to hand those
  faces a turn-out and to keep them from also getting a skirt.
- **an opening cut through a wall.** `build._opening` reads a slot's **cheeks** — two vertical
  faces of one *body* looking **at** each other, where a wall's thickness and a wall's two ends
  look away — and its **floor**, an upward face with a cheek pair standing *over* it. Per body,
  not per element: a slot cuts through the cap plates too, so per element their two reveals look
  at each other and the coping reads as a cheek pair. And *standing over*, not merely touching:
  the same cheeks meet the wall's own coping where the slot cuts through it, but stop at that
  level. The cladding subtracts the floor — a rainscreen stops at a 400 mm outlet rather than
  lining it, and "every wall top" otherwise claimed the scupper sill and flared the coping's mitre
  out through the mouth. The membrane still lines it, as an upward face of a climbed wall.
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
metre-scale coordinates. That is half a `PLANE_TOL` lattice cell, so **plane identity must never be
exact equality of a rounded key** — two faces of one plane land either side of a boundary often
enough to matter, and the headhouse taper's top already does in the shipping bake. `_plane_ids`
matches each face against the representatives already found instead, and `_lap`, `_knives` and the
run chaining all key on its id. A run that silently fails to chain is a lap that silently does not
happen. That is the accuracy floor for everything downstream: `TOL = 1e-6`
(`build.py`) and `PLANE_TOL = 1e-6` (`skin/offset.py`) exist for it. Do not tighten them — an
earlier 1 nm threshold produced a bogus self-intersection warning. `RIDGE = 1e-9` keeps the KKT
system non-singular where the soft equations leave a vertex free; it is not a tolerance to tune.
