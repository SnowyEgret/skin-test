# skin-test — state of play

Offsetting a **substrate** (an assembly of solid parts) outward by a fixed distance to
produce **skins**: open surfaces that cover a chosen subset of faces.

Last worked: 2026-08-25.

`CLAUDE.md` has the commands, the architecture and its invariants, and the tolerance
rationale. This file is the running log: what the geometry currently is, what was tried
and rejected, and what is still open.

## Start here (picking up after 2026-08-25)

### Where to pick up

**Step 1 of the four is done: `_trim_beside` is backed out.** See *"What landed on 2026-08-25"*
below. The cheek selection in `cladding_faces` stayed, so the cladding still covers the cheeks
and the bake now reads the honest number for the real fault — `clearance 3.6593 mm`, with the
warning back.

**First job: cause 1, the lining stopping at the parapet.** Contained, and the derivation to try
is written down. Then cause 2 (the knife), then the turn-down last. All of it is in *"The cheek
lining is wrong, and what it is"* below, and **start from *"Order to take them in"*** at the end
of that section — steps 2, 3 and 4 stand exactly as written.

**One thing is wanted from Duncan before much else, and it is now overdue rather than
optional:** the `clearance` verdict. Every bake with a cornice warns again, and it will keep
warning even once the lining is *correct*, because the geometry Duncan asked for reads 79.97 mm
against an 85 mm offset inherently — the reveal's mouth sits on the headhouse roof. So the
question is no longer "should we demote `clearance`" but "what should the build assert instead",
with the Möller-Trumbore pass the candidate. Named in step 1, unanswered.

**Second job: `/code-review high` over the whole branch diff.** It is owed and has not run. The
fourth-pass review below covered `skin/clean.py` *as it stood before its `_sheets` rewrite*;
everything since is **unreviewed** — `_sheets`, the `dissolve` operation, `clean`'s third
operation `close`, and all of `offset._tiling` / `_rings` / `_retiled`. A second run was launched
and died on an API session limit before producing a finding. Given that the fourth pass found four
real defects in code of exactly this kind, do not treat the unreviewed half as settled.

### What landed on 2026-08-25

**`offset._trim_beside` is backed out**, as a revert of `f0d535b` — step 1 of *"Order to take
them in"*, and exactly the disposal that commit asked for in its own message.

What was kept back from the revert, deliberately, because `f0d535b` carried two unrelated things
and only one of them was wrong:

- **the cheek selection** — `| (cheeks & faces.of_role(substrate.WALL))` in `cladding_faces`,
  with its comment rewritten to say what happened to the repair. Duncan's *"Cheeks are clad"*
  stands and the selection was never the defect.
- **its paragraph in CLAUDE.md**, under *"an opening cut through a wall"*. The whole of
  *"The trim in plan"* is gone with the mechanism.

`NOTES.md` was taken at `HEAD` rather than reverted: `e09c91a` rewrote that section afterwards,
so the revert conflicted there, and the diagnosis that condemned the trim is precisely what the
log should keep.

**Measured on the live bake, and it is the pre-trim reading character for character** — which is
the check that the revert did what it claimed: cladding `clearance 84.1503 → 3.6593 mm`,
separation `76.230 → 4.337 mm`, `WARNING: 81.341 mm inside the requested offset` back. The
membrane is untouched: `clearance 7.8808 mm`, 4 folds, 153 → 117 triangles. The cladding emits
128 triangles where the trim made it 134.

**`tests/test_import.py::test_the_baked_headhouse_reads_and_skins` now pins the defect instead of
the property**, and that is a deliberate weakening with a tripwire on it. The general
`gap > distance - slope_deviation` assertion is kept for the membrane and replaced for the
cladding by the two known-bad numbers, `clearance 0.0036594` and `separation 0.0043372`, under a
comment naming v66 and v67 as the cause. They are **expected to fail** when the knife is fixed —
that is the point of pinning them — and the comment says to restore the general form there and
then. 110 tests pass; the trim's own 125 lines of `tests/test_offset.py` went with it.

**`/code-review high` ran over the diff and found four things, all four verified and all four
acted on.** Two were the revert taking a test with it that had outlived its subject or its
generality, and they are the more interesting half:

- `test_a_free_miter_still_reaches_past_the_face_it_covers` was deleted with `_trim_beside`,
  its docstring reading *"the invariant the trim must not reverse"*. But what it pins is the
  **"solved over the whole body, then faces are selected"** invariant, which is CLAUDE.md's and
  predates the trim by months. Restored as `test_a_free_miter_reaches_past_the_face_it_covers`
  with `_neighbours` / `_top_of`, passing unchanged with the mechanism gone. The lesson worth
  keeping: a test written *as a guard on* a mechanism is not necessarily a test *of* it.
- `test_the_baked_headhouse_reads_and_skins` had a per-skin clearance check **inside the loop**
  over `skins(params)`, so every skin was checked by arriving. Replacing it with two by-name
  assertions would have left a third skin — the documented way to extend this — silently
  unchecked. The loop check is back with an explicit `if spec["name"] != "Cladding"` exemption,
  which says what is exempt and why instead of quietly covering nothing.

The other two: the membrane bound was hardcoded `0.008` rather than read from `spec["distance"]`,
duplicating a parameter-file number in the one file that derives everything else; and CLAUDE.md's
*"cleaning took the cornices cladding 63.9999 → 84.1503 mm"* no longer reproduces — it is now
3.6593 raw and 3.6593 cleaned, because `_tiling` fixed the inversion at source and the low-reading
centroid is on the cheek panel. Dated, with the membrane's 7.8808 → 5.8793 given as the live
demonstration of the same point.

**Not done, and not started:** causes 1, 2 and the turn-down. The tree is clean apart from an
untracked `audit.py`.

### What landed on 2026-08-22

**The cladding covers the scupper cheeks.** Duncan, weighing the cheeks against the floor's own
*"a rainscreen stops at the opening"* reasoning, chose to clad them. The one line in
`cladding_faces` is right and stays.

**The trim in plan — `offset._trim_beside`.** Built to unblock that, and **it does not produce
the geometry Duncan wants** — he read the result back the same day. It is in the tree, tested and
documented, but its central case is now in question. See *"The trim in plan, and the reveal it was
blocked on"* for what it is and what it measured, and then *"The cheek lining is wrong, and what
it is"* for why that is not enough. Do not treat it as settled work.

**The gusset — `clean(mesh, close=m)`.** Duncan, asked the standing question, answered *"Yes,
close it in `clean`."* The membrane's one hole, the scupper outlet, is now gusseted shut: 6 border
edges and 3459.06 mm² of it, on all three bakes. Built as the third opted-in operation of
`skin/clean.py`, exactly where the 2026-08-21 costing said it should go if it were ever wanted,
and **not** in the rules. See *"The gusset as built"*.

The second half of that question — *should `clearance` stop being the build's verdict first?* —
turned out **not to be a precondition at all**, and that is the useful finding. It stays open on
its own merits and blocks nothing. See the same section.

### What landed on 2026-08-21

Three things, all on top of `07c3e4d`, all in one commit:

1. **`skin/clean.py`** — the coplanar-overlap pass, built to the spec that stood here and
   measured against it in *"The pass as built"*. `clean(mesh) -> mesh`, its own module, the only
   one that imports shapely and deliberately not re-exported from `skin/__init__.py`. `build()`
   **measures the raw emission and writes the cleaned mesh** — Duncan's choice of the three
   offered — so no regression baseline moves and `build/` gets the tidy geometry.
2. **`clean(mesh, dissolve=True)`** — a second, opted-in operation that drops every vertex no ring
   turns at. `build()` opts in. See *"Collinear vertices, and the second operation"*.
3. **`offset._tiling`** — the fix for the defect Duncan read off the cleaned bake: a hole corner
   crossing a tiling diagonal, which had been eating the cladding's notch at the scupper cornice
   since the cornices bake first built. See *"The notch is fixed at source"*, which also carries
   the correction that the cladding's long-standing clearance warning was **never a false alarm**.

### What is open

- **The membrane's four bowties.** A lap miter running out past the rim of a band that lies wholly
  inside its neighbour — a different mechanism from the one `_tiling` fixed, and still only
  dissolved after the fact by `clean`. The cladding has none left.
- **`clearance` depends on the triangulation**, which is the part of that open item that survives
  the 2026-08-21 correction. Read the correction before acting on the item. It is **not** coupled
  to the gusset — see *"The gusset as built"*.
- **The south-junction sliver**, 205 x 7.3 mm, unchanged.

### State of the tree

Everything above is **committed** on `skin-the-walls-and-caps-bake`, working tree clean, nothing
pushed. 114 tests green in ~7.7 s (with `-W error::DeprecationWarning`), all three substrates
build, and the live bake was built last so `build/` and `display.reload()` show it.

2026-08-22 landed as **three commits, split on purpose** rather than one, because one of them is
expected to come out:

1. `471d0e4` — the gusset, `clean(mesh, close=m)`. Decided, measured, and independent of
   everything else that day.
2. `f0c4e13` — `_cut`, the one half-space cutting primitive, with `_trim_below` expressed through
   it. A pure refactor: the live bake's `Membrane.obj` and `Cladding.obj` are byte-identical
   across it, build log included. It stands on its own whatever happens to the trim.
3. `HEAD` — the cladding over the scupper cheeks and `offset._trim_beside`. **This is the one
   under question**, and it is alone in its commit so that backing the trim out is a revert rather
   than surgery. The cheek selection in `cladding_faces` is right and would have to be kept.

What
`skin_over` **emits** is unchanged from `07c3e4d` everywhere but the cornices bakes' cladding:
`_tiling` took it 134 → 122 triangles on 2026-08-21, and the cheek lining takes it back to 134
today. The rig and walls-and-caps skins are triangle for triangle what they were, which is the
property `_tiling` was written to keep, and no other skin on any substrate moves for the cheeks —
the live bake's membrane line is character for character what it was. What `build/` **writes**
differs everywhere, because it is now cleaned and thinned.

### The substrate

The live substrate is **`unit8-parapets-caps-clt-insulation-headhouse-extended-cornices.obj`** —
the cornices bake with the scupper's drip run **100 mm past each jamb** (`Cornice-Headhouse-E`
now `y 4.685…5.285` against the slot's `4.785…5.185`). Everything else is byte-identical to
`unit8-parapets-caps-clt-insulation-headhouse-cornices.obj`, which it supersedes; 29 `o` groups,
36 parts, 18 elements. It replaced `unit8-parapets-caps-clt-insulation-headhouse.obj`,
which Duncan overwrote on disk and which was never committed; the walls-and-caps bake
`headhouse-walls-parapets-caps-clt-insulation.obj` survives because `tests/test_import.py` reads
it.

```bash
python3 build.py unit8-parapets-caps-clt-insulation-headhouse-extended-cornices.obj
```

...and **build it after running pytest, not before** — the tests rebuild `build/` with the
synthetic rig, manifest included, and `display.reload()` then shows you the rig. See CLAUDE.md.

Work sits on branch `skin-the-walls-and-caps-bake` — the name is now older than what is on it.
Everything below is committed. Nine pieces of work, each with its own section; **read 4 to 7
before touching `_lap`, and 9 before touching the solve.**

1. **The Unit8 bake** (2026-08-19) — the storey below added, the first substrate to elect a
   `flanged` wall. It found a defect: the turn-out matched an unbounded *plane* rather than the
   elected faces, and dressed the membrane's parapet skirt into thin air 1.5 m above the roof.
   Fixed by `_meets_region` — since superseded, see 4.
2. **The cornices bake** (2026-08-19) — two cornices, neither of which would classify.
   `group_cornices` joins a cornice to the wall it projects from.
3. **`substrate.role_of`** (2026-08-19) — the classify-an-element call both callers duplicated,
   which now re-raises naming the element.
4. **The lap** (2026-08-20) — Duncan's observation that the skirt and the flange are one rule.
   `_hem`, `_turn_out`, `_meets_region`, `membrane_skirts`, `membrane_flanges`, `cladding_skirts`,
   the `turn_down`/`turn_out` spec fields and `_rules`' `flanged` are gone, replaced by `_lap` and
   a per-skin `lap` predicate. It closed the V11 leak. It did **not** make the code smaller —
   there is a measured table saying so.
5. **The scupper finished** (2026-08-21) — `_opening` (a slot's cheeks and its floor, derived),
   the membrane covering the cheeks, the cladding no longer lining the outlet, `_room` cutting a
   lap to the face it lands on, and Duncan's **extended cornice**, which removed the knife at the
   mouth and bought the mouth flange and the cornice-end drips for no code at all.
6. **The scupper made symmetrical** (2026-08-21) — five defects Duncan read off the
   live bake, three causes, all in `_lap`'s neighbourhood: `_room` reading only the first coplanar
   triangle that held its probe, the fold's probe starting `distance` short of a **convex** arris,
   and a run-on priced by `reach` of the direction it runs in rather than by `out`. Four new
   tests, all four red at `c098d15`.
7. **The mesh audit** (2026-08-21 — NOTES only, no code) — the outlet hole diagnosed
   and bounded, the coplanar overlap measured, the engines compared, two source-level fixes tried
   and reverted, and the decision to build the pass and leave the gusset. Everything the next job
   needs is in it.
8. **`skin/clean.py`** (2026-08-21) — the coplanar-overlap pass built to that spec,
   wired into `build()` as write-cleaned/measure-raw, `dissolve` as a second opted-in
   operation, and 20 tests. Reading it back, Duncan found the cladding's notch at the scupper
   cornice eaten by an inverted triangle — pre-existing, and hidden until the double cover stopped
   being drawn twice. `offset._tiling` fixes that at source, and takes the cladding's coplanar
   overlap to zero and its long-standing clearance warning with it.
9. **`offset._tiling`** (2026-08-21) — a patch the offset turned inside out is tiled again from
   its own boundary loops. It fixed the cladding's notch at the scupper cornice, took that skin's
   coplanar overlap to zero, and retired the "known false alarm" this file carried for weeks: the
   warning was right. See *"The notch is fixed at source"*. **Unreviewed.** Orientation at a knife took
   two goes to get right and `/code-review high` caught the second one; it also turned `clearance`
   into a weaker verdict than the open item already said. See *"The pass as built"*.

### Where it stands, measured

Re-measured 2026-08-25, after the `_trim_beside` revert. The **rig has no scupper** and is
therefore the row that did not move; the two bakes carry the cheek lining and read its defect.

| | separation | membrane / cladding clearance | crossings | buried |
|---|---|---|---|---|
| rig | 76.071 | 7.7760 / 84.6091 | 0 / 0 | none |
| walls-and-caps | 4.337 | 7.8808 / **3.6594** | not re-measured | none |
| extended cornices (live) | 4.337 | 7.8808 / **3.6593** | not re-measured | none |

| | coplanar overlap removed, membrane / cladding | triangles | border edges |
|---|---|---|---|
| rig | 53554 / 0 mm² | 33→34 / 29→22 | 25→16 / 23→18 |
| walls-and-caps | 69945 / 0 mm² | 76→52 / 84→48 | 24→8 / 36→32 |
| extended cornices (live) | 226868 / 0 mm² | 153→117 / 128→88 | 67→29 / 60→52 |

The bold clearances are the **defect**, not a regression from the revert: they are what the
cheek lining has read since it was clad, with `_trim_beside` hiding it in between. Causes 2 and 3
in *"The cheek lining is wrong, and what it is"*. **`crossings` is honestly blank** — it was
measured by a throwaway Möller-Trumbore script that is not in the repo (the standing item is to
promote it into `skin/measure.py` as `intersects(a, b)`), and it has not been re-run since the
cladding moved. Do not read the old `0 / 0` forward: with the two skins now 4.337 mm apart
instead of 76, it is the number most likely to have changed, and it is the one that would say
whether the lining actually touches the membrane.

The first table is measured on the raw emission and is **unchanged** by `clean` — that is the
point of measuring before the pass and writing after it — the second table moved on 2026-08-21
when `_tiling` stopped the cladding covering surface it never meant to. 100 tests, ~5.3 s.
No bake prints a self-intersection warning any more. The cladding's
`WARNING: 21.000 mm inside the requested offset` on the cornice bakes, carried here for weeks as a
**known false alarm**, was nothing of the kind: it was the inverted triangle, and it went when the
tiling was fixed. See *"The notch is fixed at source"*.

### After the pass, in the order they became live

- ~~**The gusset, if Duncan wants the outlet closed.**~~ **Built 2026-08-22**, in
  `skin/clean.py` as the third opted-in operation with an authored bound, exactly where this line
  said it should go — and **not** in the rules. See *"The gusset as built"*.
- **The cladding covers the scupper cheeks, and the lining is wrong.** The `cladding_faces` line
  is right and stays; the geometry it produces is not. Four corrections from Duncan, three causes,
  all diagnosed with coordinates in *"The cheek lining is wrong, and what it is"*. This is the
  next job.
- **`offset._trim_beside` is probably for the bin.** Built 2026-08-22 to unblock the cheeks; its
  only live case is one it gets wrong, because the defect was two mis-offset vertices at the knife
  and not the length of the miter. It costs nothing anywhere else, which is why it is left in
  rather than reverted, but assume it comes out. Same section.
- **`cladding_laps` is still the old election** — `interior`, nothing else — held back while the
  membrane was settled. Widening it to `np.abs(faces.normals[:, 2]) < TOL` is the whole change;
  expect it to need its own conversation about what the cladding does at a cornice.
- ~~**The offset inverts a triangle where a hole corner is closer to a tiling diagonal than the
  offset distance**~~ — **fixed 2026-08-21** by `_tiling`, see *"The notch is fixed at source"*.
  It was the cause of both of the cladding's bowties; the miter mechanism below is the membrane's,
  and is still open.
- **The lap cannot clip, and there is now more of it to clip.** The south-junction sliver
  (205 x 7.3 mm) is unchanged, but the collars restored at the two parapet ends roughly double the
  coplanar overlap around the scupper — symmetrically, which is the fix. The pass resolves the
  *symptom*; the lap emitting whole quads is still the cause.
- **The superseded cornices bake is now wrong to build** — with the cheeks covered it puts a
  membrane vertex inside `Cornice-Headhouse-E`, the mouth knife the extension removed. Nothing
  reads it; deleting it is Duncan's call.

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
| `skin/offset.py` | the solver. `planar_offset` (one constrained system), `skin_over` (union → offset → select faces → lap → trim), `_lap` / `_across` / `_receivers` (the one continuation rule), `Faces` (what a predicate may ask) |
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
Both files were deleted on 2026-08-19 and are recoverable from commit `5d77c9a`; the figures
below were measured on them and have not been re-checked since.

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
and both parapet exports skinned to identical vertex hashes — checked against the three older
exports before they were deleted later the same day. `headhouse-walls-parapets-insulation.obj`
still raised `AmbiguousPart` on a 0.42 × 0.42 × 1.675 block, unchanged and pre-existing.

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

## The Unit8 bake (2026-08-19)

`unit8-parapets-caps-clt-insulation-headhouse.obj`: the walls-and-caps bake with **the whole
storey below added** — Unit8's CLT deck, flat insulation and taper, its four parapets and their
four cap plates. 27 `o` groups, 34 parts (the tapers are multi-body), 18 elements. The headhouse
geometry is byte-identical to the previous bake; everything new is underneath it.

The Unit8 roof is **L-shaped, notched around the headhouse**, so the headhouse now stands in a
roof rather than on nothing. That is what the file is for, and it is the first substrate here
where any wall is elected `flanged` — so the first that exercises `_turn_out` on a real model at
all. The old bake elected none, and `_turn_out` returned `[]` before reaching any of its logic.

Everything derived came out right first time, which is worth recording because none of it was
touched:

- **The climb/flange election reads the notch.** `Headhouse-E` and `Headhouse-S` — the two walls
  facing the Unit8 roof — are `flanged`; `Headhouse-N` and `Headhouse-W`, on the building's outer
  perimeter, are neither. All **eight** parapets, Unit8's four and the headhouse's four, are
  `climbed`. Nothing lists a wall or a direction anywhere.
- `rise` resolved every one of the new flat-topped Unit8 parapets through its cap plate, and
  `group_caps` joined all four Unit8 cap plates to their parapets, exactly as it does upstairs.
- The three folds are still the `x = 8.5` contact, now four — the fourth is the same knife corner
  on the Unit8 side. `_reconcile` handles all four.

### The turn-out followed the plane instead of the faces

The build "succeeded" and the printed numbers caught it: **skin separation 8.000 mm**, against
77.000 mm on the previous bake. A Möller-Trumbore pass found **35 genuine crossings** between the
membrane and the cladding. Neither skin self-intersected, and the residuals were clean — the
hard constraints were all satisfied, so nothing in the solve had any reason to complain.

`_turn_out`'s `stops_on_wall` tested only whether a skin boundary edge lay **on the offset plane**
of an elected face. A plane is unbounded, and a building shares one right up a stack:
`Parapet-Headhouse-E`'s outer face is the very plane `Headhouse-E`'s is, 1.1 m higher. So the
membrane's parapet skirt, and both jambs of the scupper slot, turned out 205 mm **horizontally
into thin air at z ≈ 14.43–14.76** — because the Unit8 roof, 1.5 m below, ran into a wall that
happened to share their plane. Of the 19 edges turned out, **9 were on no elected face at all**.

This is the same failure as `_next_lift`'s first attempt (above): a shared plane is not a shared
face. It is worth noting how long it hid — `out` has been authored at 205 mm since the parameter
file landed, and the rig exercises it happily, because the rig has exactly one turn-out wall and
nothing coplanar with it anywhere.

**The fix.** The elected faces are now kept *with* the plane they offset onto, and a candidate
edge is projected back onto the substrate and must **meet those faces there** — `_meets_region`,
an exact 2D segment-versus-triangle-region test in the plane, boundary contact included. Boundary
contact matters and is not slack: a panel stopping on a wall very often ends exactly on the edge
of the wall's own face, and the membrane over `Parapet-Unit8-N`'s cap overlaps `Headhouse-E`'s
elected face by only the 8 mm the offset itself adds. It turns up, correctly, and a containment
test that sampled the midpoint alone would have dropped it.

The blast radius is exactly what it should be:

| | before | after |
|---|---|---|
| Rig, both skins | — | **byte-identical** |
| Walls-and-caps bake, both skins | — | **byte-identical** |
| Unit8 Cladding (`out: 0.0`) | — | **byte-identical** |
| Unit8 Membrane | 19 edges turned out | 10 |
| skin separation | 8.000 mm | **76.230 mm** |
| membrane ↔ cladding crossings | 35 | **0** |

76.230 rather than 77.000 is the sloped taper absorbing its share, the same way the rig reads
76.071 against its own 77; clearance is 7.8808 / 84.1503 mm, both above `distance − slope`.

The ten survivors all sit at z ≈ 12.90–13.11, on the Unit8 roof and its parapet caps, where the
flange was actually elected. The membrane runs up to the headhouse wall and **turns up** 205 mm
against it — 12.9061 → 13.1111, exact — which is the upstand the rule was written for, and the
first time this rig has produced one on a real substrate.

`tests/test_offset.py::test_a_turn_out_stops_at_the_elected_faces_not_at_their_plane` poses it in
miniature: two lifts of one wall presenting the same plane, only the lower elected. It turned out
at z = 1.9 before the fix. 63 tests, ~3.2 s.


## The cornices bake (2026-08-19)

`unit8-parapets-caps-clt-insulation-headhouse-cornices.obj` **replaces** the Unit8 bake on disk —
same substrate plus two cornices, and the earlier file is gone. 29 `o` groups, 36 parts, 18
elements.

- `Cornice-Unit8-E` — x −0.17…0.00, z 13.0066…13.0766: a 170 × 70 mm band the full 8.87 m of the
  east facade, standing proud of `Parapet-Unit8-E`'s face with `CapPlate-Unit8-E` (widened west to
  −0.17) oversailing it.
- `Cornice-Headhouse-E` — x 7.98…8.08, y 4.785…5.185, z 14.425…14.495: a 400 mm stub at the
  scupper, projecting 100 mm. This is the **new scupper detail** — the outlet drip.

### It would not skin at all

`substrate.classify` refused: `Cornice-Headhouse-E` has horizontality **0.533**, inside the
authored 0.05 margin of the halfway mark. `Cornice-Unit8-E` did not refuse and was worse — it
reads **0.704** and would have skinned silently as a `ROOF`. Neither is a roof.

The raise named no part. It said only *"horizontality 0.533 is within 0.05 of the halfway mark"*,
which in a 36-body bake is a number to match by hand against every part. `substrate.role_of` now
wraps the classify-an-element call both callers were making separately — `build.group_caps` and
`Faces.roles` each unioned the bodies and classified them — and re-raises naming the element:
*"Cornice-Headhouse-E: horizontality 0.533 …"*. That is `Fail at the seam, addressed` applied to
the one raise that was not.

### What Duncan asked for, 2026-08-19

> At the east facade where the cornice is at the top of the parapet, both the membrane and
> cladding should cover the cap plate as before, however the cladding on the facade should stop
> below the cornice. At the scupper only the membrane should cover the cornice and turn its skirt
> down. The cladding on the headhouse east facade should stop below the cornice like on the east
> facade.

### `group_cornices`, and how little it turned out to need

The rule is in CLAUDE.md. What is worth recording here is that **the membrane side needed no new
rule at all** — joining the cornice to its parapet was enough:

- at the scupper, the cornice's exposed top is caught by `membrane_faces`' "every upward face of a
  climbed wall" and its front face by `membrane_skirts`' "down the exterior face of every wall
  carried over". Measured: membrane over the top at z = 14.503, skirt down the face from 14.503 to
  **14.433** — the full 62 mm drop on a 70 mm band.
- at the east facade the same rules do nothing, because the cornice's top is buried under the cap
  plate (they share z = 13.0766, so it cancels in the union) and its face is coplanar with the
  cap's. The membrane there is unchanged, "as before".

Only the cladding needed telling, and only by exclusion.

**Two false starts, both instructive.** The first rule was *within its height, strictly shorter,
wholly outside its plan footprint*. `Parapet-Unit8-W` satisfies all three against `Headhouse-S` —
it butts the outer face, sits inside a 3.075 m wall's height and is shorter than it — and became
its cornice, which made the merged element read `AmbiguousPart: Headhouse-S: measures disagree`.
Adding *projects less far than the wall is thick* separates them with nothing authored: 3.34 m
proud of a 420 mm wall is a wing, 100 mm proud of it is a band. The first rule also had to gain
the height-containment test to keep `group_cornices` from claiming the cap plates that
`group_caps` exists to claim.

### The numbers, and one false alarm

| | faces | residual | clearance | folds |
|---|---|---|---|---|
| Membrane (8 mm) | — | 1.16e-16 | 7.8808 mm | 6 |
| Cladding (85 mm) | — | 7.36e-16 | **63.9999 mm** | 6 |

Separation 29.308 mm. **The cladding's `WARNING: 21.000 mm inside the requested offset —
self-intersecting` is a false alarm**, and this is the first time that check has cried wolf.
Verified four ways: zero membrane↔cladding crossings both directions, zero self-crossings in
either skin, no face centre of either skin inside any part, and **no skin edge crossing any
part's surface at all**. The cladding has **zero faces in either cornice's z band** — it stops at
z = 14.34, which is exactly 14.425 − 0.085, the mitre against the cornice's underside offset
plane. That is "stops below the cornice", built correctly.

What the 64 mm actually measures is a cladding face centroid 64 mm below the scupper cornice's
underside. `measure.clearance` samples vertices and centroids and cannot tell *terminates near a
projecting feature* from *folds through itself* — its docstring claims the latter. A skin that
deliberately stops short of a feature standing proud of the wall will always read low, so the
number is no longer the whole regression check it was. See the open item.

Inert where there are no cornices: the rig and `headhouse-walls-parapets-caps-clt-insulation.obj`
both come back **byte-identical**, checked against `HEAD`. 64 tests.


## The lap: skirt and flange were the same thing (2026-08-20)

Duncan, brainstorming, after asking for the north-side junction and the bare scupper cheeks:

> is it possible we have been treating the flange and the skirt as separate things when really
> they are the same? What about just one rule: When membrane meets an exterior vertical surface it
> never terminates at that edge. It always flanges onto the vertical face. It can flange up, down,
> horizontally, or around a corner.

He was right, and the two defects he named turned out to have **one cause**. `wall_faces` sorts a
wall's vertical faces three ways — exterior, interior, end — and only exterior and interior were
ever dressed. Every bare termination of the membrane in the cornices bake was on an "end":

| where | faces | why bare |
|---|---|---|
| scupper cheeks x2 | `Cornice-Headhouse-E`, `Parapet-Headhouse-E`, `CapPlate-Headhouse-E`/`E2`, taper ends | normals ±Y, across the parapet's fall |
| north junction | `Headhouse-N`'s west end face at x = 8.08 | ditto |

Fifteen edges, all of them. And the upstand that *did* exist at the north junction existed **by
accident**: `_meets_region` passed it because the cap edge overlaps `Headhouse-E`'s elected face
by the 8 mm the offset itself adds.

### What replaced what

`_hem`, `_turn_out`, `_meets_region`, `membrane_skirts`, `membrane_flanges`, `cladding_skirts`,
the `turn_down`/`turn_out` spec fields and `_rules`' `flanged` are **gone**, replaced by `_lap`
plus a per-skin `lap` predicate saying which faces a skin may continue onto. `CLAUDE.md` carries
the rule; what belongs here is what it cost to get there.

- **`_across` reads the direction off the receiving face**, from that triangle's own third vertex.
  A centroid was tried first and is wrong: part 4's face runs the full width of the rig, past
  *both* sides of the wall whose skirt turns onto it, so the centroid points whichever way the
  longer side happens to lie. It turned the rig's collar into part 2 instead of away from it.
- **Level, and only level, is snapped.** The upstand at the north junction came out 2.3° off
  vertical, because the cap plate is laid to fall and perpendicular-to-the-arris inherits that.
  It also broke the corner fold, whose arris test wants the lap direction to lie in the receiving
  plane. Snapping a mostly-vertical lap to vertical and a mostly-sideways one to horizontal fixed
  both and restored every measured figure to its pre-change value. This is `_turn_out`'s
  dominant-axis snap arriving from the other side: it needed one because it extruded along the
  *departing* panel's normal, and `_across` needs one only for the fall.
- **Two datums, kept deliberately.** A drip is measured on the substrate and an upstand from the
  skin edge — the pre-existing pair of conventions, now chosen by direction instead of by which
  function you were in. Collapsing them was tried on paper and rejected: substrate-space selection
  makes an upstand 8.3 mm short of what a roofer measures off the finished surface. Two authored
  distances therefore stay.
- **The knife at the scupper.** Making the receiver set geometric raised `_reconcile` twice, both
  at the slot: the drip is exactly as wide as the slot, so its end faces are coplanar-and-opposed
  to the cheeks, and the taper's end stands 8.6 mm proud of the sill on the parapet's own inner
  plane. `_receivers` now settles these before the solve — a covered face outranks a lap, and
  between two laps the concave arris wins. `Cornice-Headhouse-E`'s 100 x 70 mm ends stay bare;
  that is the accepted price, and it is the same family as the 2026-08-16 sliver decision.
- **Mitering is per receiving plane.** Chaining every lap that shares an endpoint, regardless of
  plane, asks `lstsq` to intersect two lines that do not meet — it threw a **400 mm triangle
  across the scupper's mouth** and dropped the skin separation to 8.667 mm. Two drips at a wall
  corner need no miter anyway: `drip_at` solves their shared arris on both planes at once.
- **A run's end is only free if nothing turns the same way there.** Without that, the two drips
  meeting at the Unit8 cap's west corner each read the other's plane as "somewhere to fold onto",
  folded, and the miter then collapsed both into nothing — the north drip lost its western 205 mm.
- **A continuation runs only where the whole of it lands on substrate.** There is no cutting in
  `_lap`, only whole quads. The parapet's inner face meets the cheek 8.6 mm above the sill, and a
  62 mm drip run on down from there put two vertices **inside** `Parapet-Headhouse-E` —
  `tests/test_import.py`'s `part.contains` assertion is what caught it, not `clearance`.

### What it fixed, measured

| | before | after |
|---|---|---|
| scupper cheeks (each 0.112 m²) | bare | covered, x 8.072…8.508, z 14.503…14.760 |
| north drip east end | stopped dead at x = 8.08 | runs on to **x = 8.277** |
| north upstand | 8 mm diagonal sliver, free vertical edge | exactly vertical, 13.1189 → **13.3239** |
| north face wrap | none | **x 8.072…8.277, z 13.1189…13.3239** — what Duncan asked for |
| membrane ↔ substrate | — | no vertex inside any part, either bake |

And every figure that was already right is still right, which is the point: skin separation
**76.071 / 77.000 / 29.308 mm** on the rig, the walls-and-caps bake and the cornices bake, and
clearances **7.7760 / 7.8808 / 7.8808 mm**, all identical to the values before the change. The
rig's four-panel collar still miters to x = 1.7865 and the cladding is untouched on all three.

Not byte-identical, though — `_lap` numbers its vertices differently and the continuation adds
panels the old code had no way to make. The regression check for this work was geometry
(triangle sets up to renumbering) for the first two stages, then the printed figures.

### What `/code-review high` caught (2026-08-20)

Five, all real, all fixed. The first is the same trap this file already records twice:

- **`_knives` paired faces on the plane equation alone.** Two walls 2.6 m apart presenting one
  plane facing opposite ways were a knife, so covering one silently refused the lap onto the
  other. *A shared plane is not a shared face* — the third time, after `_turn_out` and
  `_next_lift`. The pair must now share a vertex, which is where the contradiction actually lives
  since `_reconcile` is a per-vertex rule.
- **Plane identity was exact equality of a 1 µm-rounded bucket.** manifold3d leaves faces up to
  ~5e-7 m off plane, half a cell, and the headhouse taper's top is **already split** in the
  shipping bake, its halves 7.8e-7 apart. On a vertical face that would silently defeat a run-on
  and a miter — a run-on that does not happen is exactly the pinhole this work set out to close.
  `_plane_ids` now matches each face against the representatives already found, within the same
  tolerance as everything else, and everything downstream keys on its id.
- **A run-on invalidated the run it lengthened.** It moves the seam, so every key read from
  `runs()` before it fired was stale — the *other* end of that same run included, which then read
  the first end's vertex as its own and was blocked by the `tip == root` guard for good. A
  substrate symmetric about its own centre came out lapped on one side only. Continuations are now
  applied one at a time, re-reading the runs after each.
- **The raise for a zero `drop` and a zero `out` recommended something that crashed.** It said to
  give the rule set no `lap`, and `partial(None, fall=fall)` is a `TypeError` even though
  `skin_over` accepts `lap=None`. `skins()` now builds that spec, and it is a real thing to want:
  a skin that stops where it ends.
- **The schema and the parameter file still described `turn_out`** and the out-vs-turn_out
  cross-check, neither of which exists. Documentation asserting a property the code does not have
  is invisible to a test by construction — the standing reason this review runs at all.

All three tests it prompted are in `tests/test_offset.py`.

### What Duncan found in Blender, 2026-08-20

Three observations on `build/Membrane.obj`, all real.

**F40 and F41 were extraneous — fixed.** Two 205 mm panels across the mouth of the scupper at
x = 8.492, which is `Roof_Headhouse_InsulationTaper`'s end face offset the *wrong* way: the knife
at x = 8.5 that this bake has always folded at. `_receivers` refused it as a seam receiver, but
`carry_on`'s fold was handed `allowed & ~kept` and never asked. The knife test is a property of
the face, not of how a lap arrived at it, so it is now `_knifed`, shared by both paths.

**The coplanar edges went with them.** E116, E83 and the ones on the cheeks were the seams where
those two panels merged into their neighbours in `faces_as_ngons`. Measured after the fix: **0
coplanar edges**, and self-crossing n-gons down from **2** (the baseline, before any of this work)
to **1**.

**The sliver at V85 / V87 / V45 is still open**, and it is not a rounding error. At the *south*
junction two continuations run on from one corner along two different correct lines: the collar
follows `CapPlate-Unit8-W`'s sloped top arris and the drip's run-on is flat, so they meet exactly
at x = 11.108 and diverge to **7.3 mm** by x = 11.313. A "do not run on into ground another lap
already holds" guard was written and removed again — it never fires, because the sliver is
*between* the two panels rather than under either.

### Why the scupper mouth and the cornice ends stay bare — it is not the lap rule

Duncan, broadening the keep-or-drop question: he expected `F30`/`F32` (the cheek laps) to wrap
round the mouth arris onto `Parapet-Headhouse-E`'s outer face, and `F22` (the sill) to turn down
the **ends of the cornice**. All four of those fail at the **same two vertices**, and the lap rule
is not what stops them.

Vertices 55 `(8.08, 4.785, 14.495)` and 59 `(8.08, 5.185, 14.495)` are the lower corners of the
scupper mouth. Four planes meet at each: the facade `-X`, the cornice's end `-Y`, the sill `+Z`,
and the cheek `+Y`. The cornice's end and the cheek are the **knife** — the drip is exactly as
wide as the slot — so `_reconcile` fires, re-reads the planes from the covered faces alone, and
keeps only two:

| vertex | planes present | kept | dropped |
|---|---|---|---|
| 55 | `-X`, `-Y`, `+Z`, `+Y` | `+Z`, `+Y` | `-Y` (cornice end), **`-X` (facade)** |
| 59 | `-X`, `-Y`, `+Z`, `+Y` | `-Y`, `+Z` | `+Y` (cheek), **`-X` (facade)** |

Dropping the facade is what blocks the mouth wrap: the vertex is left at `x = 8.08` instead of
`8.072`, so the cheek lap's edge is not on the facade's offset plane and `_lap`'s fold declines it
— correctly, since placing it would put the panel 8 mm inside the wall.

**Tested, not argued.** Letting the knife faces be lapped onto anyway (keeping them out of
`covered`, so the solve is untouched) *does* generate the cornice-end drips — and they land **on
the substrate**, clearance `0.0000 mm`, because their seam springs from a vertex sitting 16 mm on
the cheek's side of the plane it is meant to hang from. There is no lap rule that fixes that.

**A narrower `_reconcile` unlocks half of it — built, measured, and backed out.** The rule drops
*every* uncovered plane at a contradictory vertex, but the contradiction is only ever between one
pair. Keeping the planes that contradict nothing — the facade at both vertices — moves the mouth
corners to `x = 8.072`, and **the two mouth wraps then appear exactly as Duncan described them**:
205 x 205 mm panels on the facade at `y 4.588…4.793` and `y 5.177…5.382`, `z 14.503…14.708`. It is
about 20 lines (`_uncontradicted`, called from `_reconcile` where it currently returns `reduced`).

It does not land, because it puts the two skins **through each other**:

| | separation | membrane↔cladding crossings |
|---|---|---|
| as it stands | 29.308 mm | **0 / 0** |
| + `_reconcile` narrowing | 8.667 mm | 2 / 7 |
| + narrowing + "cladding does not floor an opening" | 23.000 mm | 1 / 1 |

Zero crossings is the verified state of this bake (2026-08-19) and a crossing is exactly what the
separation check exists to catch, so this is not a warning to reinterpret. The rig and the
walls-and-caps bake are untouched by either change; all of it is at the scupper.

The intermediate rule in that table is worth keeping a record of, because it took three attempts
to get right and the first two were instructive. **The cladding should not line the inside of a
400 mm outlet**: with the mouth vertices freed, its coping mitre flares out through the mouth to
`(7.995, 4.7, 14.58)` and runs to within 8.7 mm of the membrane lining the cheek.

- *"a wall top flanked by two faces looking **at** each other floors an opening"* — per element,
  this drops the **coping** as well, because the slot cuts through the cap plates too and their
  reveals look at each other across it.
- *"a wall top flanked by two faces looking **away** from each other caps a wall"* — per element,
  this keeps the sill, because the cornice is grouped into the parapet and its own two ends are an
  away-facing pair on the very same coplanar region. It also drops part 1's hip in the rig.
- *toward-facing, per **body*** — correct on all three bakes: 3 faces of `Parapet-Headhouse-E` in
  both scupper bakes, nothing in the rig. A cap plate's own thickness is an away pair, the sill's
  own flanks are only the cheeks. Per body rather than per element is the whole of the difference.

Even with it, one crossing survives each way: the membrane's **sill panel** at `z = 14.503`, which
runs out through the mouth to `x = 7.972` over the cornice, passes through the cladding's facade
panel at `x = 7.995`. That is a detail question rather than a geometry one — *what does the
cladding do at a scupper mouth that sits above a cornice?* — and it is Duncan's, particularly
since it is his 2026-08-16 decision that the slot be open to the sky precisely so the cladding's
claim on the sill would be correct. **Nothing here is blocked on code.**

**The cornice-end drips need the folded vertex split**, which is the standing self-intersection
item, unchanged since 2026-08-16. One vertex has to become two — `y = 4.777` for the cornice side
and `y = 4.793` for the cheek — and nothing in the offset can do that today.

So the answer to *"can the continuation be leveraged to buy this too?"* is **yes, but only behind
a decision that is not about the lap rule**. The fold path is what places the mouth wraps, so with
the narrowing the continuation has three customers rather than one — and without it, one.

### The keep-or-drop call on the continuation: kept

Duncan handed the call back. Kept, and the reasoning recorded so it can be reversed cheaply:

- It delivers the **north junction**, which is what this whole piece of work was asked for on
  2026-08-20. Dropping it to save 109 lines would un-deliver the thing that started it and reopen
  a leak that was already deferred once.
- It is **isolated**: `carry_on`, `arris_at`, the driver loop and `_inside`, behind one call site
  and a `rounds` bound. Removing it is deleting those and passing `rounds=0`; nothing else reads
  them.
- It gains a second and third customer the moment the scupper-mouth detail above is settled.

Against: the **south-junction sliver** is its and remains open — 205 x 7.3 mm on `y = 7.548`,
between the collar's lower edge (which follows `CapPlate-Unit8-W`'s sloped top arris, rising to
`z = 13.1262` at `x = 11.3129`) and the fold band's flat top at `z = 13.1189`. Both panels are
right in themselves; the strip between them is genuinely uncovered, and closing it means clipping
one to the other's boundary rather than emitting whole quads. It is the same clipping the lap
lacks everywhere else. A guard that suppressed the run-on where another lap already held the
ground was written and removed — it never fires, because the sliver is *between* the two panels
rather than under either.

### The scupper as an opening, and what covering the cheeks would take (2026-08-20)

Duncan, on the baked result: *"There should be no cladding covering the scupper sill"*, and
*"can we treat the scupper cheeks the same as the top of the cap plate? They should be skinned by
both membrane and cladding... We might even get the membrane flanging out onto the exterior of
Parapet-Headhouse-E for free."*

**`_opening` landed**, and with it the first half. It reads the two things a slot cut through a
wall leaves behind, from geometry alone:

- **cheeks** — two vertical faces of one **body** looking *at* each other. The faces across a
  wall's thickness and the two ends of a wall are also opposed, but look *away*; that sign is the
  whole test, and it is `_next_lift`'s measure again.
- **floor** — an upward face with a cheek pair standing **over** it.

Both qualifiers were arrived at the hard way and both are load-bearing:

- *per body, not per element.* The slot cuts the cap plates too, so per element
  `CapPlate-Headhouse-E`'s reveal and `E2`'s look at each other and the **coping** reads as a
  cheek pair. And the cornice is grouped into the parapet, so its own two ends are an away-facing
  pair sitting on the very same coplanar region as the sill.
- *cheeks that rise above it.* The same two cheeks touch the wall's own coping where the slot cuts
  through it — but there they stop at that level rather than standing over it. Without this the
  coping reads as the floor of its own opening. Tried first as "has a toward pair and no away
  pair", which works on the bakes only because the roof buries the parapet's inner face at the
  slot, and fails on a slot cut through a free-standing wall.

`cladding_faces` now subtracts the floor. The cladding's 5-gon at `z = 14.58` — Duncan's E86–E90 —
is gone, the rig and the walls-and-caps bake are unchanged, and the cornices bake keeps
`29.308 mm` separation and **0 crossings**.

**Covering the cheeks does produce the mouth flange — and does not land.** Adding
`cheeks & climbed` to `membrane_faces` gives exactly what Duncan predicted: the membrane covers
the cheeks as faces rather than arriving as three overlapping laps, the facade beside each cheek
becomes a face the skin runs into, and the lap flanges out of the mouth onto it — panels at
`y 4.588…4.793` and `y 5.177…5.382` on `x = 8.072`. It is right in principle. Two things stop it:

- **13 membrane→cladding crossings.** The mouth flange runs `z 14.718 → 14.923`, which is 205 mm
  above the parapet and straight through the cladding's coping. The lap has no way to stop at the
  top of the wall.
- **Cladding the cheeks pokes 85 mm into the roof.** With `cheeks` added to `cladding_faces` too,
  the cheek panel miters against the parapet's inner face and reaches `x = 8.585`, `3.66 mm` from
  the roof taper: cladding clearance `84.9999 → 3.6594 mm`. The reveal's inner end opens onto the
  roof and there is no datum in plan to stop it — the same standing item as *"the cladding
  overhangs part 4's bare ends by the offset"*.

Both are the missing **clipping**, again: the lap places whole quads and `keep` places whole faces,
and neither can stop at the boundary of what it is dressing. That is now the blocker on four
separate things — the south sliver, the mouth flange, the clad reveal, and the `_reconcile`
narrowing's crossings.

## The extended cornice, and the scupper finished (2026-08-21)

Duncan exported it. `Cornice-Headhouse-E` now runs `y 4.685…5.285`, 100 mm past each jamb;
nothing else moved. **The prediction held, and it cost no code at all**: on the new bake, with the
rules exactly as they were,

- **folds 6 → 4.** Vertices 55 and 59, the scupper mouth's lower corners, are no longer
  contradictory. The cornice's ends are no longer coplanar with the cheeks, so there is no knife
  there, so `_reconcile` no longer drops the facade plane with it.
- **the membrane flanges out of the mouth**, on `x = 8.072` at `y 4.472…4.793` and
  `y 5.177…5.498` — what Duncan asked for and what the `_reconcile` narrowing was built to buy.
- **the cornice's ends take their drips**, `x 7.972…8.072`, `z 14.433…14.503` — refused before,
  where they landed *on* the substrate.
- 0 crossings, nothing buried, `clearance 7.8808 mm`.

The `_reconcile` narrowing recorded above is therefore **unnecessary rather than untaken**, and
should stay untaken: it bought the same wrap by weakening a rule, where the substrate bought it by
removing the degeneracy.

### Covering the cheeks, and the clip that let it land

Duncan: *"can we treat the scupper cheeks the same as the top of the cap plate? They should be
skinned by both membrane and cladding."* Half of it landed.

`membrane_faces` now adds `cheeks & climbed`. The cheeks lie *across* their parapet's fall, so
`wall_faces` calls them ends and neither exterior nor interior could ever reach them — which is
why the membrane used to arrive at them as three overlapping laps rather than covering them.

It did not land on its own. Covering them put **13 membrane→cladding crossings** at `z ≈ 14.83`,
all of them laps springing off the newly-covered cheek and running their full 205 mm onto faces
far shorter than that — a 34 mm cap-plate reveal, most of them — ending 120 mm above the top of
the wall and through the cladding's coping. So:

**`_room` / `_leaves`: a lap is now cut to the face it lands on.** `carry_on` already refused a
*continuation* that would leave the substrate; a round-1 lap had no such check at all. It marches
along the lap direction over the coplanar triangles — marching rather than testing the far end,
because the union triangulates a wall and a lap commonly crosses several of its triangles: the
62 mm drip off a 34 mm cap plate must still run its full depth down the parapet's coplanar face
below. A lap with no room is dropped.

With it, the numbers on every bake are unchanged and covering the cheeks is clean:

| | separation | clearance | crossings |
|---|---|---|---|
| rig | 76.071 | 7.7760 / 84.6091 | 0 / 0 |
| walls-and-caps | 77.000 | 7.8808 / 84.9999 | 0 / 0 |
| extended cornices | 25.654 | 7.8808 / 63.9999 | 0 / 0 |

The scupper is now dressed all through: both cheeks `x 8.072…8.508`, `z 14.503…14.760`; both
cornice ends `z 14.433…14.503`; the facade carrying membrane from `14.433` to `14.760` across the
whole parapet, mouth flange included, and **not a millimetre above the cap**.

**The cladding covering the cheeks did not land**, and is not a clipping problem. Its cheek panel
miters against the parapet's inner face and reaches `x = 8.585` — 85 mm past it, `3.66 mm` from
the roof taper, `clearance 84.9999 → 3.6593`. That is a `keep` face's offset against an *unskinned
neighbour*, the standing *"the cladding overhangs part 4's bare ends by the offset"* item, and it
needs a trim in plan that nothing here has. It is one line to add back the day that exists:
`| (cheeks & faces.of_role(substrate.WALL))` in `cladding_faces`.

**The superseded bake is now wrong to build.** With the cheeks covered,
`unit8-parapets-caps-clt-insulation-headhouse-cornices.obj` puts a membrane vertex **inside**
`Cornice-Headhouse-E` — the knife at the mouth, which is exactly what the extension removed.
Nothing reads it; deleting it is Duncan's call, as the last three were.

### What `/code-review high` caught (2026-08-21)

Seven, all real, all fixed. Three of them were the lap doing by sampling what it should have done
by marching, which is the same mistake three times:

- **The run-on bridged a void.** It tested the tip and the far end and nothing between, so two
  bodies presenting one plane with a 130 mm gap between them read as solid and the lap hung over
  it. It marches with `_room` now, like a round-1 lap.
- **The fold checked one end of the band it was placing**, while its comment claimed "all of it
  has to land on the face". Both ends now, and marched.
- **The continuation budget truncated silently.** `rounds * len(segs)` was read once, at the
  *initial* count, and `carry_on` appends — 27 segments became 33 on the shipping bake. Exhausting
  it dropped the membrane from 145 faces to 137 with no raise and no report, which is exactly the
  silent omission this module is written against. The loop now terminates on `tried` alone and
  `rounds` **raises** if it is ever reached.
- **The 45-degree snap flipped a drip into an upstand.** `_across` rounded anything under 45° onto
  the horizontal, and `reach` then read the flattened `t_z` and billed a lap raking 40° *down* the
  205 mm upstand instead of the 62 mm drip. `RAKE = 0.05` now: a lap within 3° of level is level,
  and one that genuinely rakes keeps its direction and is priced by it. The docstring also still
  claimed there was no snapping at all.
- **`corner()`'s parallel test was scale-dependent** — `|u1 × u2| < PLANE_TOL` on *unnormalised*
  seam directions, so two 3 mm seams read parallel below 6.4° and two 1 mm seams at any angle, and
  the miter was skipped. Carried over from `_turn_out` unexamined.
- Dead `Counter` import, and `_plane_ids` recomputed ten times a build; it is cached on the body.

One of the fixes then exposed an older bug of the same family: taking the seam direction from the
two ends' *substrate vertices* blocked the second end of any segment whose first end had already
run on, because running on clears that end's vertex. A symmetric substrate came out lapped on one
side. It reads the direction from the ends as points now.

### Extending the cornice past the scupper — yes, and here is exactly what it buys

Duncan asked, with an independent reason of his own: water should not fall off the end of a
cornice into the rainscreen cavity. On the geometry the answer is also yes, and specifically:

The cornice is **exactly as wide as the slot**, so its two end faces are coplanar with the cheeks
and face the other way. That single degeneracy is the **knife**, and the knife is behind all of
this:

- vertices 55 and 59 are folds only because of it. `_reconcile` then drops the **facade** plane
  along with the cornice's end, which is what leaves the mouth corners at `x = 8.08` and refuses
  every lap that wants to spring from them;
- the cornice's own end faces cannot be lapped onto at all — tested, they land *on* the substrate,
  clearance `0.0000 mm`;
- `_receivers` has to carry a knife rule, and `_knifed` has to be shared with the fold path,
  because of it;
- two of the three attempts at `_opening` were broken by the cornice's ends and the sill being one
  coplanar region.

Extend the cornice past each jamb — any real overhang, 100–200 mm — and the ends are no longer
coplanar with the cheeks. There is then **no knife at the mouth at all**: 55 and 59 stop being
folds, the facade plane survives, the mouth corners offset properly, and the cornice's ends become
ordinary faces to drip down. The `_reconcile` narrowing becomes unnecessary rather than merely
untaken.

It does **not** fix the clipping problems above — the mouth flange overrunning the parapet top and
the clad reveal reaching into the roof are independent of it. Worth doing anyway: it removes a
degeneracy that has cost four separate workarounds, and Duncan's own reason stands on its own.

### Has it simplified the code? No — measured

| | before | after |
|---|---|---|
| `skin/offset.py` code lines | 384 | **561** (+46%) |
| `build.py` code lines | 440 | **425** |
| removed | `_hem` 25 + `_turn_out` 97 + `_meets_region` 23 = **145** | |
| added | | **322** |

Where the 322 went, and this is the useful split:

- **the lap proper — 163 lines** against the 145 it replaced. A wash, for two predicates instead
  of four, one direction rule instead of two hand-elected face sets, and `flanged` retired.
- **the continuation — 109 lines** (`carry_on`, `arris_at`, the driver loop, `_inside`). Entirely
  new capability, not a replacement for anything, and the only thing that needs it is the north
  junction: the scupper cheeks are covered **with or without it**, measured. Every defect above
  is in it or was found by it.
- **robustness the review demanded — 50 lines** (`_plane_ids`, `_knives`, `_knifed`). The old code
  never asked "is this the same plane" structurally, so it never had to answer it correctly.

So the *rule* is simpler and the *mechanism* is not. `build.py` is where the simplification
actually shows.

### The cladding is deliberately not done

`cladding_laps` is still the old election — `interior`, nothing else — held back because Duncan
asked to settle the membrane first. Widening it to `np.abs(faces.normals[:, 2]) < TOL` is the
whole of the change; the machinery underneath is already general. Expect it to need its own
conversation about what the cladding does where it runs into a cornice, since it is the skin that
deliberately *stops* below one.

### Left open by this work

- **T-vertices at the run-on.** The drip's inner edge is now one edge from x = -0.178 to 8.277
  while the covered cap top it springs from ends at 8.072, so the two meet along a T rather than
  sharing a vertex. Coincident geometry, no hole, but it is the T-vertex item below arriving for
  real.
- **`rounds=3` is a cap, not a proof.** `_lap` iterates continuations until nothing grows, bounded
  by a round count. It settles after two on every substrate here, because only an end that sits on
  a substrate vertex can continue and a fold's rim end does not. That is an argument, not a test.
- **The lap cannot clip.** It places whole quads, so where a continuation would overhang the face
  it lands on, it is not placed at all rather than shortened. The 8.6 mm of cheek below the sill's
  offset is the one place in these bakes where that shows.

## The scupper made symmetrical (2026-08-21, second pass)

Duncan built the live bake and reported five defects around the scupper and the two roof
junctions. All five, and they are **three** causes:

| his words | cause |
|---|---|
| *"F34 is missing on the south side of the scupper. The scupper is symmetrical."* | `_room` |
| *"F31 is different from its counterpart on the north side."* | `_room` |
| *"F28 does not wrap the corner like before."* | the fold's probe |
| *"F39 does not extend as far east as before (.062 east of V48 — should be .205)."* | `reach(along)` |
| *"F28 should extend .205 to the south"* | `_room` |

**`_room` read the first coplanar triangle holding its probe, not every one of them.** A lap
always starts on an arris, so the probe — 8 µm along the lap direction — sits on a shared edge or
a shared corner *every single time*, and two or three coplanar triangles hold it. Only some carry
the ray on; a triangle that merely corners on it exits at once and reports no room at all, and
`_room` then marched nowhere and the lap was dropped. Which triangle came first is manifold3d's
triangulation order, and **that is mirrored by nothing** — so a detail that is mirrored in the
substrate came out unmirrored in the skin. Measured at the cornice's two ends, same call, same
distance wanted: 0.205 north, **0.0** south.

It takes the furthest exit among all the holders now, and stops when none of them carries the ray
further. Membership is a tolerance question and cannot be tightened out of existence — the south
probe is 9.6e-7 outside the corner triangle's edge, well inside `PLANE_TOL` — which is why the
regression test transcribes the two real triangles as literals rather than posing a made-up pair.

**The fold's probe started `distance` short of the arris at a convex corner.** The seam a fold
springs from lies on the offset of the face the lap is *leaving* as well as of the face it turns
onto, so it sits `distance` off the arris along the fold direction. At a concave corner that is
`distance` **past** it and harmless; at a convex one it is `distance` **short**, out over the void
beyond the corner, and the march reports no room. So **no fold had ever been placed at a convex
corner** — the mechanism worked only where the corner happened to be internal, which is every case
it was written against (the cornice's ends, the scupper cheeks). `tip` is on the arris, so it
supplies the slide.

**A run-on was priced by `reach(along)`.** `reach` answers "which way does this lap leave its
arris" — down is a drip, up or sideways an upstand. A run-on does not leave an arris at all; it
runs *along* one. Asking `reach` about the run direction made a seam raking down a coping laid to
fall read as a drip at one end and an upstand at the other, purely because the two ends face
opposite ways along the same fall. One straight arris, 62 mm one way and 205 mm the other — which
is exactly what Duncan measured at V48. A run-on runs sideways, so it runs `out`.

### What it cost, and what came with it

| | rig | walls-and-caps | live bake |
|---|---|---|---|
| separation | 76.071 | 77.000 | 25.654 |
| clearance, membrane / cladding | 7.7760 / 84.6091 | 7.8808 / 84.9999 | 7.8808 / 63.9999 |
| crossings both ways, self-crossings, buried faces | 0 | 0 | 0 |
| every membrane face centre within … of the substrate | 8.224 mm | 8.040 mm | 8.058 mm |

The `_room` fix changes **nothing** on the rig or the walls-and-caps bake, byte for byte — it only
ever fires where a probe lands on a marginal corner. The other two do change the rig, and both
changes are the defect they fix showing up there too:

- the turn-out against part 4 now folds round the corner onto the wall beside it at both ends
  (2 new bands), which is Duncan's *"it can flange up, down, horizontally, or around a corner"*
  arriving where it always should have;
- the drip run-on off the rig's raking arris goes 62 → 205 mm at the end that faces downhill.

`test_a_skin_with_no_datum_is_not_trimmed` pins the rig membrane's lowest vertex and was
re-blessed 1.090 → 0.959 for the first of those.

**Laps that were being dropped now exist, and they bring their overlaps with them.** The parapet
ends that die into a taller wall — `Parapet-Unit8-N` into `Headhouse-E`, `Parapet-Unit8-W` into
`Headhouse-S` — now get the sideways collar the rule always specified, and the run around each
end profile chains and mitres as one. Total coplanar double-covered area in the live membrane goes
151,077 → 221,990 mm², and **that increase is the symmetry itself**: the largest overlaps on the
north side of the scupper (17,270.0 mm²) now appear identically on the south (17,269.9 mm²). The
overlapping-laps condition is pre-existing — the top figures are unchanged — and is the standing
"the lap cannot clip" item, not new behaviour.

**Two small bands that came free with the corner fold**, worth Duncan's eye: at each scupper jamb
the lap onto the cap plate's reveal now folds round onto the facade, 205 x 19 mm at
z 14.718…14.737. That is *within* the cap plate's own thickness, not above it, and it is mirrored.

### Four tests, all four red at `c098d15`

- `test_room_reads_every_triangle_holding_the_probe_not_the_first` — the two real triangles as
  literals, marched in both orders.
- `test_a_lap_folds_round_a_convex_corner_it_reaches` — a low wall into a tall one at a building
  corner. `drop=0.0` so the only bands in the skin are the ones under test.
- `test_a_run_on_is_priced_as_an_upstand_whichever_way_the_seam_rakes` — a wedge between two
  taller neighbours; the assertion is symmetry in plan, not a blessed length.
- `test_the_scupper_comes_out_symmetrical_on_the_live_bake` — the live bake's first regression
  check. The **vertex set** is pinned and the triangulation is not: the two sides agree point for
  point, while which diagonal each quad splits on does not have to mirror, and does not.

77 tests, ~4.7 s.

## The hole at the scupper outlet (2026-08-21)

Duncan, having accepted the symmetry fixes: *"Let's revisit the holes at E86, 14, 75, 9, 74, 85.
Now that the scupper cheeks are skinned, are they any easier to close?"*

**Yes — bounded, though not for the reason that would let an offset close it.** Covering the
cheeks supplied the two 18 mm edges that turn the outlet from a **notch in the skin's perimeter**
into a **hole of its own**. Border components of the membrane, same bake, same rules but for
`cheeks & climbed`:

| | components | the outlet |
|---|---|---|
| cheeks not covered | 2 | four edges inside the 37-vertex perimeter loop |
| cheeks covered | **3** | its own **5-vertex, 6-edge closed loop** |

The hole is two triangles pinched at `(8.492, 4.985, 14.503)`, 1729.5 mm² each, and every vertex
they need is already in the mesh. Adding them takes the membrane 67 → 61 border edges with
nothing buried. **Not done**: see the choice at the end.

**Why no offset can close it.** The two edges are 16 mm apart in x because they sit on opposite
sides of the `x = 8.5` knife — the roof insulation butts the parapet **on the parapet's own
plane**, and the slot cuts through that parapet, so both sides of the contact are exposed at once.
It is the 2026-08-16 fold, not a new condition. The riser between them is the taper's end face:
8.6 mm tall at each jamb and **zero at `y = 4.985`**, because the roof falls to the middle of the
outlet and its top meets the sill exactly there. That is the shape of the hole.

That face is `lap`-allowed (it is vertical) but `_knifed` blocks it and `_receivers` never reaches
it, and covering it outright makes the contradiction survive among covered faces, so `_reconcile`
raises rather than dropping a plane:

```
ValueError: the surface folds back on itself at vertex 67 [8.5, 4.785, 14.503618] ...
7 of its faces are covered by a skin, so this is not a stray face that can be ignored.
```

**The substrate lever is closed here, unlike the cornice.** Four variants, each measured, none of
them worth having:

| variant | folds | outlet | clearance |
|---|---|---|---|
| as modelled | 4 | 6 edges, closed | 7.8808 mm |
| taper lapped **1 mm into** the parapet | 2 | still 6 edges — the knife becomes a plain uncovered riser | **1.9999 mm** |
| taper pulled **1 mm off** the parapet | 2 | **0 edges** — closes | **0.2732 mm** — a 1 mm crevice is far narrower than 2 x offset |
| sill laid to the roof's own fall (the wedge filled in, so the taper's end has no exposed height) | 4 | still 6 edges, same shape | 7.8808 mm, residual 1.28e-16 |

The last one is the interesting negative. It is the better detail on its own merits — a flat sill
under a roof that falls to the middle of its outlet leaves an 8.6 mm lip at each jamb — and it
builds perfectly cleanly, but **the knife survives as a zero-height sliver**: manifold3d still
emits plane-16 triangles along the contact line, `_reconcile` still fires at both jambs, and the
hole is unchanged. So the knife is not the 8.6 mm wedge. It is the ordinary condition of a roof
meeting a wall, and no change to the *sill* touches it. (Raising the sill clear of the taper was
already rejected 2026-08-16 on drainage.)

**The choice, for Duncan.** Closing it means a **gusset** — a face that is not the offset of any
substrate face, bridging where the solid has no thickness. That is a new kind of face in a module
where everything so far is either an offset plane or a lap off one, and it has a measurable cost:
the two patches are chords across the fold, so `clearance` reads **7.8808 → 5.8793 mm** and
`build.py` would print its self-intersection warning even though nothing is buried and there are
no crossings. Set against that, there is exactly **one** instance of the condition in all three
substrates — the other two folds, `V33` and `V97`, are at `z = 12.35`, section cuts no skin
reaches — which is the usual argument for waiting until a second one exists before writing a rule.

If it is wanted, the rule has a shape: *a border loop that closes on itself within `2 x distance`
of a reconciled fold vertex is the tear that fold left, and is triangulated*. Detection is cheap
and local; the design question is whether `clearance` should stop being the build's verdict first
— which is the standing item below.

*(Answered 2026-08-22. Duncan said yes, and it was built in `clean` — where `clearance` turns out
not to be a precondition, because `build()` measures the raw emission. Both halves of the rule
sketched here are wrong, and knowingly so: the `2 x distance` bound was already refuted below, and
the surviving criteria are flat / narrow / not-already-covered. See "The gusset as built".)*

## Overlapping laps, and what a cleanup pass would and would not fix (2026-08-21)

Duncan: *"The membrane mesh needs cleaning up. There are coplanar edges (140, 99). There are
intersecting coplanar faces... if we calculate the surface area of the membrane, will the
overlapping faces skew the result? Does Trimesh or Manifold3d provide cleanup? Maybe the holes
could be closed in a cleanup pass."*

**E140 and E99 are not interior coplanar edges — each has exactly one face.** They are the
boundary of a **bowtie quad**: `(10.467, 7.548, 13.1543)-(10.467, 7.548, 13.0766)` and
`(8.072, 3.063, 13.0766)-(8.072, 3.063, 13.1561)`, at the two parapet ends that die into a taller
wall. A miter runs each band's outer line out to where the two meet; where one band lies wholly
**inside** the next — a 205 mm collar off a parapet's end against the 205 mm upstand off the roof
below it, on the same wall — there is no meeting, the intersection lands beyond the far end of the
smaller band's own rim, and its two triangles come out wound opposite ways and overlapping. The
retraced boundary edge is what that looks like from outside.

Six such quads across the two skins. **Two of the four in the membrane are mine**, from the
`_room` fix earlier the same day: it restored collars that were being dropped, and those collars
are what nest. Both cladding bowties are long-standing and untouched by any of it — the cladding
is byte-identical before and after — and the larger is **200,655 mm²**, on `Headhouse-E`'s facade.

**Yes, the overlap skews the area, and by more than a signed grouping shows.** A bowtie's two
halves face opposite ways, so matching planes by `(n, d)` puts them in different groups and misses
their overlap; planes have to be matched **either way up**:

| | summed | true | over by | bowties |
|---|---|---|---|---|
| Membrane at `c098d15` | 125.940573 | 125.797036 | 143 537 mm² (0.114%) | 2 |
| Membrane now | 126.169998 | **125.943129** | 226 868 mm² (0.180%) | 4 |
| Cladding (unchanged all day) | 129.883734 | **129.481482** | 402 253 mm² (0.311%) | 2 |

shapely (GEOS) and `manifold3d.CrossSection` (Clipper2) agree to the µm² on every plane, so the
figure is not an artefact of one engine.

**Neither library offers this at the mesh level.** All measured, not assumed:

- `unique_faces` + `nondegenerate_faces`: 153 → 153 triangles, area unchanged. Exact duplicates only.
- `trimesh.boolean.union([skin])`: `ValueError: Not all meshes are volumes!`
- `trimesh.repair.fill_holes`: `ModuleNotFoundError: networkx` — and the wrong tool anyway, it
  would try to close the skin's own perimeter.
- `manifold3d.Manifold(open sheet)`: `Error.NotManifold`, zero triangles out.

Both ship the right primitive in **2D**, though: `shapely.unary_union` or
`manifold3d.CrossSection` for the union, `manifold3d.triangulate` to get back to triangles (it
takes holes, and wants the exterior wound CCW — feeding it shapely's raw rings, which are not
oriented, silently returns overlapping triangles and *more* area than it was given).

**A prototype pass — group by plane either way up, union in 2D, re-triangulate — measures well:**

| | triangles | area | border edges | T-junctions | non-manifold edges |
|---|---|---|---|---|---|
| Membrane | 153 → 151 | 126.169998 → **125.943129** | 67 → 48 | 19 → 4 | 0 → 2 |
| Cladding | 134 → 111 | 129.883734 → **129.481482** | 54 → 55 | 4 → 4 | 0 → 0 |

It fixes the area exactly, dissolves the retraced edges Duncan found, resolves the bowties
implicitly, and *improves* the T-junction count. It costs two non-manifold edges in the membrane
and it dissolves the facet structure `skin/export.py` regroups into n-gons.

**It does not close the holes** — measured: the outlet comes through untouched, 6 border edges
before and after, because its two triangles span the `x = 8.5` knife and are coplanar with
nothing. A coplanar pass has nothing to say about it. The pass would be a natural *home* for the
gusset step, but it is a separate mechanism.

**Correction to the line above, measured after it was written:** the pass does *not* dissolve the
facet structure `skin/export.py` regroups into n-gons — it improves it. The membrane writes 48
n-gons before and 47 after, and the **two self-crossing ones go to zero**. The residual cost is
smaller and different: two non-manifold edges in the cleaned membrane, at
`(8.072, 5.177, 14.7603)-(8.072, 5.177, 14.737)` and
`(11.3129, 7.548, 13.3312)-(11.108, 7.548, 13.3239)`. The cladding writes 26 either way, none
self-crossing.

### Which 2D engine, and nothing to install (2026-08-21)

Duncan, leaning to emit-then-clean *"based on the idea that a library we already depend on might
offer it for free. If not, open3d, pyvista, or pymeshfix can do it."* Both viable engines are
already here, so nothing needs installing:

| | area | a preserved point moves | collinear vertices |
|---|---|---|---|
| `shapely.unary_union` (GEOS, double) | reference | **0.000 nm** | kept |
| `manifold3d.CrossSection` (Clipper2) | agrees to 0.012 mm² over 1.56 m² | up to **4.7 nm** | dropped |

`manifold3d` is already a **hard** dependency — `substrate.union` is built on it — and 4.7 nm is
far inside `PLANE_TOL` and inside manifold3d's own float32 floor (~500 nm at 15 m out), so it is
not dangerous. But shapely is bit-exact on every point the union keeps, and it **keeps collinear
vertices**, which `skin/export.py` preserves deliberately so that a neighbouring facet cornering
there does not leave a T-junction. So: shapely for the union, `manifold3d.triangulate` to get back
to triangles (already a dependency, and it takes holes). Shapely would join yaml and jsonschema on
the undeclared-dependency list.

**The three named would not do it**, and all three for the same reason — they solve
repair-to-watertight and simplification, not exact coplanar boolean on an open sheet. From their
APIs rather than measured, since none is installed:

- **pymeshfix** (MeshFix) repairs a mesh into a *closed, watertight, manifold* surface. The skins
  are open sheets by design; it would close the membrane into a shell.
- **open3d**'s `remove_duplicated_triangles` is exact-duplicate only — trimesh's equivalent was
  measured a no-op here — and quadric decimation is lossy and moves vertices off their offset
  planes.
- **pyvista/VTK**: `vtkCleanPolyData` merges points and drops degenerates;
  `vtkBooleanOperationPolyDataFilter` needs closed surfaces. `vtkFillHolesFilter` with a size
  threshold is the one thing on the list that speaks to the *holes*, but it fans a triangulation
  across the loop with no regard for the offset planes, which is what two hand-placed triangles
  already do exactly.

**Where it should run, if it is built.** *Not* inside `skin_over`. The union inserts new vertices
where two bands' boundaries cross, so a cleaned mesh no longer satisfies *"every vertex that
survived is exactly where the offset put it"* — the assertion the `base` trim test makes, and the
property that makes `_trim_below` a cut rather than a clamp. Cleaning belongs as an explicit step
over a finished skin, so the raw emission stays inspectable and that invariant keeps meaning what
it says.

### Two source-level fixes tried and rejected, both by measurement

The instinct was to stop `_lap` emitting the bad quad rather than clean it afterwards. Neither
worked, and the numbers are recorded so it is not retried blind:

1. **Refuse a miter that reverses its own band** (keep the rectangle). Membrane bowties 4 → 0, but
   border edges **67 → 79** — every un-mitered band leaves a notch against its neighbour — and the
   double-count was *unchanged* at 230 292 mm², because the rectangle still overlaps.
2. **Drop the swallowed band and miter its neighbours across it.** Bowties 4 → 0, double-count
   226 868 → 179 703 mm², border edges 67 → 75 — and **true area 125.943129 → 125.917865**, so it
   lost 25 264 mm² of real surface. The band is *not* wholly covered by its neighbour after the
   neighbour's own miter moves; the comment claiming it was is what the measurement falsified.
   Disqualifying on its own.

The lesson is the same one both times: **the lap rule legitimately produces overlapping bands**, and
a miter between two of them cannot un-overlap them. Resolving coplanar overlap is a 2D boolean
problem and belongs where a 2D boolean can be run over the whole plane at once, not in a
pairwise joint rule. `skin/offset.py` is unchanged by this section.

## Is the gusset worth its complexity? (2026-08-21)

Duncan: *"Would the gusset make our code more or less complex, more or less maintainable? I am
concerned about introducing more complexity because our student-house skinning module drowned in
it... Another consideration: we may encounter other meshes in the model we might want to clean up."*

**More complex — and the two candidates are complex in different ways, which is the whole of the
answer.** Measured, as prototypes written the way they would land:

| | code lines | where it lives | what else has to know |
|---|---|---|---|
| the coplanar-overlap pass | **64** | its own module, `clean(mesh) -> mesh` | nothing |
| the gusset | **40** | inside `skin_over`, see below | `clearance`, the face-provenance invariant, every future predicate |

The line counts are the *less* interesting half. What separates them is whether the new thing
becomes a **category the rest of the module has to account for**, which is the failure mode that
killed `skin_assembly.py` — 2480 lines of accumulated special cases inside the rule system.

**The gusset's cost is not its 40 lines, it is its detection rule.** Two criteria were written and
both are wrong, which is itself the evidence:

- *every vertex within `2 x distance` of a fold vertex* — fails. The tear runs the full 400 mm of
  the slot **between** two fold vertices 400 mm apart; the `2 x distance` bound is across the tear,
  not along it. It selects nothing.
- *the loop is thin* — discriminates cleanly here (thinnest principal extent 0.000 mm against
  480.251 and 680.970 mm for the two perimeters) but it is an **authored threshold**, and this
  module does not let a derivation rule pick a side with a number.

The one derived criterion that works is *every vertex lies on one of the two offset planes of a
knife plane*, and it does discriminate — true for the tear, false for both perimeters, on all
three components. But it needs `_plane_ids` and `_knives` **on the body**, which exist only inside
`skin_over`. So a correct gusset cannot be a post-hoc mesh utility: it has to run in there, next to
the knife machinery it reads.

And once it does, it introduces a face that is **not the offset of any substrate face**, in a
module where the standing invariant is that every face is an offset plane or a lap off one. The
coupling shows up immediately and is already measured: `clearance` reads **7.8808 → 5.8793 mm**
because a gusset is a chord across a fold, so `build.py`'s verdict has to change with it; and the
`base` trim test's *"every remaining face is still on a plane the offset produced"* stops being
true of the skins in general.

**Against all that: one instance in three substrates.** The other two folds are at `z = 12.35`,
section cuts no skin reaches.

**The cleanup pass has none of that shape.** Mesh in, mesh out; nothing in `skin/offset.py` or the
`RULES` learns it exists; it is testable on a hand-made overlapping pair with no substrate at all.
A *cleanup* is also allowed an authored bound where a *derivation* is not — which is exactly why
"fill a bounded hole" belongs there if it is ever wanted, and not in the rules.

**On other meshes, the reuse argument is thin here, measured.** The only meshes in this repo with
coplanar overlap are the emitted skins. `substrate.union(parts)` — the mesh `skin_over` actually
offsets — comes back **264 triangles, 0 mm² of overlap, 0 degenerate faces**, because manifold3d
produces a clean manifold; and the 36 parts are closed solids that `from_obj` already checks and
`_collapsed` already tidies. (Concatenating the 36 and auditing that reads 262 m² "over", which is
an artefact of separate solids sharing planes, not a defect.) So the reuse case is about the
student-house model rather than anything here — but it costs nothing to keep: write the signature
`clean(mesh) -> mesh`, not `clean_skin(...)`.

**Decided, Duncan 2026-08-21: build the pass, leave the gusset.** If the outlet should close, it
goes in the same module later as a second, opted-into operation with an authored bound, where a
bound is honest. *(It did, on 2026-08-22 — see "The gusset as built", which also corrects the
`clearance` coupling costed here: it is a cost of putting the gusset in `skin_over`, and does not
follow it into `clean`.)* That keeps the one thing the student-house module lost: the rules stay a set of
derivations, and everything that merely tidies geometry sits outside them. The spec for the pass
is at the top of this file.

## What `/code-review high` caught (2026-08-21, third pass)

Four findings, all four real, all four fixed, and **all four latent** — every skin on every
substrate comes back byte-identical afterwards (six MD5s checked). That is the point of running
it: none of these was reachable by the tests or the build, and two were introduced the same day.

- **`skin/offset.py` — the `out` gate short-circuited the fold as well as the run-on.** Mine, from
  the run-on fix earlier in the day: `want = out; if want == 0.0: return False` sits above *both*
  branches of `carry_on`, but only the run-on is priced by `out` — a fold is priced by
  `reach(into)`, which is `drop` for a fold that turns downward. So a skin with `out: 0.0` and a
  non-zero `drop`, which is exactly the **cladding**, could no longer fold a lap round any corner.
  The old gate (`reach(along) == 0.0`) let that through. It also made the code broader than the
  CLAUDE.md sentence describing it. Now the test folds into `whole` and guards the run-on alone.
- **`build.py` — `_wall_planes` / `_next_lift` matched planes by exact equality of a rounded key.**
  `_wall_planes` returned `np.round(rows / TOL) * TOL` and `_next_lift` then compared those rows
  `< TOL`; both sides on the same lattice means the difference is 0 or ≥ TOL, so the tolerance was
  decorative. This is the pattern the Tolerances section forbids and that `_plane_ids` was
  rewritten in this same branch to stop doing — and `_next_lift`'s own docstring already warns
  about it for the `opposed` pairs while `flush` went ahead and did it. Axis-aligned walls hide it,
  because their `d` is a whole number of micrometres; a wall running **diagonally in plan** does
  not, and two triangles of one face landing either side of a boundary would make `_next_lift`
  return nothing and `rise` raise `flat top` on a wall that plainly has a lift above it. Rows are
  now deduplicated on a rounded key and returned **unrounded**: measured on a diagonal fixture,
  `d` was `0.759257` before, exactly on the lattice, and is `0.759256602` now.
- **`skin/offset.py` — the `rounds` net had less headroom than it looked.** A band costs up to
  **four** entries in `tried`, not two: two ends, and a run-on moves the end it lengthens so that
  end is asked again under its new key. Against `rounds * len(segs)` the rig already measured
  2.00, so a substrate whose laps run on at both ends would trip a raise that blames the geometry
  for a correct model. The bound is `rounds * 2 * len(segs)` now, with the ceiling written down.
- **`skin/offset.py` — `drip_at` was silently wrong with no vertical face at the vertex.**
  `np.linalg.lstsq` on a zero-row system returns `[0, 0, 0]` rather than complaining, so the drip
  was rooted on the **substrate** instead of `distance` out from it. Measured on a leaning-face
  fixture with the guard removed: it built, four faces, residual **4.34e-17**, clearance
  **0.0000 mm** against an 8 mm offset, and nothing in the stack said a word. Unreachable through
  either shipped `lap` predicate — both admit only vertical faces and a drip's receiver is one of
  them — but reachable by any predicate that admits a sloped receiver, so it raises now and names
  the vertex.

Two of the four are pinned by new tests (`test_a_drip_with_no_vertical_face_to_miter_onto_raises`,
`test_wall_planes_are_not_snapped_onto_the_tolerance_lattice`), both of which fail against the code
as it stood. The other two are a guard placement and a bound; neither has a fixture that would not
simply be asserting the arithmetic back. 79 tests, ~4.9 s.

The review also cleared five things it had suspected and checked: the ear clipper (fuzzed on 3,843
random simple polygons and 2,000 notched rectilinear loops — no false refusals), `group_cornices`
/ `group_caps` idempotency, `_opening`'s locality on the live bake, the `_room` and `at_arris`
fixes themselves, and the substrate export names against `Path.stem`.

## The pass as built (2026-08-21)

`skin/clean.py`, `clean(mesh) -> mesh`, ~150 lines with its docstrings against the prototype's 64.
It hits the acceptance table on the two columns that were the point — **area is exactly the area
covered**, on both skins, to the µm² — and beats it on the rest:

| membrane, live bake | prototype | as built |
|---|---|---|
| triangles | 153 → 151 | 153 → **147** |
| area | 126.169998 → 125.943129 | **the same** |
| border edges | 67 → 48 | 67 → **45** |
| n-gons written | 48 → 47 | 48 → **43** |
| self-crossing n-gons | 2 → 0 | 4 → **0** |
| non-manifold edges | 0 → **2** | 0 → **0** |

The cladding lands exactly where the prototype did: 134 → 111 triangles, 129.883734 → 129.481482,
54 → 55 border edges, 26 n-gons either way, none self-crossing. (The self-crossing counts differ
before the pass because the two audits count differently — mine flags a loop that merely pinches
itself at a point. Both agree the answer after is zero. And my first count of them was itself
wrong, from a projection basis taken off the first three points of a loop whose first three points
were collinear: use Newell for a loop normal, always.)

**The wart is gone, and its cause was what the spec guessed.** The prototype re-triangulated each
polygon independently and welded afterwards. Triangulating each **whole plane in one
`manifold3d.triangulate` call** — every ring of every region of that plane's union, oriented, in
one list — makes two regions meeting along a line share the vertices they meet at, and the two
non-manifold edges never form. It is also what took the triangle and border counts below the
prototype's.

### Two things the prototype had wrong

**1. Orientation cannot be decided after the union at all. That is a knife.** Grouping planes
either way up is right and necessary — it is the only way a bowtie's two halves land together —
but *what to do about the two ways up* took two goes to get right, and both wrong answers were
silent:

| deciding orientation... | what it costs | found by |
|---|---|---|
| per **plane**, by majority (the prototype) | `substrate.union(parts)` volume **84.293580 → 104.688220 m³** | building it |
| per **region** of the union, by the faces covering that region | two cubes meeting along an edge, volume **2.0 → 4.0** | `/code-review high` |
| per **way up**, unioned separately, `_sheets` deciding which is which | nothing measurable, on any substrate | — |

The middle one is the instructive failure. Two coplanar sheets facing opposite ways are an
ordinary condition — a roof butting a wall on the wall's own plane exposes both sides of the
contact at once, which is the 2026-08-16 fold and the very thing `_knives` exists for — and they
are usually **edge to edge, not apart**. `unary_union` merges two touching polygons into one, so
by the time there is a region to vote on, the boundary between the two sheets is gone and the
smaller side is inverted. Voting per emitted triangle instead does not save it either: the merged
polygon is triangulated across the old boundary, so the answer becomes whatever the triangulator
happened to do. **The ways up have to be separated before the union runs.**

What separates them is **overlap, not adjacency**. `_sheets` connects two faces of a plane when
they intersect with positive *area*, and gives each connected component the direction of the
greater area in it. A bowtie's halves overlap, so they are one sheet and the artefact winding is
outvoted; a knife's two sides touch along a line and stay two sheets. Then each direction is
unioned on its own, and both go into one `triangulate` call so they still share the vertices along
the line they meet at. With that: the substrate union, all 36 parts of the live bake, and two
cubes meeting along an edge all come back with volume, area, watertightness and winding identical
to the bit — and both live skins are unchanged, to the µm², from the region-voting version.

**2. The membrane's own orientation is untouched by any of it**, which is worth stating because
the first check of it said otherwise. Comparing each cleaned face against the nearest original
face by centroid distance reports one flipped face on the membrane; it is an artefact of the
check — the "nearest" face is 45 mm away on a *different* plane. On the cleaned face's own plane,
all 0.22288 m² of original face area faces the same way it does. Compare within the plane, not by
proximity.

### What it proved about `clearance`, and it is not good news

Cleaning the cornices bake's cladding takes its clearance from **63.9999 mm to 84.1503 mm**, which
looks like the known false alarm curing itself. It is not. The sample that read 64.0 mm is a face
**centroid** at `(7.995, 5.1133, 14.361)`, against `Cornice-Headhouse-E` — and that point is still
on the cleaned surface, 0.0000 mm from it. Nothing moved. Re-triangulating simply removed the
triangle whose centroid happened to land there, so the metric stopped looking.

That is a sharper version of the standing open item than the one already recorded. `clearance`
does not only fail to distinguish "stops short of a feature" from "folds through itself" — its
answer **depends on how the surface happens to be triangulated**, which is not a property of the
geometry at all. It is why `build()` measures the raw emission: had it measured the cleaned mesh,
the cornices warning would have gone quiet today and looked like a fix. The Möller-Trumbore
crossing check remains the one that held up.

### What `/code-review high` caught (fourth pass, on the pass itself)

Four findings, all four real, all four fixed. Two would have been wrong answers on other people's
geometry rather than on anything here, which is the point: `clean` is documented as a mesh utility
and NOTES says Duncan expects to use it on the student-house model.

- **The knife again, one case further out** — the region-wide vote above. Reproduced with two unit
  cubes meeting along an edge: watertight in, volume 2.0 → 4.0 out, `overlap_removed` reporting
  0.0 so nothing warned. It also falsified this file's own claim that a test pinned the property:
  the test then standing put a **gap** between its two regions, which is the case `unary_union`
  cannot merge. Four tests now, including the touching one and the two cubes.
- **The weld radius was `PLANE_TOL`, which is the substrate's own lattice.** Every coordinate here
  is snapped to 1 µm, and two neighbouring lattice points at metre scale are 9.9999999925e-07
  apart — inside the radius. A 1 µm-wide coplanar strip therefore welded away silently, and the
  loss was *reported as overlap removed*. `WELD_TOL = 1e-9` now: five orders above the ~1e-14
  noise it actually has to absorb, three below the lattice. The docstring says both bounds.
- **`metadata["folds"]` rode along onto a re-indexed mesh.** The metadata copy already dropped
  `plane_ids` as a per-face cache and then carried a list of **vertex** indices onto a mesh whose
  vertices were rebuilt: on the live bake the raw skin's fold vertex 33 and the cleaned mesh's are
  2.6 m apart, and an index can point past the end. `build.py` prints folds off the raw skin so
  nothing misreported, but `tidy` is what goes into the manifest and the OBJ. Dropped, not
  remapped — nothing beats something wrong.
- **The clean report was gated on triangle count** while its comment claimed it fired whenever the
  clean did anything, so a clean that dissolved real overlap without changing the count would have
  written a different mesh than every printed number was measured on, silently. Gated on both now.

The review also confirmed, independently, that the cleaned area equals the per-plane union area to
~1e-14 m² on all four substrate/skin combinations, that no face comes out flipped, and that every
number in the tables above reproduces.

### Collinear vertices, and the second operation (2026-08-21)

Duncan, same reading: *"There are also colinear edges in both skins. Does clean weld colinear
edges?"* It did not, deliberately — shapely keeps collinear vertices through the union and
`skin/export.py` keeps them on purpose, because dropping one that a neighbouring facet corners on
leaves a T-junction. Measured on the cleaned skins: 35 collinear corners in the membrane and 30 in
the cladding, of which only 6 and 10 were used by no other facet.

**"Used by no other facet" turned out to be the wrong test, and too timid.** The right one is *no
ring **turns** at this vertex* — a vertex may sit on two rings and be straight through on both, in
which case dropping it from both changes nothing. Asked that way it is 19 and 20 vertices rather
than 6 and 10, and it is asked **once over every ring of the mesh**, never per plane. Added on
Duncan's word as `clean(mesh, dissolve=True)`, a second opted-in operation, with `build()` opting
in:

| live bake | triangles | vertices | border edges | T-junctions | collinear corners |
|---|---|---|---|---|---|
| Membrane, cleaned | 147 | 94 | 45 | 3 | 35 |
| ...and thinned | **115** | **75** | **35** | **0** | **3** |
| Cladding, cleaned | 111 | 81 | 55 | 4 | 30 |
| ...and thinned | **81** | **61** | **45** | **2** | **0** |

T-junctions *fall* rather than rise, which is the point: a vertex no ring turns at is exactly a
T-junction anchor. The three left in the membrane are vertices some other facet genuinely corners
at, and are correctly kept. Across all three substrates and both skins the area still equals the
covered area to **0.000000 mm²**, nothing is non-manifold, no vertex sits more than 2.5 nm off a
plane the offset produced, clearance is unchanged, and it is idempotent. `STRAIGHT_TOL` is 1e-9 m:
a union-inserted crossing lies on its line to double precision, five orders below that, while the
shallowest real corner in a building is millimetres off — there is nothing in between for the
number to get wrong.

### Where it sits, and what it costs

- **`skin/clean.py` is the only module that imports shapely**, and `clean` is deliberately **not**
  re-exported from `skin/__init__.py`: `import skin` must not require it. `build.py` imports
  `skin.clean.clean` directly. Same containment as yaml and jsonschema in `skin/parameters.py`,
  and the same reason — the student-house seam. shapely does join the undeclared-dependency list.
- **`build()` measures raw and writes cleaned**, chosen by Duncan from three. Every printed
  number is a property of the offset and none of them moved on any of the three substrates; a
  single extra line reports what the clean removed. `build/` and therefore `display.reload()` get
  the cleaned mesh.
- **It is idempotent in what it produces**, and it does not mutate its input. A second pass over
  either live skin finds 0.000 mm² left to remove and returns the same triangle count, the same
  vertex count, the same vertex *set* and the same area to twelve decimals — but **not** the same
  index order, because the plane groups are walked in face order and that order has changed. Do
  not write a test asserting `clean(clean(m))` is `clean(m)` array-for-array; assert on the mesh.
- **A vertex the union preserved comes back bit-identical** — the 2D point is mapped back to the
  vertex it was projected from rather than unprojected — and every vertex of a cleaned skin lies
  within 4.2e-7 m of a plane the original had, which is manifold3d's own float32 floor and not
  drift introduced here.
- **It cannot close a hole, still.** The outlet comes through untouched, exactly as measured
  before it was built.

## What the clean made visible at the scupper cornice (2026-08-21)

Duncan, off the freshly cleaned bake: *"There is a new defect in the cladding. V8 is too low. E10
and E9 should be one horizontal edge."*

**Not a new defect, and not the clean's.** In that plane the covered area is **bit-identical**
before and after — `symmetric_difference(raw, cleaned).area == 0.0` on the whole of `x = 7.995`.
What changed is only what Blender **draws**: the notch's bottom and right edges were being drawn
on top of a panel that already covered the notch's lower right, and the clean stopped drawing the
double cover. The wireframe now tells the truth about a surface that has been that shape all along.

| the notch's outline, plane `x = 7.995` | |
|---|---|
| drawn before | `(4.6, 14.34)–(5.37, 14.34)` and `(5.37, 14.34)–(5.37, 14.58)` |
| drawn now | `(4.6, 14.34)–(4.7909, 14.34)`, then a **rake** to `(5.37, 14.434)`, then up to `(5.37, 14.58)` |

**Duncan's expectation is right, and the height is 14.340.** `Cornice-Headhouse-E` is
y 4.685…5.285, z 14.425…14.495, so the cladding's 85 mm-clear notch around it is exactly
y 4.60…5.37, z **14.34**…14.58 — symmetric about the outlet's centre line, bottom edge horizontal.
The 14.4339837 he read off the stray vertex is not a height in the model at all: it is where the
offending edge crosses `y = 5.37`.

**The cause, which is worth having, because this file had the wrong mechanism for it.** The
bowties were explained here as a miter running out past the rim of a band that lies wholly inside
its neighbour. That is the *membrane's* mechanism. The cladding's 200 655 mm² bowtie on
`Headhouse-E`'s facade — the big one already named above — is a different one:

- The union punches the cornice's contact out of the parapet's facade face, leaving a rectangle
  with a rectangular hole, and manifold3d tiles it with a fan from `(2.85, 14.025)`. One of those
  triangles is `(2.85, 14.025) — (5.285, 14.425) — (7.12, 14.718)`.
- The hole's corner `(5.285, 14.425)` sits **4.7 mm** from the diagonal between the other two.
- The offset moves that corner 85 mm outward, to `(5.37, 14.34)` — clean across the diagonal. The
  triangle inverts, and the inverted triangle is precisely the sliver that eats the bottom right
  of the notch.

So `planar_offset` keeps the union's triangulation while moving its vertices, and **a vertex that
starts within the offset distance of a diagonal joining two of its neighbours will cross it**. The
face outline is offset correctly; the tiling of it is not. That is a third member of the family
with "the lap emits whole quads" and "the lap cannot clip": the raw emission covers area it should
not, and `clean` dissolves the double count without touching the cause. Fixing it means
re-triangulating a face whose tiling the offset inverted — detectable exactly, with no threshold:
a face whose normal ends up opposed to its own plane's. Four such faces in the membrane and two in
the cladding on the live bake; `skin/clean.py`'s `_sheets` already finds them, but it is the wrong
place to fix them, because by then the substrate face they came from is gone.

**Do not "fix" this in `clean`.** Its job is what the plane is covered by; it cannot know that a
particular covered sliver was never wanted. The notch will come back symmetric when the offset
stops inverting triangles, and not before.

## The notch is fixed at source, and `clearance` was right all along (2026-08-21)

Duncan, on the diagnosis above: *"Fix it."*

`skin/offset.py` gains `_tiling`, run on the kept faces before any lap is placed. A face whose
offset triangle ends up pointing against the body's own normal has been turned **inside out** by
the solve; the patch it belongs to — coplanar faces joined edge to edge — is tiled again from its
own boundary loops, which an inversion does not move. Detection is exact and wants no threshold.
It applies to a patch that inverted and nowhere else, and the rig and the walls-and-caps bake come
out **triangle for triangle identical**, which is the property to keep.

- `_rings` walks the patch's boundary into loops and **raises** on a pinch rather than guessing
  which way to turn.
- `_retiled` takes the widest loop as the outline and the rest as holes, and checks the tiled area
  against the area those loops enclose — the same check `substrate`'s ear clipper makes, because
  an outline that crossed itself would otherwise tile to well-formed triangles covering the wrong
  region and nothing else would notice. The check is **relative**, not against `PLANE_TOL`: it
  sets a sum of triangle areas against a shoelace, so what noise there is scales with the patch.
  Measured on the two real patches the slack is 1.9e-16 and 2.5e-16 against a 1e-9 bound, and the
  defect it guards against is 7e-3 of the patch — seven orders of headroom either way.
- No shapely: signed areas are a shoelace and the tiling is `manifold3d.triangulate`, so
  `skin/offset.py` keeps the dependency it had.

**What it fixes, measured on the live bake.** The notch round the scupper cornice is symmetric
again — outline `(4.6, 14.58) (4.6, 14.34) (5.37, 14.34) (5.37, 14.58)`, one horizontal edge at
z = 14.340, exactly as Duncan called it. The stray vertices at `(4.7909, 14.34)` and
`(5.37, 14.433984)` are gone.

| cladding, live bake | before | after |
|---|---|---|
| triangles emitted | 134 | **122** |
| summed area | 129.883734 | **129.454269** |
| area actually covered | 129.481482 | **129.454269** — the two are now the same number |
| coplanar overlap for `clean` to dissolve | 402 253 mm² | **0** |
| inverted faces | 2 | **0** |
| clearance | 63.9999 mm + WARNING | **84.1503 mm**, no warning |
| skin separation | 25.654 mm | **76.230 mm** |

27 213 mm² of surface that was never wanted is gone with it. The membrane is untouched — its four
bowties come from the lap miter, a different mechanism, and `clean` still dissolves them.

### The correction: the cornices warning was never a false alarm

This file has said for weeks that the cladding's `WARNING: 21.000 mm inside the requested offset`
on the cornice bakes was **wrong** — that four independent checks (crossings both ways,
self-crossings, face centres inside parts, skin edges against part surfaces) all came back clean
and the cladding stopped correctly on its mitre. Every one of those measurements was accurate.
The conclusion drawn from them was not.

The sample reading 63.9999 mm was the centroid of the **inverted triangle**, at
`(7.995, 5.1133, 14.361)`, against `Cornice-Headhouse-E`. That triangle was real surface, sitting
inside the 85 mm zone the cladding is supposed to keep clear round the cornice. `clearance` was
right; only the word *self-intersecting* in the message was wrong, which is exactly why the four
checks — every one of them a test for **self-intersection** — came back clean. Four right answers
to the wrong question outvoted one right answer to the right one.

With the tiling fixed the reading is 84.1503 mm against `Roof_Unit8_InsulationTaper.6`, inside the
1.683 mm the sloped planes absorbed, and the bake prints no warning at all. So the standing item
below — *demote `clearance` to a number rather than a verdict* — should **not** be taken on the
strength of that warning: it caught a defect nothing else in the stack could see. The real
complaint against it stands and is narrower: its answer moves when the triangulation moves.

## The gusset as built (2026-08-22)

Duncan, asked the standing question: *"1. Yes, close it in clean. 2. I do not fully understand the
implications of each option."*

**On (2), the answer turned out to be that there were no implications to weigh — the two questions
are not coupled, and the 2026-08-21 costing above is what made them look coupled.** That costing
measured the gusset *inside `skin_over`*, where it is a face the offset produced, and there
`clearance` reads 7.8808 → 5.8793 mm and `build.py` prints a self-intersection warning on a skin
with nothing buried in anything. In `skin/clean.py` it is not: `build()` **measures the raw
emission and writes the cleaned mesh**, so the printed verdict is taken on `skin_over`'s output
before any gusset exists. Reproduced, on the live bake:

| | membrane clearance |
|---|---|
| raw emission — **what `build.py` prints** | 7.8808 mm |
| cleaned | 7.8808 mm |
| cleaned and gusseted | 5.8793 mm |

So the printed line is byte-identical before and after, and *"demote `clearance` to a number
rather than a verdict"* stays open on its own merits, blocking nothing. The 5.8793 mm is real and
is the honest reading of the written mesh — a gusset **is** a chord across a fold — which is why
the build says out loud that it placed one. It is the same discipline as printing folds: a surface
the module invented must not arrive silently.

**What it does.** Third opted-in operation, `clean(mesh, dissolve=..., close=m)`, zero off. On all
three bakes:

| | triangles | border edges | n-gons written | area |
|---|---|---|---|---|
| membrane, `close: 0.0` | 115 | 35 | 43 | 125.943129 m² |
| membrane, `close: 0.025` | 117 | **29** | 45 | 125.946588 m² |

2 tears closed, 3459.06 mm² — 2 × 1729.5288 mm², the two triangles this file bounded on
2026-08-21, to the last digit quoted then. Winding consistent, no non-manifold edge, no
T-junction, no vertex invented. The cladding is byte-identical, and stays so even when handed the
membrane's own bound. The rig has no tear and is untouched.

### Why one tear reports as two

The tear **pinches to a point**: two triangles meeting at one vertex of degree four, at
`(8.492, 4.985, 14.503)`. It is one border component of 5 vertices and 6 half-edges, and no ring
walk can turn at that vertex without guessing which way to go — the same condition `offset._rings`
refuses outright. So nothing walks. The component is read as the planar graph it is and handed to
`shapely.polygonize`, which returns both regions. `tears_closed` counts regions filled.

### The three conditions, and which one is doing the work

The 2026-08-21 costing rejected two detection criteria and found only one that was derived — *every
vertex lies on one of the two offset planes of a knife plane* — which needs `_plane_ids` and
`_knives` and therefore drags the gusset into `skin_over`. Landing it in `clean` instead means the
authored bound the costing said a cleanup is entitled to. But an authored width **alone** is not
safe, and the third condition is what makes it so:

- **flat**, to `PLANE_TOL`. Measured across both skins on all three substrates: the tear is flat
  to **1.5e-15 m**; the next flattest border loop stands **94.14 mm** off its own best-fit plane.
  Thirteen orders of margin, because a skin's perimeter wraps a building and a tear does not.
- **narrow**, to the authored `close`. The tear is **18.016 mm** across; the narrowest loop that
  must stay open is **248.268 mm**. Authored at **0.025** — 39% above the one and an order below
  the other. Deliberately **not** derived as `2 x distance`: the tear is 16 mm across in plan but
  18.016 mm along its own plane, because the roof it opens on falls, so the obvious derivation
  misses the very tear it was reasoned from. That is worth remembering as a small lesson in its
  own right — the number that *sounds* derived was measured and found wrong.
- **not already covered by the mesh**, which is derived and is the load-bearing safety condition.
  Without it the worst case is silent and severe, and it is not exotic: the perimeter of *any*
  flat sheet narrower than `close` is a flat narrow loop, so a 20 mm cover flashing would have its
  own outline "closed" and come back **doubled** — two coincident surfaces, reported as a tidy-up.
  A tear is by construction where the surface is **missing**. A test pins it.

Orientation is read off the mesh, not guessed: the border is taken as **half-edges in their own
faces' directions**, and a gusset must traverse each shared edge the other way. A normal-based
guess gets one of the two ways up right by luck, so the test runs the fixture both ways up.

The order is union → dissolve → close, each reading the outline the one before left. A gusset is
fitted to the border of the *finished* surface, and a border edge a bowtie left is an artefact
rather than a tear.

### What it cost

Ten tests, eight of them hand-made with no substrate behind them, two on the bakes because the
pinch is produced by the rules and not by hand. 110 tests, ~6.6 s. `skin/offset.py` and `RULES`
are unchanged and still do not know the module exists. `close` joins the parameter file under
STRICT-COMPLETE — required on every skin, in the schema, ignored by `check_seeds` for the same
reason `base` is: it bounds a cleanup, not a surface.

## The trim in plan, and the reveal it was blocked on (2026-08-22)

Duncan, asked whether the cheeks should be clad at all given that the scupper **floor** is
deliberately excluded on the reasoning *"a rainscreen stops at the opening; the membrane lines
it"*: **"Cheeks are clad."** So the reveal is lined and stops at the sill, the way a rainscreen
returns into a window opening, and the floor stays out. The two are now a deliberate pair rather
than an unexamined inconsistency.

### Re-measured first, because everything underneath had moved

The blocker was recorded on 2026-08-21, before `_tiling`, `clean` and the gusset. Re-measured on
the current stack it was **unchanged**: adding `| (cheeks & faces.of_role(substrate.WALL))` to
`cladding_faces` took the live bake's cladding from `clearance 84.1503 → 3.6593 mm` and the skin
separation from `76.230 → 4.337 mm`.

It also turned out to be **one end, not two**, which the old note did not record.
`Parapet-Headhouse-E` spans `x 8.080…8.500`, and its **west** face is already clad — 20 triangles
at `x = 7.995`, `y 2.345…7.625`, spanning the whole slot — so the cheek panel's west arris miters
against a *covered* neighbour and was always right. Its **east** face is clad only from
`z = 14.707` up, the coping's return lip; below that it is bare, and the panel ran to `x = 8.585`
down to `z = 14.5036`, 85 mm past the wall face and into `Roof_Headhouse_InsulationTaper`.

### Three attempts, and what each one taught

The rule went through three shapes before it was right, and the two rejected ones are the useful
part of the record.

1. **"Cut at the plane of an uncovered, non-receiving, convex neighbour."** Does not fire at all.
   The parapet's east face is a lap **receiver** — it takes the coping's drip — so excluding
   receivers excludes the very arris in question. The lesson: *a receiving face is one face, and a
   lap onto it is one band off one arris*. `_lap` now reports `sprung`, the arrises it actually
   placed a seam on, and the test is per arris.
2. **"Cut at every uncovered, non-sprung, convex neighbour."** Fires everywhere, and **reverses a
   documented invariant** — *"vertices on the edge of a selection sit on the miter they would have
   had if the neighbours were skinned too"*. Three existing tests assert that behaviour, and a
   plate skinned on its top alone lost the `distance` it reaches past its own sides:
   `17.48 → 15.84 m²`. Rejected on the spot. A rule that makes three tests fail because it changed
   what they were written to pin is not a fix, it is a different design.
3. **"...and the miter lands inside the substrate", tested with `contains`.** Also does not fire.
   The reveal's miter is not *inside* the roof — it hangs **3.66 mm above** it. Measured, not
   assumed, and it is why the shipped test is a distance and not a predicate.

### What it is

**At a convex arris to a face the skin neither covers nor laps onto, a miter that lands closer to
the substrate than `distance` is cut back.** Being `distance` off the substrate is the whole
definition of this surface, so a point of it that is nearer has stopped being an offset of
anything — which is a fact about the geometry rather than a judgement about intent, and it is what
keeps the rule a repair to the invariant rather than a reversal of it. The bound is `distance`
itself less the `slope_deviation` the solve already declares, so nothing is authored.

**It is cut twice, and it needs both.** Once to the plane of the face it mitered against, and once
clear of the **offset** of whatever it broke against — always a third body, because the two faces
a miter is made of are exactly `distance` away by construction. With only the first cut the reveal
came back at **41.8148 mm**, because the cut inherited a bottom edge the bad miter had raked. Both
together give the reveal lining it should be:

| | cladding clearance | separation | cheek panel |
|---|---|---|---|
| cheeks not clad | 84.1503 mm | 76.230 mm | — |
| clad, no trim | 3.6593 mm | 4.337 mm | `x 7.995…8.585`, `z 14.5036…14.718` |
| clad, first cut only | 41.8148 mm | 33.860 mm | `x 7.995…8.500`, `z 14.5418…14.718` |
| **clad, both cuts** | **84.1503 mm** | **76.230 mm** | `x 7.995…8.500`, `z 14.585…14.718` |

Both cheeks, symmetrical. The bake reads exactly what it read before the cheeks were covered at
all, and no bake prints a warning.

### What it did not move

Every clearance and separation on all four substrates is unchanged, to the last digit, with the
trim in and the cheeks out — and with the cheeks in, only the cladding's face and border counts
move. The rig is byte-identical. That is the property the second attempt failed and this one has:
**the only thing cut on any substrate here is the reveal.**

### Known conservativeness

A miter vertex belongs to **two** arrises, so a break at one corner cuts both of them along their
whole length, taking free edge that was never wrong. On a box with a close neighbour the `-y` and
`+y` edges come back flush with the wall's ends though only their `+x` corners were ever broken.
It errs toward not leaving surface that is not an offset of anything, which is the safe direction,
and it costs nothing on any substrate here. A test pins it on a box, where it is easy to pose and
easy to see; do not "fix" it by loosening the trim without a case that needs it.

### What it cost

`_cut` is now the one cutting primitive, a half-space with its crossings cached per edge, and
`_trim_below` is expressed as `-z <= -base` through it — every bake byte-identical across that
refactor. `_tiling` returns a plane id per triangle and `_lap` returns `sprung`; both were
single-caller functions, so neither signature change reaches beyond `skin_over`. Five new tests,
four of them synthetic. 114 tests, ~8.9 s.

## The cheek lining is wrong, and what it is (2026-08-22)

Duncan, reading `build/Cladding.obj` back in Blender on the live bake, on the **north** cheek:

> *"The geometry is incorrect. At the north cheek for example, V52 should be at V49, V5 should be
> at V4. V62 (on the skirt) should also be on the cheek plane (y=4.87). E72 should be at the
> height of V6 and extend to x=8.585."*

Vertex numbers are the exported OBJ's own order, which is what Blender shows: `skin/export.py`
writes every mesh vertex as a `v` line before any face, so Blender's index *is* the index into
`mesh.vertices`. All four corrections are consistent under that reading and they describe one
shape, which is how the mapping was confirmed.

### The four, in coordinates

| | is | should be | what it is |
|---|---|---|---|
| V5 | `(7.995, 4.87, 14.718)` | V4 `(7.995, 4.87, 14.84009)` | lining's top-west corner |
| V52 | `(8.500, 4.87, 14.718)` | V49 `(8.585, 4.87, 14.819018)` | lining's top-east corner |
| E72 | see below | `z 14.580` (V6's height), out to `x = 8.585` | lining's bottom edge |
| V62 | `(8.585, 4.785, 14.707)` | **stays** — see the revision below | skirt's outer edge, at the slot |

**On E72, one loose end, recorded rather than smoothed over.** Reconstructing Blender's edge
numbering the documented way — first appearance while walking each face's loop in order, see the
`expressing-geometry-requirements` memory — makes **E72** the lining's *west* edge, `V5–V51`,
vertical at `x = 7.995` from `z 14.718` to `14.585034`. The **bottom** edge, `V51–V53` at
`z = 14.585034` running `x 7.995…8.500`, comes out as **E71**. Duncan's description — *"at the
height of V6 and extend to x=8.585"* — can only be the bottom edge, so either the reconstruction
is one step out on this mesh or the number was. It changes nothing: the target quad is pinned
by V4, V49 and V6 independently. Worth re-deriving on the next mesh before trusting an edge
number to the digit.

So the lining wants to be the full reveal — a trapezoid from the facade's offset plane out to the
east return's, and from the sill's offset up to the coping:

```
(7.995, 4.87, 14.84009) ── (8.585, 4.87, 14.819018)      the coping, sloped
(7.995, 4.87, 14.580)   ── (8.585, 4.87, 14.580)         the sill's offset, flat
```

with the skirt's outer edge run out to `y = 4.87` to close the corner against it. Built today it
is `x 7.995…8.500`, `z 14.585…14.718`.

### Three causes, and they are independent

**1. The top stops at the parapet, not the coping** (V5→V4, V52→V49). The cap over this parapet
is authored as **two bodies** — `CapPlate-Headhouse-E` (`y 2.430…4.785`) and `CapPlate-Headhouse-E2`
(`y 5.185…7.540`) — split by the slot. `build._opening` reads cheeks **per body**, deliberately and
for the reasons in its own docstring, and pairs vertical coplanar regions of one body that look
*at* each other. Neither plate contains a pair: each has exactly one reveal. So union faces **198**
and **199**, at `y = 4.785`, `z 14.718…14.752`, come back `cheek False` / `kept False`, and the
lining stops at `z = 14.718` where the parapet's own cheek ends.

Note what this is *not*: it is not the role filter and not `~floor`. Those faces read
`role WALL True`. The per-body pairing simply cannot see a reveal whose opposite number is in
another body — and per element is already ruled out in that docstring for two other reasons, so
this wants thought rather than a flag flip.

**2. The bottom edge is kinked and dives** (E72). Two substrate vertices, both at the scupper
knife, and neither is a tolerance question:

- **v66** `(8.500, 4.785, 14.495)` → offsets to **`(8.415, 4.870, 14.580)`**. Its planes are the
  sill (`z = 14.495`), the cheek (`y = 4.785`), and the **roof taper's west end face**, normal
  `−x` at `x = 8.500`. That third plane's offset is `x = 8.415`, so the corner moves 85 mm the
  wrong way and the bottom edge kinks back at `x = 8.415`. The parapet's east face — normal `+x`,
  same `x = 8.500`, offset `8.585` — does not touch this vertex at all.
- **v67** `(8.500, 4.785, 14.503618)` → offsets to `(8.585, 4.870, 14.503618)`, **z unchanged**.
  This is the long-documented **fold vertex 67** (see *"The hole at the scupper outlet"*): the two
  opposed planes at `x = 8.500` are a knife, `_reconcile` drops one, and the ridge leaves z where
  it started. That is what rakes the bottom edge down 76 mm over the last 170 mm of its run.

Both are the knife the scupper has always had. **This, and not the length of the miter, is where
the `clearance 3.6593 mm` reading came from.**

**3. The skirt ends in a slant** (V62) — **withdrawn and replaced, 2026-08-22, and this is the
live version.** Duncan, having mocked the scupper up in SketchUp and posted two views of it:
*"I want to revise my corrections. V62 should remain where it is. The skirt should turn downwards
on each side of the scupper."*

So the rim is right where it is and there is no missing miter. Measured off the built
`build/Cladding.obj`, the notch the skirt leaves in the exterior plane `x = 8.585` is 400 mm wide
at the rim (V63/V64, `y 4.785…5.185` at `z = 14.707` — the true slot) and 230 mm at the root
(V50/V51, `y 4.870…5.100` at `z = 14.819` — inset by the offset), joined by that diagonal. The rim
width was always right. What is missing is the surface closing the 85 mm between the two: on each
side of the slot the skirt **turns down** and runs to the **sill's offset**, and it does **not**
return across the bottom (Duncan, asked both).

**It is not the fold `_lap` already places, and that is the whole difficulty.** A fold turns onto
the *departing* face — here the cheek, plane `y = 4.870`. This return stays in the skirt's **own**
plane, `x = 8.585`, and runs down it. None of `carry_on`'s three answers at a free end covers
that: the same plane carries on, another face meets it at an arris, or nothing.

What is **not** the blocker, so nobody needs to raise it: `out: 0.0`. That gate is on the run-on
alone and deliberately so — a fold is priced by `reach(into)` and bills `drop` when it turns
downward, precisely so the cladding is not denied every corner it turns.

The derivation to try first is that **a lap band follows the boundary of the face it laps onto**.
A drip is the band inside the top edge of the wall it hangs on; where that boundary turns — down
the side of an opening — the band turns with it. That is one rule covering the run-on, the fold
and this, rather than a fourth case bolted onto the stop condition. It is a guess at the shape,
not a measured result; nothing has been built.

### What this says about `_trim_beside`

*(Acted on 2026-08-25: it is backed out. The reasoning below is why, kept as written.)*

**It is treating the symptom.** The trim cut the lining back to `x = 8.500` and lifted it to
`z = 14.585` to get the offset property back, and that is exactly what Duncan says is wrong: he
wants the miter **kept**, out to `x = 8.585`, with the bottom edge fixed instead. Fix cause 2 and
the miter needs no trimming.

That does not automatically condemn the mechanism — it is derived, tested, and it moves nothing
anywhere else on any substrate — but its only live case is one it gets wrong. **The default
assumption for the next session should be that it comes out**, and that the argument for keeping
it has to be made fresh from some other case.

### One measurement to have before deciding

Duncan's target quad, sampled against the substrate:

| corner | to the substrate |
|---|---|
| `(7.995, 4.87, 14.84009)` | 149.0296 mm |
| `(8.585, 4.87, 14.819018)` | 145.5229 mm |
| `(8.585, 4.87, 14.580)` | **79.9702 mm** |
| `(7.995, 4.87, 14.580)` | 84.9999 mm |

So **the geometry Duncan wants reads 79.97 mm against an 85 mm offset** and `build.py` will print
`WARNING: … inside the requested offset` on the cornice bakes. It is inherent, not a defect: the
reveal's mouth sits directly on the headhouse roof, so no correct panel can stand 85 mm off
everything there. It is the documented `clearance` exception — *"a skin that deliberately stops
short of something standing proud"* — arriving for real. But it does end the property recorded
yesterday that **no bake prints a warning any more**, and that is worth saying out loud rather
than discovering later. It also strengthens the standing item below about demoting `clearance`
from a verdict to a number.

### Order to take them in

**Revised 2026-08-22 after the turn-down replaced 3, and nothing here is started.** Duncan is out
of weekly budget and expects to pick this up Monday night.

1. ~~**Back `_trim_beside` out**~~ — **done 2026-08-25**, see *"What landed on 2026-08-25"*.
   Reverted as `f0d535b`, keeping the cheek line in
   `cladding_faces` — that commit is on its own for exactly this. The bake goes back to reading
   `clearance 3.6593 mm` and warning, which is the honest reading of a real defect. Note that the
   geometry Duncan wants reads 79.97 mm against an 85 mm offset **anyway**, inherently, because
   the reveal's mouth sits on the headhouse roof — so the warning is arriving either way, and
   "no bake warns" is over. That forces the standing `clearance` item below: demote it to a
   printed number and promote the Möller-Trumbore check to the verdict. **Duncan's call**, and
   worth having answered before the fixes land rather than after.
2. **Cause 1**, the lining stopping at the parapet. Contained. Do not relax `_opening`'s per-body
   pairing — its docstring rules per-element out for two other reasons that both still hold. The
   derivation to try is to *grow* the cheek set: a coplanar vertical region of another body that
   overlaps a known cheek in plan and faces the same way is also a cheek, which is what "the slot
   cuts through the cap plate too" means geometrically.
3. **Cause 2**, the knife. `_reconcile` and the most delicate thing in the module, and the one
   that decides whether `_trim_beside` ever comes back. Be precise about which vertex is which:
   only **v67** is `_reconcile`'s doing. **v66** is not a contradiction at all — its planes are
   not opposed and the parapet's east face does not touch it. It is the "solved over the whole
   body" invariant working as written, with the roof taper's end plane pulling the vertex 85 mm
   *inward*. The question v66 poses is whether an uncovered face's plane should still constrain a
   vertex when it pulls it inside `distance` — the same test `_trim_beside` makes, applied at
   solve time to a plane instead of after the fact to a triangle. Write it as a candidate and
   measure it; do not design it further on paper.
4. **The turn-down.** Last, and now more firmly so: it springs off the mouth arris and its outer
   edge is `x = 8.585`, which is the coordinate cause 2 gets wrong today. Set it out before the
   knife is fixed and it inherits the same raked bottom. It is neutral for `_trim_beside` either
   way — a lap lies on the face beyond the arris it springs from, so the return would never have
   been cut by it.

## Open items

- ~~**The scupper mouth and the cornice ends are bare.**~~ Closed 2026-08-21 by the extended
  cornice, which removed the knife rather than weakening `_reconcile` — see that section. The
  `_reconcile` narrowing described here is **unnecessary rather than untaken** and should stay
  untaken.
- **The south-junction sliver**, 205 x 7.3 mm, left by the continuation. See above; it needs the
  lap to clip against its neighbour rather than emit whole quads.
- ~~**Coplanar laps overlap, and it skews the area**~~ — membrane 0.180%, cladding 0.311%, plus
  six bowtie quads. **Decided 2026-08-21: emit then clean.** `skin/clean.py` is specified at the
  top of this file. **Built 2026-08-21** — see *"The pass as built"*: area is now exactly the
  area covered, on both skins. The two source-level alternatives are measured and ruled out; the
  *cause* — the lap emitting whole quads that overlap — stays open above.
- ~~**The membrane has one hole: the scupper outlet**~~ — **closed 2026-08-22** by
  `clean(mesh, close=m)`, on Duncan's decision. See *"The gusset as built"*. Every other border
  component in either skin is a legitimate free edge — the skin's own perimeter — and three
  conditions keep them that way.
- **`clearance` cannot tell "stops short of a feature" from "folds through itself".** *(Read the
  correction in "The notch is fixed at source" first: the cornices warning this item was built on
  was **right**, and the cladding really did have surface 21 mm inside its offset. What survives
  is the triangulation-dependence, not the cry of wolf.)* The cornices
  bake makes the cladding read 63.9999 mm against an 85 mm offset and print
  `WARNING: … self-intersecting`, and it is wrong — four independent checks (crossings both ways,
  self-crossings, face centres inside parts, skin edges against part surfaces) all come back
  clean, and the cladding stops exactly on its mitre against the cornice underside. The metric
  samples vertices and centroids against every part, so any skin that deliberately terminates
  beside something standing proud of the wall reads low. **Worse than that, measured 2026-08-21
  while building `clean`:** the number depends on how the surface is triangulated. Cleaning the
  cladding reads 63.9999 → 84.1503 mm with nothing moved — the offending centroid's triangle was
  merely re-triangulated away, and the point is still on the surface at 64 mm. A verdict that a
  re-triangulation can change is not a verdict about the geometry. CLAUDE.md still says a clearance below
  `distance − slope_deviation` means something broke; that is now false in the presence of a
  cornice, and a warning that cries wolf every build is worse than none. The Möller-Trumbore pass
  is the check that actually held up, which strengthens the standing "promote it into
  `skin/measure.py` as `intersects(a, b)`" item below — it should probably become the check
  `build.py` prints, with `clearance` demoted to a number rather than a verdict. Not fixed:
  changing what the build asserts is Duncan's call.


- ~~**The membrane leaks at V11: an in-line butt has no wrap.**~~ Closed 2026-08-20 by the lap
  rule — see above. The drip runs on past the butt to x = 8.277 and the upstand folds round the
  corner onto `Headhouse-N`'s north face, spanning z 13.1189…13.3239, which is the panel Duncan
  specified. Of the four candidates put to him, the one that landed is the first: dress onto every
  exposed face at the termination, general, covering both junction types.
- ~~**The membrane should turn up at the scupper cheeks.**~~ Closed 2026-08-20 by the same rule.
  Both cheeks are covered from x 8.072 to 8.508 and z 14.503 to 14.760 — up from the sill, down
  from the cap plate's reveal, and sideways off the parapet's inner face. The 2026-08-16 note
  predicting the turn-up would make the two `x = 8.508` edges vertical is superseded: the fold
  vertices there are all displaced 8–14 mm, which is a corner miter and not a defect.
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
  a bare end is not a datum the model shares, so there is nothing in plan to author.
  **Still open after `_trim_beside` (2026-08-22), and deliberately so.** That trim fires only
  where a miter lands *closer to the substrate than the offset*, and these hang in free air —
  they break nothing, they are just longer than a builder would want. Cutting them is the
  wider rule the second attempt was, and it reverses the miter invariant; it wants its own
  decision and its own measured pass, not a widening of this one.
- ~~**`_fan_is_valid` treats a redundant collinear vertex as concavity, but only next to
  vertex 0.**~~ Settled 2026-08-19 by ear clipping, which accepts both readings faithfully —
  the corner is an ordinary triangle vertex where an ear is available there and is dropped
  contributing nothing where one is not. `_fan_is_valid` itself is unchanged; it is now a
  *routing* test ("can the fan have this one?") rather than a refusal.
- ~~**Three of the four headhouse OBJ exports are committed and nothing reads them.**~~ Deleted
  2026-08-19 on Duncan's say-so: `headhouse-parapets-clt-insulation{,-no-scupper}.obj` and
  `headhouse-walls-parapets-insulation.obj`, superseded by
  `headhouse-walls-parapets-caps-clt-insulation.obj`, which `tests/test_import.py` does read.
  They live in commit `5d77c9a` if one is ever wanted back. **Every figure in this file quoted
  against those three is now a note rather than a check** — the sections dated 2026-08-15 and
  2026-08-16 in particular. The one survivor of them in the tree is the detached-sliver wedge,
  transcribed as literals in `tests/test_import.py`.
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
