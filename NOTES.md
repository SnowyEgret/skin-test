# skin-test — state of play

Offsetting a **substrate** (an assembly of solid parts) outward by a fixed distance to
produce **skins**: open surfaces that cover a chosen subset of faces.

Last worked: 2026-08-28.

`CLAUDE.md` has the commands, the architecture and its invariants, and the tolerance
rationale. This file is the running log: what the geometry currently is, what was tried
and rejected, and what is still open.

## Start here (picking up after 2026-08-28)

### Where to pick up

**Current state: the building skins in six, with its floor slabs, warning-free.** Build it with
`python3 build.py whole-building-walls-parapets-caps-cornices-clt-insulation-floors.obj`; that is
what `build/` holds. Read *"Six skins"* at the end for the current shape of a skin — a membrane per
roof and two masonries, which is where the parameter file's `rules:` and `select:` fields come
from — then *"The floor slabs arrived"* below for what they settled, then *"What Duncan read back"*
for the two defects that session found, then *"Open, and first thing tomorrow"*.

    Membrane-Deck9      offset   8 mm | residual 1.02e-16 | clearance  7.3148 mm
    Membrane-Headhouse  offset   8 mm | residual 1.70e-16 | clearance  7.8811 mm
    Membrane-Unit8      offset   8 mm | residual 1.02e-16 | clearance  7.9199 mm
    Cladding            offset  85 mm | residual 1.80e-15 | clearance 17.9998 mm
    Masonry-Brick       offset 150 mm | residual 1.94e-15 | clearance 86.8850 mm
    Masonry-Firewall    offset 161 mm | residual 1.89e-15 | clearance 18.0278 mm

The three membranes are the one membrane cut up — 237.3814 m2 between them, the figure the single
skin printed — and the two masonries likewise, 271.1112. Every figure quoted **below** this line
was measured with three skins rather than six, and the surfaces they name have not moved; where a
skin is called `Membrane` or `Masonry` in an older section, read it as all of its zones together.

**The whole student-house arrived on 2026-08-28 and all three skins solve on it.**
`whole-building-walls-parapets-caps-cornices-clt-insulation.obj` — 79 objects in 92 bodies, nine
wall lifts in two wings, three roofs, both scuppers, three corniced walls, the headhouse. Duncan:
*"a last test before we publish our repo... I am hoping it will skin without incident."* It was
not without incident: one authored condition, two real defects in this module, and the floor
slabs, which are missing and account for everything still visibly wrong. All four earlier
substrates are byte-identical bar the two deck bakes' cladding, which **gains** 1.021 m2 each.

    Membrane   offset   8 mm | residual 2.13e-16 | clearance  7.3148 mm | 276 -> 216 triangles
    Cladding   offset  85 mm | residual 1.29e-15 | clearance  0.0002 mm | 484 -> 286 triangles
    Masonry    offset 150 mm | residual 2.19e-15 | clearance 18.0001 mm |  51 ->   6 triangles

**Warning-free**, as of the `rise` fix below. The suite is 155 -> 160.

Separations 10.000 / 55.973 / 18.000 mm — the same three figures the deck bake gives, which is
the check that says nothing about the enlarged substrate moved the systems relative to each other.

**The authored condition: `UNSURVEYED`.** Duncan: *"The L0, L2 and L3-internaljoin-S panels and
their adjacent panel ends on that plane must be left uncovered until a full student-house site
model is surveyed."* Read as L0, L2 and **L4** — there is no `L3-internaljoin-S` in the export and
L3 is the other wing, nowhere near `y = 10.3`, so the third name is taken as the third of the
three panels on that plane. Worth a word from Duncan, but there is only one coherent reading.

The build **stopped dead** on it before anything else: `rise` raises on `L0-internaljoin-S`,
because the three panels are a stack of their own — set back 250 mm at the foot of each lift, so
nothing rests on the one below — with no cap and no slope anywhere in it. That raise is the
geometry saying it cannot tell which side is out, and the stamp is the authored answer. See
CLAUDE.md, *"a wall the substrate cannot yet place takes no skin at all"*. The "adjacent panel
ends" half costs one clause rather than a rule: with no exterior seed on `y = 10.3` there is
nothing for `_grow_coplanar` to carry across, so the returns the streetfront and courtfacing walls
present there stay ends. Measured at **0 faces** claimed on that plane by any of the three skins.

**The defect: a horizontal edge welding two sheets that have parted.** This one is worth reading
properly, because it was silent-ish and general. The solve keeps substrate-horizontal edges
horizontal by tying endpoint heights, and those ties **chain** — which is correct until a chain
runs from an upward sheet to a downward one at the same level, and then it demands `+distance`
and `-distance` of one connected set of heights. Least-squares does not report that; it splits
the difference. Measured before the fix: **5.15 mm** of `offset_residual` on the membrane, 66.5 on
the cladding, 96.6 on the masonry — five orders above the 1e-9 that means something broke — and
the membrane then died in `_tiling` with *"the offset outline crosses itself"*, which names a
symptom two steps downstream of the cause. `_retiled` was right to refuse; the outline really had
crossed itself, because the solve had put it 5 mm out.

It is at `z = 6.75` and nowhere else on this substrate, and the reason it is only there is the
open item below.

**Left open: the floor slabs are missing, and that is what made the pinch.** Duncan said so
mid-session. Every lift has a 250 mm rebate at its foot — an inset "foot" the slab bears beside —
so with no slab the rebate ring is an exposed **upward** face at every lift boundary. That alone
is one sheet and harmless. At `z = 6.75` the building also steps off the internal join line
(`y = 10.3`) onto the court line (`y = 11.3`), so the L6 lift oversails and its foot's **soffit**
is exposed at the very same level. The two sheets meet at exactly two points —
`v204 [0.2281, 10.3, 6.75]` and `v429 [10.8519, 10.3, 6.75]`, both on the join plane — and those
two points are the whole of the weld: cut them out of the level graph and it splits cleanly into
one up component and one down component.

Confirmed by construction rather than by argument: adding a synthetic floor plate at
`z 6.75..7.00` takes the exposed up faces at that level from 11 to **0**, the pinch vertices to
none, and all three skins then build with the torn-edge rule never firing. So a re-export with
the slabs in removes the condition at source. The rule stays regardless — the weld is a real thing
for the module to get right, and a building that genuinely steps like this without a slab between
is not an error — but the geometry Duncan wants is the one with the slabs.

**No longer posed, but the asymmetry behind it is still there: the cladding's one warning.**
It is **gone** as of the `rise` fix above — the whole-building bake now builds *warning-free* — and
it went for a reason rather than by luck: all three crossings were the drip at an internal corner
of `Lobby-`, `L3-` and `L5-courtfacing-E`, and those are among the walls whose direction the fix
corrected. What follows is the diagnosis as it stood, kept because the asymmetry it names is real
and the next substrate that lands a skin flush on a substrate face will pose it again.

**Also open, and small: the cladding's one warning.** `WARNING: 3 crossing(s) into the substrate`,
and it is a **52 nm graze**, not a penetration. `buried` reports nothing; a 7 260-point sample over
each of the three triangles has **0 points inside**; the deepest reading is 52.5 nm. The cause is
exact: the drip band's mitre at the internal corner where the mitoyen wall meets `*-courtfacing-E`
lands flush on that wall's face at `x = 8.92` — correctly, dying on the wall behind the neighbour's
cladding, the same arithmetic as *"the outer system owns the corner"* — and `substrate.union` puts
that plane at `x = 8.919999948`, **52.0 nm** inside the part's own snapped `8.92`. The skin is
exactly where the offset put it; the surface it is checked against is the *parts*, which sit up to
~5e-7 m from the union the skin was derived from.

So it is a measurement artefact of comparing across the union/parts boundary, and the asymmetry
that lets it through is that `measure.buried` allows for the float32 floor (`SURFACE_TOL = 1e-6`)
and `measure.intersects` does not (`tol = 1e-9`). It has not bitten before because no earlier bake
puts a skin surface flush *on* a substrate face — every skin there stands 8, 85 or 150 mm proud of
everything. **Duncan's call**, because it is the build's verdict and he chose that verdict on
2026-08-25: give `intersects` the same allowance `buried` has, or leave the warning standing and
documented. Nothing else on this substrate warns.

### The floor slabs arrived, and settled it (2026-08-28)

`whole-building-walls-parapets-caps-cornices-clt-insulation-floors.obj` — the same 79 objects plus
`L0.Floor` … `L8.Floor`, 101 bodies. Duncan: *"Skin it to show how the C-shapes will go away."*
They go, and so does the other thing the missing slabs were causing.

    Membrane   offset   8 mm | residual 1.70e-16 | clearance  7.3148 mm | 276 -> 216 triangles
    Cladding   offset  85 mm | residual 2.14e-15 | clearance 17.9998 mm | 310 -> 139 triangles
    Masonry    offset 150 mm | residual 1.92e-15 | clearance 18.0001 mm |  51 ->   6 triangles

Warning-free, separations unchanged at 10.000 / 55.973 / 18.000 mm.

**The C-shapes are gone, and only they are gone.** The cladding's claim on wall tops:

    z          1.15   2.55   3.95   5.35   6.75   8.15   9.55  | 12.83  12.83  13.10  13.10  14.74  14.74
    without    11     13     11     11     11     11     11    |   5      5      4      4      5      5     faces
    with        0      0      0      0      0      0      0    |   5      5      4      4      5      5

79 faces and 40.768 m² of slab-bearing ledge, gone; all six real coping levels unchanged face for
face and square metre for square metre. On the emitted skins: **Membrane and Masonry are identical
to five decimal places** (237.38144 and 271.11120 m²), and the Cladding goes 642.72484 → 580.65679,
losing 62.068 m² — 30.416 of horizontal shelf, 20.539 of the 33 mm drip hanging off it, and the
rest the returns and miters at the ends of those runs.

**And the `z = 6.75` weld goes with them**, which is the same fact said differently: the exposed
ledge was one of the two sheets that met at a point. 11 up faces at that level → 0, two pinch
vertices → none, and the torn-edge rule fires nowhere on this substrate. `clearance` on the
cladding goes 0.0002 → 17.9998 mm, which is the authored reveal and is what it should read.

**What the slabs posed instead: a slab is not a cap plate.** Two of the nine were joined to walls
as cap plates and cost 16.087 m² of court elevation, and the cause is a sentence the code did not
say. `_next_lift`'s docstring reads *"flush on both faces **across its thickness**"*; the code took
any opposed pair, and a wall's two **ends** are an opposed pair too — they look away from each other
exactly as its faces do. `L0-courtfacing-W` is 420 mm thick and 3.18 m long:

    pair                          separation   L2.Floor flush with both?
    y = 7.12 / y = 10.30  (ends)    3.1800 m           yes
    x = 10.68 / x = 11.10 (faces)   0.4200 m           no

So the slab was its next lift, `group_caps` joined it as the cap, the merged element classified
**`roof`** on the slab's area, and `wall_faces` skipped a wall that was no longer a wall. The
facade was not misclassified — it was never classified at all.

Fixed by taking the pairs across the direction the element is **thin in**. Not the smallest
separation, which was tried and is wrong: a rebate is an opposed pair too, and one across the
element's *length* is as narrow as one across its thickness. `Parapet-Headhouse-S` is 420 mm thick
and 5.44 m long and carries a 248.1 mm rebate at each end as well as along its face — three pairs
at 0.2481 m, two of them lengthways — so the smallest picked a lengthways pair, the cap plate was
refused, and every headhouse wall lost its direction. The widest pair in each direction is what
that direction measures, and the thin one is the direction whose widest is smallest: 0.42 m across
the thickness against 5.44 m along the run. Every pair in that direction is then kept, rebates
included, because `CapPlate-Deck9-S2` sits in exactly such a rebate.

**All five earlier substrates are bit-identical across this fix**, checked against the state before
it as well as against the start of the session.

One difference is left and it is not a loss: seven walls each drop **0.043 m²** of facade, a sliver
at a court corner in the 250 mm slab zone — `L3.Floor` runs out to `y = 7.2919` and buries it, so
the union has no such face any more. Confirmed: 2 faces / 0.0430 m² there without the slabs, 0 with.

**What the slabs do not settle** is the `UNSURVEYED` condition, which is authored and still holds:
the `y = 10.3` join plane now carries 48 faces rather than 34 — the slabs present their own edges
on it — and **none** of them is claimed by any skin.

### What Duncan read back off the whole-building cladding (2026-08-28)

Two defects, and they have different homes: one was ours, one is the missing slabs again.

**The four-storey slot was `rise`'s weighting, and it is fixed.** Duncan: *"E76/77/78 is a four
storey vertical slot which shouldn't be there. It looks like the southern ends of the alleyback-W
panels are not being covered."* He was right about the faces. The cause is the item this file had
open as *"The lift that is not a lift"* since 2026-08-27 — `L7-alleyback-W` coming out with
`rise = (0.604, -0.797)`, a diagonal — but **not** the cause that entry proposed. It is not that
`_next_lift` accepts the two returns at the wall's ends; it is that `rise` then weighted them by
the lift's **own underside area** where its docstring says "how much underside the lift bears on
us with". A return is a whole elevation long, so it outvotes the wall's actual next lift:

    lift                    direction     own underside     bears on this wall
    Parapet-Deck9-W         (1, 0)           4.406 m2            2.865 m2     <- the real lift
    Parapet-Deck9-N         (0, -1)         10.397 m2            0.137 m2
    Parapet-Deck9-S         (0, 1)           4.587 m2            0.160 m2
    ---------------------------------------------------------------------
    weighted as coded  -> (0.604, -0.797)      weighted as documented -> (1.0, 0.008)

The four `*-alleyback-W` panels inherit the diagonal up their stack, so `facing` on their `y = 7.54`
end read −0.797 and classified **interior** rather than as the end it is. An end coplanar with a
neighbour's facade is grown into the exterior and clad; an interior is not — hence a slot the full
height of the wall. Weighted by `_plan_overlap` instead, which is the measure `group_caps` already
settles a contested plate with, and which is what the docstring promised. Measured: the two
headhouse bakes are **bit-identical**, the two deck bakes gain 1.021 m² each, the whole building
gains 4.299 m², and **nothing anywhere loses a face**. It also retires the entry below: the
spurious 87 × 250 mm panel on `L7-alleyback-W`'s corner return is gone, which is the 0.043 m² the
deck bakes trade for the 1.064 m² end.

The fix `_next_lift` did *not* need is worth recording, because it was the obvious one and it was
wrong: requiring the opposed pair to be held by **one body** would break a parapet built as an
inner and an outer leaf, where no single body holds both faces. Weighting is the smaller and truer
change — the returns really are lifts of that wall, they just carry almost none of it.

**The C-shaped bits are the missing floor slabs, and they are not fixed.** Duncan: *"There are
c-shaped bits of cladding (selected) which are extraneous. It looks like they are covering interior
surfaces."* They are wall tops, claimed by `cladding_faces`' "every wall top", at **seven internal
lift boundaries**:

    z = 1.15  2.55  3.95  5.35  6.75  8.15  9.55     11 to 13 faces each, 40.8 m2 in all

Each is the slab-bearing **rebate** at the foot of the lift above: every lift is inset 228.1 mm on
its outer face and 248.1 mm at its ends for the 250 mm below its finished floor, and with no slab
drawn in it that ring is an exposed upward face of the wall below. "Every wall top" reads it as a
coping, the cladding runs out across it and the lap hangs a 33 mm drip off its edge — a bracket in
section, wrapping each wall, which is exactly what Duncan selected. Only the three cap-plate levels
(12.83, 13.10, 14.74) are real copings.

Proven the same way the `z = 6.75` pinch was: a floor plate at `z 6.75…7.00` removes **that level's
11 faces and 6.539 m² and nothing else**, every other level untouched. So the re-export that closes
the pinch closes this too, and the two are one substrate defect with two symptoms.

`cladding_faces`' **ledge** rule cannot catch it as written, and the reason is worth knowing. It
takes both halves — a roof running into the wall, and the wall carrying on above — and *neither*
reads here. There is no roof, because the slab is the roof and it is absent; and "carrying on
above" is tested as `triangles.z.max < the element's own highest`, which is false, because the
rebate ring **is** the top of `L0-courtfacing-N` and the wall carries on as a *different element*.

If Duncan wants the rule anyway rather than the slabs, the shape of it is derivable with nothing
authored: **an upward face at the level the next lift bears on is a bearing, not a coping** —
`_next_lift` already computes that level. It is deliberately not built: it reaches every wall in
every substrate, it does nothing at all once the slabs are in, and one substrate poses it.

### What the review round found (2026-08-28)

`/code-review high` over the whole-building work. Four findings, all verified against the code
before acting, all four real, and none of them moved a vertex — the four earlier substrates stayed
byte-identical and the whole-building report is unchanged to the figure. Two are the same mistake
in two places: **an index is not a name, and a name is not an identity.**

- **`torn` rode through `clean` with stale indices.** `clean` strips `plane_ids` and `folds`
  precisely because cleaning rebuilds both indexings, and `torn` is a list of vertex index *pairs*
  — the same kind of thing — and was not in the tuple. It matters more than `folds` does, because
  `pipeline` hands back the **cleaned** mesh and the student-house supplies its own reporting off
  it, so a caller would have got pairs indexing the pre-clean numbering. `build.py` was already
  reading it off the raw skin, which is why nothing here showed it. Stripped now, and the test
  that states the property covers all three keys.
- **`build.stamped` matched `metadata["name"]`, which is not the `o` name when a group splits.**
  `from_obj` writes `<group>.1`, `<group>.2` when one `o` group yields several solids — this bake
  does it to the taper layers — and only `metadata["object"]` is unconditionally the group. A join
  panel exported as two disjoint solids, which a rebate detached at a lift boundary would produce,
  would have matched nothing, been stamped with nothing, **silently**, and been clad after all.
  Matched on `object` now. The docstring had the same slip written out in prose.
- **The `UNSURVEYED` check read only the element's first body.** `faces.roles[members[0]]` on the
  line above is safe because a role is computed per element and shared; a metadata tag is not, and
  `elements_of` orders members by part index. Asked of every body now.
- **The adrift-vertex cut skipped an edge that names no sheet.** `face_rise` is `nan` off a level
  face, so a horizontal edge between two *sloped* faces gives an empty sheet set and fell through
  the `len(rs) == 1` guard — chaining the two sheets through the very point the rule separates.
  No substrate poses that edge; excluding it was an accident of how the sheets are read rather
  than a decision, and dropping the clause makes the code say what the comment already said.

**`build.py` split into three on 2026-08-28 and the result packaged the same day**, so that the
student-house can import the rules rather than copy them. Everything importable is now the
`skinning` package — `skinning.rules`, `skinning.pipeline` over `skinning.skin` — and `build.py`
and `audit.py` stay outside it at the root as this rig. `pip install -e .`, or install from the git
URL. No geometry moved through either step: the report and every OBJ are byte-identical on all four
substrates. See *"The module split: rules, pipeline, rig"* and *"Packaging it"*.

**The reveal landed on 2026-08-27 — a second authored allowance, `reveal: 0.018`.** A cladding
skin stands `distance` off the wall it clads and `reveal` off a substrate feature it dies against.
The same day the skirt over a cornice was told to run to the cornice's bottom. All four substrates
build warning-free and the suite is 138 → 148.

    Membrane   offset   8 mm | residual 9.89e-17 | clearance  7.3149 mm | 215 -> 163 triangles
    Cladding   offset  85 mm | residual 9.44e-16 | clearance 17.9999 mm | 199 -> 119 triangles
    Masonry    offset 150 mm | residual 1.69e-15 | clearance  18.0000 mm |  12 ->   2 triangles

Separations are 10.000 / 55.973 / **18.000** mm. That last one is the design and not a collision:
the cladding's return wraps down the cornice and stops flush with its underside, the masonry's top
stops `reveal` under the same soffit, and the two look straight at each other across the joint. **Slope absorption is bit-identical to before on
every substrate** — 0.685/7.279/7.400 here, 0.158/1.717/2.969 on unit8, 0.158/1.717 on the
headhouse, 0.655/6.963/12.287 on the three-part deck — which is the check that says the reveal
moves the planes it names and disturbs nothing else in the solve. See *"The reveal, and the sill
that is a roof"* below for what it cost to get there.

The cladding's clearance is now **the authored reveal**, and will be on any substrate with a lined
opening: the lining stands 18 mm off its cheek by construction, so `distance` is no longer the
floor. That is the fourth reason `clearance` is printed rather than asserted, and the first one
that is a design intent rather than an artefact.


**The fourth substrate arrived on 2026-08-26 and now builds, warning-free.**
`deck9-parapets-caps-cornices-clt-insulation-unit7-walls-headhouse.obj` — 35 objects, the
student-house deck 9 with its L7 walls under it, the same headhouse on top, **two** scuppers, and
a second corniced wall. Duncan: *"The geometry is familiar, I am hoping this will skin without
incident. A real test for our program."* It was not without incident: **seven** defects, all in
this module, all fixed and pinned. See *"The deck 9 bake: what it found"* below.

As it stood **that day** — the current figures are the block above, and the cladding and masonry
readings have since moved with the reveal:

    Membrane   offset   8 mm | residual 9.89e-17 | clearance  7.3149 mm | 215 -> 163 triangles
    Cladding   offset  85 mm | residual 1.10e-15 | clearance 74.8901 mm | 215 -> 126 triangles
    Masonry    offset 150 mm | residual 1.78e-15 | clearance 150.0000 mm |  12 ->   2 triangles

No self-crossing, nothing crossing into the substrate, nothing buried, no pair of skins crossing.
The three earlier substrates were unchanged to the figure — 173172 mm², 3304 mm², 145 → 115,
142 → 86, clearance 7.8808 and 74.8903, separation 66.889 — and the suite was 131 → 138.

**`Headhouse-N`'s nib needs no re-modelling after all.** Duncan chose on 2026-08-26 to cut it and
re-export rather than build a vertex split, and that is now moot: the fold at `v53` was the
membrane covering the inside of the headhouse, and once the deck under the headhouse is read as
the floor it is, the membrane never goes near that pinch. The substrate builds as exported. The
vertex split stays undone and unqueued — see *"The open question"* for what it would be, and note
that nothing now poses it.

**The 771 mm² triangle buried in the cap plate is gone too**, and for a reason rather than by
luck: it was a face of a **boolean flap**, not of the substrate. Duncan chose to leave it warned;
`substrate.union` dropping the flap removed the face it stood on, and the cladding's clearance
went 0.0006 → 74.8901 mm. Nothing was tolerated in the end.

### Open, and first thing tomorrow

**2026-08-28's second session landed in three commits**, one per seam: the whole building
(`UNSURVEYED`, the torn-edge rule and a review round), then `rise`'s weighting, then the floor
slabs and `_next_lift`'s thickness. Each carries its own tests and its own section below.

**All six substrates build warning-free**, the suite is 161, and the four that predate this
session are bit-identical to where they started except the two deck bakes' cladding, which gains
1.021 m² each from the `rise` fix (and loses the spurious corner panel).

**Do not delete `whole-building-…-clt-insulation.obj`** — the one *without* floors. It is now the
only substrate that poses the torn-edge weld, and `test_the_whole_building_reads_and_skins` pins
the rule on it: 8 torn edges, the two pinch vertices, and clean residuals on all three skins. The
floors bake supersedes it as the model of the building, not as a test case. Both are in the suite.

**Three things are Duncan's to call, and none of them blocks anything:**

- **`L3-internaljoin-S` is read as `L4-`.** There is no `L3-internaljoin-S` in either export and L3
  is the other wing, nowhere near `y = 10.3`, so `build.UNSURVEYED_OBJECTS` names L0, L2 and L4.
  One line if that is wrong.
- **`measure.intersects` allows 1e-9 where `measure.buried` allows `SURFACE_TOL = 1e-6`.** No
  substrate poses it any more — the three 52 nm crossings went with the `rise` fix — but the
  asymmetry is real and the next skin to land flush *on* a substrate face will pose it again. See
  the entry above for the measurement.
- **A bearing ledge is only not a coping because the slab buries it.** With the slabs in, nothing
  is wrong; without them, "every wall top" reads the rebate ring as a coping and the cladding runs
  out across it. The `ledge` rule cannot catch it — it needs a roof running in, and the slab *is*
  the roof. If it is ever wanted as insurance the shape is derivable with nothing authored: *an
  upward face at the level the next lift bears on is a bearing, not a coping*, and `_next_lift`
  already computes that level. Deliberately not built: it reaches every wall in every substrate
  and does nothing once the slabs are in.

**And one that is not open, but is worth not re-deriving**: the `turning upstand` the reveal work
declined to price is still undecided, and still posed by no substrate.

### What the second review round found (2026-08-27)

`/code-review high` over the reveal and the skirt-over-a-cornice work. Six findings, all verified
against the code before acting; four were code and two were figures in this file.

- **The reveal and the flush stop are disjoint by face, not by plane.** `reveal_faces` excludes what
  `wrapped` names, so no *face* is in both — but two cornices whose soffits sit at one level, one
  wrapped and one not, put a face of each on the one plane. `skin_offsets` was writing as it walked,
  so the second pass read the first's own value back and raised the **facade miter** error, naming a
  cause that was not there. It now collects `{plane: distance}` first and raises on a real conflict
  with an accurate message. No substrate poses it — the three soffits are at 11.4644, 12.736 and
  14.425 — so a test poses it instead.
- **`check_seeds` divided by a zero `reveal`.** It is documented as a standalone opt-in a caller may
  run without `validate`, so the schema's `exclusiveMinimum: 0` is not the guard on that path, and a
  zero reached the integer-multiple loop as a divisor: `ZeroDivisionError` instead of a named field.
  Refused by name now, with the reason zero is malformed here where it is an off switch for `drop`.
- **`flush_faces` had no facade gate**, so a skin that clads no facade could still force a plane to
  zero. Only `wrapped`'s "runs down its face" clause was keeping the membrane out, and that is a fact
  about these bakes rather than about what a reveal is for. It now makes the same test
  `reveal_faces` does.
- **Two `np.isclose` calls without `rtol=0.0`** in the new tests — CLAUDE.md's own named hazard, and
  it was live: at 1e-5 relative the real tolerance was ~0.15 mm. Fixing it **failed two tests**,
  which is the finding earning its keep. Both were asserting tighter than the arithmetic supports:
  the scupper's lining lands at `16.371998975` against an exact `16.372`, 1.025 µm out, which is the
  float32 union floor `TOL` exists for. Now `rtol=0.0, atol=2e-6`, and the `np.round` for `unique`
  moved from 6 dp to 9 so a coordinate no longer lands exactly on the comparison boundary.
- **Two figures in this file were wrong.** The headline Membrane residual read `9.71e-17` against a
  deterministic `9.89e-17` — a right value replaced with one taken from a mid-iteration build — and
  the Cladding triangle counts read `193 -> 121` against `199 -> 119`. Both corrected. The lesson is
  the dull one: re-run before quoting, including the lines you are not editing.

The review also confirmed, independently and by measurement, that the `_lap` per-face-offset wiring
is inert (OBJs byte-identical with `offsets` forced to `None` on all four bakes), that the growth
claims exactly 6 cornice faces per cornice-bearing bake and none on either scupper cornice, and that
slope absorption is bit-identical on all four.

### The skirt over a cornice (2026-08-27)

Duncan, reading the built bake: *"In the cladding, the skirt covering a cornice should extend to the
bottom of the cornice. This rule applies only to skirts over cornices. Currently it is dropping
0.115. It should be derived from the bottom of the cornice - .184719 in this case."*

**It is not a skirt, and that is the whole of the diagnosis.** No lap places it: built with
`lap=None` the band is still there. `CapPlate-Deck9-N` oversails its wall and its north face is
flush with the cornice's outer face at `y = -0.16`, so the cladding *covers* the plate's fascia —
`z 12.806…12.833` on the substrate, offsetting to `y = -0.245`, `z 12.806…12.920719` — and stopped
at the arris with the cornice below, which is on that same plane and excluded as a cornice face.
Duncan's 0.115 is `12.920719 - 12.806`, the drop to the cornice's *top*; his 0.184719 is
`12.920719 - 12.736`, the drop to its bottom.

So the fix is a face selection. `cladding_faces` grows along the surface into the cornice — the move
`masonry_faces` and `_opening` already make — and the band runs to the cornice's bottom because that
is where the coplanar run ends. Measured: 6 faces on each cornice-bearing substrate, the wall
cornice's fascia and its two returns, and **none at all** on either scupper cornice, which stand
proud of their wall and so are coplanar with nothing clad. That is what makes *"only skirts over
cornices"* fall out rather than be tested for.

**The last 18 mm needed a second rule.** With the fascia covered, the band overshot to `12.718`:
the cornice's soffit was still a `reveal` plane, so the skin held the joint under a cornice it had
stopped stopping at. `flush_faces` gives the soffit of a cornice this skin **wraps** an offset of
**zero** — a flashing ends at the arris, neither hanging `distance` below it nor leaving it bare by
`reveal`. Same arithmetic as `facade_offsets`' "the outer system owns the corner".

**Two things this got wrong first, both caught by the suite.** `wrapped` read any covered cornice
face, and a cornice joined to a climbed parapet has its top picked up by the membrane's "every
upward face of a climbed wall" — so every such cornice read as wrapped and the **membrane** set its
soffit to zero, a waterproofing layer holding a cladding detail. It now reads only a face the skin
runs *down*. And a test pinned `drop.max() == 13.0766` on the unit8 return elevation, which by then
was reading a **tiling** artefact: with the cornice's end covered, that patch is continuous through
`(0, 13.0766)`, so the point is interior and whether it survives as a triangle corner is `_tiling`'s
business — it does at one end of the wall and not the other. Re-pinned on the outline instead.

**The plane-ownership clause is now inert**, and that is worth knowing before someone deletes it.
It exists because a wall cornice's ends lie in the neighbouring elevation — `Cornice-Deck9-N` puts
one on the `x = 8.5` court plane, 21 faces of which 15 are the cladding's own — and taking that
plane raised at `v90`. Those ends are now *covered*, so they never reach `reveal_faces`; removing
the clause leaves all four substrates building. What would bite it is a cornice whose fascia is not
flush with the cap plate over it, so the skin does not run down the band, while its ends still lie
in clad elevations. `test_a_cornice_end_in_a_clad_elevation_is_left_to_that_elevation` poses exactly
that by stubbing `wrapped`, which is how every cornice read the day before.

### The reveal, and the sill that is a roof (2026-08-27)

Duncan: *"The offset of the cladding edge from the cornice is currently the same as the offset
from the wall. Formulate a plan for creating a second offset seeded to 16 mm. The top of the
masonry cladding should be offset by this value under a cornice. The cladding should be offset
from bottom, and sides of the two scuppers by this value."*

**The number is 18 mm, not 16.** `reveal` is a distance between two surfaces, so `check_seeds`
reads it — `base` and `close` are exempt for being a datum and a bound on a cleanup, and neither
reason transfers. 0.016 is exactly 2x `Membrane.distance`, which the seeding rule refuses. Duncan
chose to author 0.018 rather than move the membrane off 8 mm. 0.017 and 0.015 are refused too (5x
the cladding's 0.085 and 10x the masonry's 0.150); 0.014 and 0.018 are the nearest values that
clear all six.

**The rule is two sets and one exclusion**, and the exclusion is the whole of the difficulty. A
cornice's soffit and ends, and the cheeks of an opening the skin lines — but **never an upward
face**. The reason is in Duncan's second message, and it is the sentence that unblocked this:
*"The cladding should maintain its original offset from the top of the scuppers."*

I had read *"bottom of the scupper"* as the sill and built it that way. It is the drip cornice's
soffit; the sill is the **top** edge of the hole. Read in elevation the hole is bounded by the
cornice's soffit below, the cornice's ends and the cheeks at the sides, and the sill plane above —
and **neither slot has a head at all**, because the cap plate is split in two (`CapPlate-Deck9-S`
/ `S2`, `CapPlate-Headhouse-E` / `E2`) and the mouth runs open to the coping. That was the tell I
missed: a face called "the top of the scupper" does not exist, so the phrase had to mean an edge
of the hole.

**What moving the sill cost, measured before the clarification arrived.** The headhouse taper
falls to the outlet and lands on `z = 14.495` exactly, so the sill and the roof are one continuous
surface arriving at `v93 [8.5, 4.985, 14.495]`:

    f298 plane  9 [-1, 0, 0, -8.5]              0.085  Roof_Headhouse_InsulationTaper.1
    f297 plane 55 [0, 0.0431, 0.9991, 14.6962]  0.085  Roof_Headhouse_InsulationTaper.1
    f296 plane 54 [-0.02, 0, 0.9998, 14.3221]   0.085  Roof_Headhouse_InsulationTaper.2
    f294 plane 53 [0, -0.0431, 0.9991, 14.2669] 0.085  Roof_Headhouse_InsulationTaper.3
    f261 plane 27 [0, 0, 1, 14.495]             0.018  Parapet-Headhouse-E
    f242 plane 27 [0, 0, 1, 14.495]             0.018  Parapet-Headhouse-E

Plane 27 is level and hard; the three tapers are 1.1–2.5° off level and soft, so they absorbed
`85 - 18` — **68.703 mm**, and `slope_deviation` is a max, so that pinned the build's second
diagnostic at a floor it could not fall below. And the cladding's turn-down band, hanging on
`x = 8.585` out over the roof, came down to `sill + 18 = 14.513` where the membrane at that point
has already climbed to `14.5131`: the band's corner sat **0.1 mm below it**, 3 crossing pairs raw
and 2 written, separation 0.049 mm.

Two things ruled out on the way, both worth not re-trying. **Per face instead of per plane**
raises — `two offsets on one plane at vertex 83 [8.08, 4.785, 14.495]`, where the sill and the
drip cornice's top share the plane they are coplanar on. And **a trim at `sill + reveal`** cannot
work in either direction: a cut only takes away, and the bottom edge at `14.580` is already above
the datum, so it would remove nothing and move nothing. Lowering that edge *requires* moving the
sill plane, so the 68.703 mm and the 0.1 mm were one decision, not two.

**The plane-ownership clause.** A scupper cornice's ends carry nothing but the cornice — two faces
each, nothing clad — so the whole plane is reveal. A wall cornice's ends are not: a band runs past
the returns at each end, and `Cornice-Deck9-N` puts one on the `x = 8.5` court plane, 21 faces of
which 15 are the cladding's own. Taking it raised at `v90 [8.5, 4.785, 14.503618]`. So a plane is
taken only where it carries no face this skin covers that is not itself a reveal face, and
`facade_offsets` keeps the rest. A cheek passes on its own, being covered *and* held at the reveal.

**Where it all landed**, live bake:

    Masonry top                       z = 12.718   (soffit 12.736 - 0.018)
    Deck scupper, hole bottom         z = 11.4464  (soffit 11.4644)
    Deck scupper, hole sides        x = 15.072 / 16.508   (cornice ends 15.09 / 16.49)
    Deck scupper, cheek lining      x = 15.208 / 16.372   (cheeks 15.19 / 16.39)
    Deck scupper, hole TOP             z = 11.6194  (sill 11.5344 + 0.085, unchanged)
    Headhouse, hole bottom             z = 14.407
    Headhouse, hole sides           y = 4.667 / 5.303
    Headhouse, cheek lining         y = 4.803 / 5.167
    Headhouse, hole TOP                z = 14.580   (unchanged)

The turn-down band is now `drop + reveal` = 51 mm wide where it was 118. Nothing in `_lap` decides
that: a turned band runs from the skin's own edge, so its width followed the lining inboard.

**`_lap` now takes the per-face offsets**, which the `cladding_laps` docstring had been asking for
since 2026-08-26. Four sites: `drip_at`'s miter, the fold's receiving level, the fold probe's step
back onto the arris, and the turned band's level. It **moved no geometry**: run both ways on all
four substrates, every emitted vertex of every skin is bit-identical, worst delta 0.0. So it is a
backstop rather than a repair. The 12 vertices of the
live bake that carry both a lined cheek at 18 mm and a face the skin laps onto at 85 mm are the
reason it should not be left as a coincidence.

One reading moved and is fully accounted for: unit8's masonry clearance `150.0002 → 86.8849`,
which is the panel's own top corner 85 mm past the end of `Cornice-Unit8-E` (it mitres onto the
rainscreen there) and 18 mm under its soffit — `sqrt(85^2 + 18^2)`. And that bake's
masonry/rainscreen separation went `150.000 → 88.0001`: the brick's top rose 132 mm and what is now
nearest to it is the rainscreen's own return coming over the parapet at `z = 13.0766`, straight
above it. Both are the geometry doing what it should.

**Still open, and deliberately not decided:** whether a *turning upstand* should take the reveal.
Every turn on all four substrates today is a drip, so nothing poses it — the same gap the lap rule
already records.

### The skirt around the deck, and the two rules under it (2026-08-27)

Duncan, reading the deck 9 build back: *"The cladding skirt is inconsistent around the deck. It is
correct around the headhouse. It is correct to the east of the deck scupper. To the west of the
scupper the skirt descends all the way down to the ledge (E44) instead of stopping at 12.792 and
turning down the scupper as it did correctly to the east. It is correct on the west parapet. To the
north, instead of stopping at 12.792 it descends all the way down to the ledge (E31) then covers
the ledge (E54). On the east parapet it stops correctly (E121 at 12.792) then continues all the way
down (E57) then covers the ledge (E55). It looks like the rule is being interpreted differently in
slightly different contexts."*

He was right about the last sentence, and it was two rules rather than one — the two errors his
2026-08-26 note promised. What made it look like four different behaviours is that two *accidents*
masked the second error on two of the four parapets.

**Error 1: two corner returns read as a scupper.** `_opening` pairs cheeks by the sign alone — two
vertical faces of one body looking **at** each other rather than away. `Parapet-Deck9-W` carries
the deck's north-west and south-west corner blocks, because the north and south parapets stop at
`x = 20.52` and it runs on to fill both corners. So one body holds a return on `y = 0.1881` and
another on `y = 7.2919`, the two planes that face each other across the deck, 7.1 m apart. They
paired. `cheeks` is then grown along the surface, so **both whole planes** were claimed the length
and width of the building — the inner faces of the north and south parapets, the L7 walls' faces
below them, and the cap plates' reveals — and `cladding_faces` covers `cheeks & WALL`. A covered
face is skinned over its whole outline, so the skirt was not a drip that ran too far: it was the
inside of the parapet clad head to foot, mitred onto the ledge at the bottom.

The missing half of the test is the word **through** in `_opening`'s own first sentence. A reveal
is cut through its wall and so comes through the union flanked by the wall's two faces — an opposed
pair looking *away* from each other, which is a thickness by the same sign the pairing uses. The
scupper's cheeks are flanked by their parapet's exterior and interior faces, 248 mm apart; a corner
return is flanked by the two faces turning that corner, a quarter turn apart, and by nothing
opposed at all.

The flanking **pair** is what carries it, and a first attempt that asked only for *some* opposed
pair was accidental rather than structural: a court's inner face is flanked by an opposed pair too
— the returns at its two ends — and passes. What separates them is that those look *toward* each
other, because what lies between them is the court and not a wall. `tests/test_offset.py` poses a
plain rectangular ring wall, asserts it reads as no opening at all, then cuts a real slot through
one side of the same body and asserts the slot's cheeks come back.

Measured on the deck bake: 45 cheek faces → 18, which is exactly the two scuppers' four reveals and
the plate reveals the growth adds to them. 0 → 0 on the other three substrates; the single cheek
pair each of the two headhouse bakes poses is unchanged.

**Error 2: "every wall top" claimed the ledge.** The ledge at `z = 11.5344` is an upward face of a
wall, so the cladding covered it — and that is why the skin then ran out across it under the
membrane. It is `_rules`' own sentence read the other way round: a wall **thicker below the roof
than above it** presents its roof's own datum, not a coping. `cladding_faces` now subtracts it,
named by the very relation that elects the wall to be climbed, and the membrane still covers it on
that same election.

Both halves of that are load-bearing. *The roof runs in* is what makes it roof rather than coping.
*The wall carries on above it* is what makes it a step rather than a top — and it is not
belt-and-braces: a coping shares an edge with the top of a cornice beside it, and an **ungrouped**
cornice is its own element and classifies `ROOF`, which is the `_stacked_box` fixture in
`test_the_masonry_runs_the_whole_face_below_a_cornice_not_one_lift`. On the roof clause alone that
test's cladding came back empty and the build raised in the base trim. The seed is grown along the
surface through the wall tops, because the union triangulates a ledge and only the triangles on the
roof's own edge touch it.

**The two accidents that hid it.** The south ledge was already gone, taken out with the scupper's
sill as *the floor of an opening* — `floor` is read per coplanar region and the sill and the ledge
are one region of one part. The west ledge was already gone too, taken out by the false cheek pair
standing over it. So the rainscreen sat on the north and east ledges and not on the other two,
which is the inconsistency Duncan was reading, and neither exclusion had anything to do with what a
ledge is.

**What error 1 was doing for the membrane, and where that belongs.** Fixing the pairing alone broke
the membrane: 7 crossings into the substrate and `clearance 7.3149 → 0.0002 mm`. The corner returns
lie *across* their wall's fall, so `wall_faces` calls them ends and neither exterior nor interior
reached them; the membrane was covering them as `cheeks & climbed`, and with the cheeks gone it
lapped a 205 mm upstand onto them instead. That is a real requirement wearing the wrong rule's
clothes. **An interior wraps a corner the same way a facade does**, and `wall_faces` already grows
ends into the exterior set for exactly that reason — it now grows them into the interior set as
well, exterior first and keeping precedence. The membrane then came back **bit-identical** to
before: 215 → 163 triangles, 214901 mm², clearance 7.3149, 81 border edges.

**Measured, deck bake.** Cladding 215 → 193 raw triangles, 126 → 121 cleaned, 107 → 87 raw border
edges, `clearance 74.8901` unmoved, no warning. The skirt is now a 33 mm band from the coping's
offset down to `12.792` on all four parapets, and the only cladding below that anywhere on the deck
is the two turn-downs at the scupper — `x 15.157…15.275` and `16.305…16.423`, each `85 + 33` wide,
mirrored, both running to the sill at `11.6194`. Before the fix only the east one existed; the west
one was buried inside the full-height panel. The other three substrates are unchanged to the
figure, and `_opening`, `wall_faces` and the ledge subtraction each move **nothing at all** on them
— 0 faces, measured on all three.

Four tests, all four red before the fixes: the courtyard-and-slot pair in `tests/test_offset.py`,
the ledge and coping on a stepped-parapet fixture there, and two on the deck bake in
`tests/test_import.py` — the whole run of the skirt, and the corner returns reading as interior.

### The lift that is not a lift (2026-08-27; CLOSED 2026-08-28)

**Read the entry at the top of this file first.** The diagnosis below is right about the
symptom and about `_next_lift` accepting three lifts, and **wrong about where the fix goes**:
the returns really are lifts of that wall, and what was broken was `rise` weighting them by
their own underside area instead of by how much of each bears on the wall. Requiring the
opposed pair to be held by one body — the first shape proposed below — would have broken a
parapet built as two leaves. Kept as written because the measurements in it are still good.

Found while checking what the skirt fix left behind, and **not fixed**: it is a `_next_lift`
question, which decides every wall's exterior and interior, and Duncan should choose whether to
spend that.

`L7-alleyback-W` (`x 20.52…20.9`, `y 0…7.54`) comes out with `rise = (0.604, -0.797)` — a diagonal,
which is the average of two parapets' falls. `_next_lift` accepts three lifts on it:
`Parapet-Deck9-W`, which genuinely is its next lift, and `Parapet-Deck9-N` and `-S`, which are the
returns at its two ends. Those two pass the flush-on-both-faces test only because the pair is made
up **across two bodies of one element**: the parapet supplies `x = 20.52` and its own cap plate,
which overhangs to the building's outer plane, supplies `x = 20.9`. The docstring's own reasoning
against a neighbour's cap plate — *"It is not flush with y = 7.12, so it is not another lift"* — is
defeated by the parapet standing beside it in the same element.

What it costs today is one panel: the wall's own corner return at `y = 7.2919`, `z 8.065…8.315`,
`x 20.52…20.6069`, reads `facing = 0.797 > fall` and so is a facade rather than an end, and the
cladding covers it. With `rise = (1, 0)` it would read as an end, be grown into the **interior** by
the rule this session added, and take a lap instead. `L7-courtfacing-E` has the same shape of
answer (`rise = (-0.154, -0.988)`, two lifts, one of them the north parapet across a zero-area plan
overlap) and no visible defect. The alley elevation itself is saved by the growth: `x = 20.9` reads
as an end at `facing = 0.604` and is grown into the exterior set off `Parapet-Deck9-W`'s facade.

The shape of a fix is to require the opposed pair to be held by one body, or to require a plan
overlap of substance rather than of bounds. Both reach every wall in every substrate, so neither is
a small change.

### The deck 9 bake: what it found

The substrate is `deck9-parapets-caps-cornices-clt-insulation-unit7-walls-headhouse.obj`, exported
2026-08-26 and matching the Blender scene object for object. What it poses that no earlier bake
did: **cap plates mitred at the corners** rather than overlapping, a **cornice running the full
width of an elevation** and past the returns at both ends, a **wall cantilevered out over the
court** above `z = 12.595`, and a roof plane carrying an insulation CLT's end face.

Seven defects, each found by running it, each fixed and pinned. The first four came out of
getting it to build at all; the last three out of Duncan reading the result back:

1. **A cornice at a corner picked the wrong host.** `Cornice-Deck9-N` runs 12.4 m over an 11.6 m
   parapet and over the 380 and 420 mm ends of the two parapets returning at its ends. It stands
   proud of all three and passes every condition against all three, and all three are 1856 mm
   tall, so *"the tallest wins"* had nothing to choose with and kept the first in the file. The
   union of that 380 mm return with the band read horizontality 0.235 — `WALL` by area, `ROOF` by
   the thinnest OBB side — and `group_caps` stopped the build. Now the host is the body **backing
   most of the band's run** (11.6 m against 0.38), height breaking a tie. Every cornice on every
   other substrate here has exactly one candidate, so nothing else moved.

2. **A cap plate at a corner was claimed by two walls and went to the wrong one.**
   `CapPlate-Deck9-S2` runs 4510 mm along the south parapet and lands in a 248 mm rebate at the
   head of `Parapet-Deck9-W`, flush with both faces of *that* rebate, so `_next_lift` accepts it
   for both walls. `group_caps` assigned inside the loop, so the last element in the file won, and
   the plate joined the return: `Parapet-Deck9-W` then read horizontality 0.204 and `Faces.roles`
   refused it. Claims are now collected and the plate goes to the wall backing most of it in plan,
   1.025 m² against 0.094 m². One plate contested out of ten; the rest are unchanged.

3. **`facade_offsets` decided per facade-face where it had to decide per plane.** The masonry
   mitres onto a neighbour's plane, and the neighbour's *facades* are what identify that plane —
   but the assignment was also scoped to the exterior set, so a face on the plane that is nobody's
   facade kept `mine`. `Roof_Deck9_CLT`'s end lies in the court elevation at `x = 8.5` between two
   rainscreen-clad walls, and the plane was asked for 0.085 and 0.150 at once at the vertex it
   shares with the parapet above: `two offsets on one plane at vertex 14`. The identification is
   still made off the neighbour's facades; the assignment now reaches the whole plane, minus what
   this skin covers — which is the split that is *meant* to raise, and still does.

4. **`clean`'s `dissolve` cut a corner off the cladding.** GEOS returned one ring with two
   consecutive coordinates 1.78e-15 m apart, where several rectangles meet at a point. They weld
   to one vertex, each then reads as straight through *itself* — its ring neighbour is the same
   point, so the cross product is exactly zero — and both were dropped. An L-shaped ring came back
   as a diagonal and the cladding **gained 0.910 m²**, on the one pass whose whole claim is that it
   changes no outline. `build.py` printed it as `-904982 mm2 of coplanar overlap removed`, a
   negative that is worth reading as the alarm it is. Consecutive repeats are now dropped where the
   ring is built. `tests/test_import.py` states the property on both committed bakes.

5. **The membrane covered the inside of the headhouse.** Duncan, reading the build back:
   *"The selected faces in Membrane should not be covered. They are on the inside of the headhouse
   walls."* Seven faces — the interior faces of `Headhouse-N`, `-S` and `-W`, two laps onto
   `Headhouse-E`, and the deck itself at `z = 11.195` between them. One cause under all of it:
   `Roof_Deck9_CLT` runs on under the headhouse with the insulation cut away around it, so its
   bare top read as a roof surface, and a roof surface elects the walls it runs into. **A roof is
   a roof where it has the sky over it** — `_under_cover` casts straight up from the face and
   reads whether the substrate is hit. One part, one role, two surfaces: no test on the part could
   have separated them. 2 faces on this bake, none on either headhouse bake.

6. **The membrane stopped at the roof's edge on every deck 9 parapet.** Duncan: *"Horizontal
   ledges like F11 in Substrate_Parapet-Deck9-S should be covered with membrane. Membrane then
   continues up the parapet wall and covers the cap plates like on the headhouse."* The parapet is
   420 mm thick to `z = 11.5344` and 248 mm above it, so the roof build-up butts into the thick
   part and what it meets at its own level is the **top** of that thickening — a 172 mm ledge,
   coplanar with the finished roof and continuous with it. It touches no vertical face of the
   parapet at all, so `interior & meets` elected none of the four, and their copings went bare.
   **A roof runs into a wall through a ledge as well as through a face.** Both halves of Duncan's
   sentence are that one election: the ledge and the coping are both "every upward face of a
   climbed wall", the cap plate being one body of the element. Nothing is elected on either
   headhouse bake, where the build-up sits on the walls and meets the parapets face to face.

7. **The union came back in three pieces.** Two **flaps**: four triangles each, two facing each
   way, enclosing nothing, at two of the four cap-plate mitres — the shared face manifold3d left
   behind where two plates meet exactly on one plane. Invisible until fix 6 climbed the parapets;
   then the membrane covered both sides of one and `_reconcile` refused the vertex, which is the
   fold `planar_offset`'s own runaway guard names "a fragment a boolean left behind". Volume over
   area separates a flap from a solid with nothing to tune — 197 mm of mean thickness against 1.8
   and 12.6 **nm**, on a substrate snapped to a 1 µm lattice — so `substrate.union` drops them and
   says how many in `metadata["flaps_dropped"]`. It also took the cladding's buried triangle with
   it: that face was the flap's, not the substrate's.

#### `Headhouse-N`'s nib, and `v53` — closed, and how

This was the blocker for most of 2026-08-26, and fixes 5 and 7 dissolved it. It is written up
because the diagnosis is still the right one to reach for the next time a fold refuses, and
because what closed it was **not** the answer that had been chosen.

With the first four fixes in and none of the later ones, the membrane raised at

    the surface folds back on itself at vertex 53 [8.5, 2.85, 12.595]: it lies on planes
    facing [-1, 0, 0] and [1, 0, 0] ... 6 of its faces are covered by a skin

and it is not a sliver. The geometry is real, and it is a **point** of zero thickness:

- `Headhouse-E` is the west wall, `x 8.08…8.5`, and it begins at `z = 12.595` — it cantilevers out
  over the court, with nothing under it in this export. Its face at `x = 8.5` faces **+x**, into
  the headhouse: the interior face of that wall.
- `Headhouse-N` below that level stops at `x = 8.5`, flush with where `Headhouse-E`'s inner face
  will be. Its face at `x = 8.5` faces **−x**, out over the court: the wall's end.
- The two meet at exactly one point, `[8.5, 2.85, 12.595]`, coplanar and opposed. Material is on
  the −x side above it and on the +x side below it.

The membrane reaches both sides, and legitimately. It covers `Headhouse-N`'s interior face at
`y = 2.85` and turns concavely onto `Headhouse-E`'s inner face — an ordinary internal corner of a
room. And it covers a small rebate face at `y = 2.6781` and turns concavely onto `Headhouse-N`'s
end — that rebate is the **nib**: a 420 x 248 x 245 mm block hanging below the cantilever's north
edge, `y 2.43…2.6781`, `z 12.35…12.595`, isolated in space, its numbers borrowed from elsewhere in
the model (248.1 mm is the deck 9 cap plate's width, 245 mm a CLT thickness). Both concave, so
`_receivers` has nothing to choose with — its rule is *concave beats convex* — and it hands the
contradiction to `_reconcile`, which is what the docstring says it does where a pair is concave on
both sides.

`_knife_side` cannot help: it substitutes the far half's normal only where the skin **dresses
nothing of that body**, and here it dresses both.

Two ways out were costed, and Duncan chose the first — cut the nib and re-export. **Neither was
needed.** The membrane only reached the rebate face because it was climbing `Headhouse-N` at all,
and it was climbing it because the deck under the headhouse read as a roof. Fix 5 stops that, the
rebate face is no longer covered, and the pinch at `v53` is simply not somewhere this skin goes.
The substrate builds as exported. What follows is what the two ways out were, kept because the
second is still the honest general answer if a skin ever does have to dress both sides of a pinch.

- **Change the substrate.** Measured, not guessed: an OBJ with `Headhouse-N` rebuilt as the plain
  L-prism it would be without the nib — every other object byte-identical — builds all three
  skins, no self-crossing, nothing crossing into the substrate, residuals 1.35e-16 / 4.15e-15 /
  1.61e-15. The nib is the whole cause. (An earlier probe that replaced the part with a boolean
  union of two boxes threw up other errors; that was the probe, not the geometry. The surgical
  rewrite is the one to believe.)
- **Split the vertex.** The correct general answer: where the substrate pinches to zero thickness
  on a plane, the two sides are separate sheets and the shared vertices should be duplicated, one
  per side, each solved from its own side's planes. That subsumes `_knife_side`, which is the
  one-sided special case of it. It is invasive — `planar_offset` returns `faces=mesh.faces.copy()`
  and `_tiling` and `_lap` both index `skin.vertices` with `body.faces`, so a split changes the
  indexing every one of them shares. One instance so far.

Deferring is a real answer here, and there is exactly one instance.

#### What `/code-review high` found on top

Five findings on the same diff, all verified against the code before acting, all addressed.

- **`buried` was not deterministic**, which made the verdict itself flap: 3 and 4 in alternate
  runs over one fixed cladding mesh, with nothing about the geometry changing. `trimesh.contains`
  casts a ray in a random direction and a sample *on* a part's surface resolves whichever way the
  ray leaves. That is no longer a rare reading — `facade_offsets`' zero branch puts skin vertices
  in a substrate face on purpose — and a verdict that moves without the geometry moving is
  precisely what `clearance` was demoted for on 2026-08-25. Containment is now confirmed against
  the distance to the surface, at `SURFACE_TOL = 1e-6`: the union's float32 floor, not a weld
  radius. The sample that flapped sat **6.390e-07 m** from `CapPlate-Deck9-N`, on the plane its
  cornice shares. The deck bake now reads a steady 3.
- **The cross-skin verdict read the raw meshes alone.** The per-skin verdict is deliberately taken
  on both, because `clean` invents a gusset and a verdict is about what ships; the pairwise loop
  was not, which left exactly the gap that change closed. The membrane carries 3459 mm² of gusset
  on the live bake. Both now.
- **`cladding_laps`' docstring cited a guard that fix 3 above removed.** It said the `_lap` hazard
  was unreachable "because an interior face is never in the exterior set `facade_offsets` moves" —
  true until the miter widened from the neighbour's facade *faces* to the whole plane. What keeps
  it unreachable is now a measurement and the docstring says so: across all four substrates, no
  face any skin may lap onto is a face `facade_offsets` moves (0 of 2, 0 of 12, 0 of 102, 0 of
  138), and `Masonry` is safe by construction with `lap: None`. Check it again if either predicate
  widens.
- **`others` is every sibling skin, not every cladding system**, so the membrane is a miter
  *target* as well as being exempt as a miter *taker*. What stops the cladding taking an 8 mm
  miter onto it is that `membrane_faces & exterior` is 0 on every substrate — geometry, not
  construction, and `membrane_faces` claims cheeks while `wall_faces` grows a wall end into the
  exterior set, so a scupper cut at a building corner would reach it. Measured and written down,
  not fixed: a system list here would be a second place saying what `CLADDING_SYSTEMS` says.
- **`check_seeds` exempts every zero, not only a zero `out`**, and three places said otherwise.
  Load-bearing now rather than academic: `Masonry.drop` is authored `0.0` beside `Cladding.out`,
  and they would collide as equal seeds if the claim were true. Corrected in `parameters.py`,
  `skin-parameters.yaml` and CLAUDE.md.

The review also confirmed independently that the deck bake's 3 cladding crossings are **not**
caused by the `facade_offsets` widening — the old mask gives the same 3 — and that `v53` is the
code correctly refusing a substrate condition.

#### The cap-plate mitre step — also closed

Behind the fold sat one warning: the cladding buried a single 771 mm² triangle at
`x 8.68…8.82, y −0.05…0.14, z 12.806…12.825`, on the mitre plane at the west end of
`CapPlate-Deck9-E`. Duncan chose to leave it warned, on the grounds that nothing in the face rules
can tell a 19 mm step in a coping mitre from a facade. That turned out to be the wrong reading of
it, and the record below is kept for the diagnosis rather than the conclusion: **the face was not
the substrate's.** The two plates mitre exactly and share that face; what stood there was the
boolean flap of fix 7, and dropping the flap removed it. Cladding clearance 0.0006 → 74.8901 mm,
buried samples 3 → 0.

#### What the mitre actually is, since two readings of it were wrong

Worth recording, because both wrong readings were plausible and the measurement settled it in one
line. `CapPlate-Deck9-E` and `CapPlate-Deck9-N` **mitre exactly**: they share the four corners
`(8.5, −0.16, 12.806/12.833)` and `(8.7481, 0.1881, 12.806/12.825)`, their boolean intersection is
−4.6e-18 m³, and the two mitre faces coincide face for face at 2965 mm² each way. There is no
wedge, no step, and nothing proud of anything — the first reading, that their different falls
leave a sliver exposed, was wrong. Nor is the exposed face a facade the rules over-claim, which
was the second reading. It is the **contact itself**, which manifold3d kept as a detached flap
instead of dissolving, and `_owner` then split between the two plates because a coincident face
has no nearest part. Four faces on one plane, two each way, on the same four vertex indices.

The lesson for next time: when two coplanar opposed faces turn up, check `union.body_count`
before reasoning about what the substrate is doing.

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

**`/code-review high skinning/skin/` reached the unreviewed half, and found eight things.** All eight
verified against the code; seven fixed, one referred to Duncan (the fourth bake, in Open items).
Three were in the day-old `measure` code and four in code that had never been in a diff:

- **`substrate.union` returned the caller's own part** when given one, and `skin_over` then wrote
  plane ids into its metadata — so *"`parts` is never mutated and stays the substrate"* was false
  for a one-part substrate. The test asserted `union([only]) is only`, pinning the very
  optimisation that broke the invariant above it; it now asserts a separate equal mesh, plus the
  invariant end to end.
- **`_plane_ids` cached with no invalidation**, and `Trimesh.copy()` copies metadata — so a moved
  body got the representatives of where it used to be. Plane identity drives lap chaining, knives
  and the tiling, so that is *"a run that silently does not happen"*, the exact failure the
  function was rewritten to close. Now fingerprinted on the vertices.
- **`np.allclose(..., atol=PLANE_TOL)`** in the free-end guard kept numpy's default `rtol=1e-5`,
  eleven times the tolerance the call names. Same defect as the one fixed in `measure` the day
  before, in code years older.
- **`_cut` used `PLANE_TOL` as a weld radius**, which *is* the 1 µm lattice — a crossing landing
  one lattice cell from a real corner silently deleted that corner. `WELD_TOL` now, declared in
  `offset.py` rather than imported from `clean.py`, which would breach the shapely containment.
- **`_cross` reconstructed the shared segment's midpoint from a borrowed anchor**, only within
  `tol` of the other plane, so its distance from the true line grew as `tol / sin θ`. It solves
  for a point on the line now. Probed: right answer down to 0.001° either way, but the guard was
  the wrong shape and the fix is cheaper than the reasoning about when it bites.
- `clearance`'s docstring said parts are "concatenated" where the code queries per part and its
  own inline comment gives the opposite reason.

**Not done:** nothing of the four. The turn-down landed on 2026-08-26. The tree is clean apart
from an untracked `audit.py`.

**A fourth `/code-review high` ran over the whole branch after cause 1 landed**, and found six
things. The one that mattered is recorded above: the cheek growth was bounded by a shared plane
rather than by contiguity. The other five are small and all fixed — `_across` indexing `[0]` into
a list a degenerate union triangle leaves empty (now a named refusal); `corner()` dividing by zero
on a seam the solve collapsed, whose NaN went through `NaN < PLANE_TOL` into `lstsq` and would
have written a NaN vertex without raising; `_plane_ids`' new cache stamp not fingerprinting
**winding**, so a `fix_normals()` would leave it looking valid with every id wrong; and two parts
sharing an `o` group name writing one substrate OBJ twice, so one part vanishes from
`reload(substrate=True)` — the very check that path exists for. All five were unreachable on
current paths; four of the five are one line.

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
`skinning/skin/clean.py`, exactly where the 2026-08-21 costing said it should go if it were ever wanted,
and **not** in the rules. See *"The gusset as built"*.

The second half of that question — *should `clearance` stop being the build's verdict first?* —
turned out **not to be a precondition at all**, and that is the useful finding. It stays open on
its own merits and blocks nothing. See the same section.

### What landed on 2026-08-21

Three things, all on top of `07c3e4d`, all in one commit:

1. **`skinning/skin/clean.py`** — the coplanar-overlap pass, built to the spec that stood here and
   measured against it in *"The pass as built"*. `clean(mesh) -> mesh`, its own module, the only
   one that imports shapely and deliberately not re-exported from `skinning/skin/__init__.py`. `build()`
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
8. **`skinning/skin/clean.py`** (2026-08-21) — the coplanar-overlap pass built to that spec,
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

Re-measured again 2026-08-26, after the turn-down landed. Only the cladding on the two bakes with
a scupper moved; the rig and the membrane are unchanged to the digit.

| | separation | membrane / cladding clearance | skins cross | buried |
|---|---|---|---|---|
| rig | 76.071 | 7.7760 / 84.6091 | 0 | none |
| walls-and-caps | 67.018 | 7.8808 / 75.0194 | 0 | none |
| extended cornices (live) | 67.018 | 7.8808 / 75.0194 | 0 | none |

| | coplanar overlap removed, membrane / cladding | triangles | border edges |
|---|---|---|---|
| rig | 53554 / 0 mm² | 33→34 / 29→22 | 25→16 / 23→18 |
| walls-and-caps | 13530 / 2530 mm² | 68→52 / 100→48 | 16→8 / 32→24 |
| extended cornices (live) | 173172 / 2530 mm² | 145→115 / 144→88 | 59→29 / 56→44 |

The cladding's two figures fell 5 mm on 2026-08-26 and **neither is a defect**. The sample taking
the low reading is now the turn-down's own bottom-outer corner at `(8.585, 4.755, 14.580)`, which
stands 75.0194 mm over the headhouse roof taper, where the lining's corner 115 mm inboard stands
79.9703. Same geometry, read at a point that did not exist before. The 2530 mm² is the miter
between the skirt and its turn-down, dissolved by `clean` — see *"The turn-down: a band that turns
keeps its own price"*.

Re-measured again on 2026-08-25 after cause 2 landed. The cladding's 3.6593 mm and the 4.337 mm
separation are gone — both were the scupper knife, and both came right together. **79.9703 rather
than 85 is correct and inherent**, because the reveal's mouth sits on the headhouse roof; see
*"Cause 2 fixed: a knife has a side"*. The **crossings column was blank** when this
table was re-taken on 2026-08-25 and is now filled in by `measure.intersects`, built the same day
— see *"The clearance verdict"*. It reads **2 triangle pairs on both bakes**, on the cheek lining just above
the sill. The suspicion that prompted leaving it blank was right: the old `0 / 0` was
measured before the cheeks were clad, and carrying it forward would have hidden this. Neither skin
crosses itself or the substrate on any of the three.

The first table is measured on the raw emission and is **unchanged** by `clean` — that is the
point of measuring before the pass and writing after it — the second table moved on 2026-08-21
when `_tiling` stopped the cladding covering surface it never meant to. 100 tests, ~5.3 s.
No bake prints a self-intersection warning any more. The cladding's
`WARNING: 21.000 mm inside the requested offset` on the cornice bakes, carried here for weeks as a
**known false alarm**, was nothing of the kind: it was the inverted triangle, and it went when the
tiling was fixed. See *"The notch is fixed at source"*.

### After the pass, in the order they became live

- ~~**The gusset, if Duncan wants the outlet closed.**~~ **Built 2026-08-22**, in
  `skinning/skin/clean.py` as the third opted-in operation with an authored bound, exactly where this line
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

- `skinning/skin/parameters.py` mirrors `bim/phase1/parameters.py` (`load` / `validate` /
  `load_validated`, `ParameterError` naming the field). No `merge` — this rig has no
  separate structure file for numbers to be injected into.
- **The core takes a dict, never a path.** `skins(params)` is where the parameter layer
  stops; below it, nothing has heard of a knob.
- **On migration**: the `classify` / `fall` / `skins` block moves into
  `student-house-parameters.yaml` under `skin:`, the schema fragment is pasted into that
  repo's schema, and the caller passes `topo["skin"]`. `skinning/skin/parameters.py` is then dead
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
  `skins()` binds it, so what `skinning/skin/` receives still has the `Faces -> bool[nfaces]`
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

**Still open, Duncan's call:** nothing declares dependencies. `skinning/skin/parameters.py` adds `yaml`
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
python; this rig does not, because nothing on the bpy side touches `skinning/skin/`.

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
  cladding system across every part, exactly as `current_substrate()` does. `skinning/skin/` still
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
`skin_over`, and `_trim_below` in `skinning/skin/offset.py`. Three things that were decided while
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
| `skinning/skin/offset.py` | the solver. `planar_offset` (one constrained system), `skin_over` (union → offset → select faces → lap → trim), `_lap` / `_across` / `_receivers` (the one continuation rule), `Faces` (what a predicate may ask) |
| `skinning/skin/measure.py` | `clearance` (skin to substrate), `separation` (skin to skin) |
| `skinning/skin/substrate.py` | `polyhedron` (from vertex/face lists), `from_obj` (a baked export, one part per `o` group), `snapped`, `prism`, `cube`, `l_block`, `u_block`, and `classify` / `horizontality` (WALL vs ROOF from shape) |
| `skinning/skin/export.py` | OBJ writer that emits n-gons, not triangles. `write_obj` one per file for `build/`, `write_objs` many as `o` groups for a whole substrate |
| `skinning/skin/parameters.py` | the parameter layer. `load` / `validate` / `check_seeds` / `load_validated`. The only module that imports yaml or jsonschema |
| `skin-parameters.yaml` | every tunable number: `classify`'s thresholds, `fall`, the five distances |
| `skinning/skin/skin-parameters.schema.json` | the JSON Schema it is validated against. **Inside** the package, because every validation path reads it |
| `pyproject.toml` | the package: `skinning`, its six dependencies, and `pythonpath = ["."]` so a bare `pytest` works |
| `skinning/rules.py` | every derivation: the face rules, the `RULES` table, `skins()`, `classifier`, the two `check_*` guards. Migrates |
| `skinning/pipeline.py` | the seam: `prepare` (group → union → `Faces`) and `run` (substrate in, skins out). Reads no file, writes none, prints nothing. Migrates |
| `build.py` | this rig: the substrate as transcribed data, the OBJ emission and the printed report. Stays |
| `blender/display.py` | the only file that imports bpy. Loads, never authors |
| `tests/test_offset.py` | the geometry suite |
| `tests/test_parameters.py` | the parameter-layer suite |
| `tests/test_import.py` | the OBJ import suite |
| `tests/test_clean.py` | the coplanar-union, dissolve and gusset suite |
| `tests/test_measure.py` | the verdict suite: `intersects`, `buried`, `separation` |
| `tests/test_seam.py` | the module seam: `rules`/`pipeline` never import the rig |
| `audit.py` | scratch: every number in the mesh tables below, measured |

## The two skins

Numbers in `skin-parameters.yaml`, face rules in `skinning/rules.py`'s `RULES`, joined by name by
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
- **trimesh is triangles-only.** `skinning/skin/export.py` regroups coplanar triangles via
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
| `skinning/skin/offset.py` code lines | 384 | **561** (+46%) |
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
and it dissolves the facet structure `skinning/skin/export.py` regroups into n-gons.

**It does not close the holes** — measured: the outlet comes through untouched, 6 border edges
before and after, because its two triangles span the `x = 8.5` knife and are coplanar with
nothing. A coplanar pass has nothing to say about it. The pass would be a natural *home* for the
gusset step, but it is a separate mechanism.

**Correction to the line above, measured after it was written:** the pass does *not* dissolve the
facet structure `skinning/skin/export.py` regroups into n-gons — it improves it. The membrane writes 48
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
vertices**, which `skinning/skin/export.py` preserves deliberately so that a neighbouring facet cornering
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
pairwise joint rule. `skinning/skin/offset.py` is unchanged by this section.

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

**The cleanup pass has none of that shape.** Mesh in, mesh out; nothing in `skinning/skin/offset.py` or the
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

- **`skinning/skin/offset.py` — the `out` gate short-circuited the fold as well as the run-on.** Mine, from
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
- **`skinning/skin/offset.py` — the `rounds` net had less headroom than it looked.** A band costs up to
  **four** entries in `tried`, not two: two ends, and a run-on moves the end it lengthens so that
  end is asked again under its new key. Against `rounds * len(segs)` the rig already measured
  2.00, so a substrate whose laps run on at both ends would trip a raise that blames the geometry
  for a correct model. The bound is `rounds * 2 * len(segs)` now, with the ceiling written down.
- **`skinning/skin/offset.py` — `drip_at` was silently wrong with no vertical face at the vertex.**
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

`skinning/skin/clean.py`, `clean(mesh) -> mesh`, ~150 lines with its docstrings against the prototype's 64.
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
`skinning/skin/export.py` keeps them on purpose, because dropping one that a neighbouring facet corners on
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

- **`skinning/skin/clean.py` is the only module that imports shapely**, and `clean` is deliberately **not**
  re-exported from `skinning/skin/__init__.py`: `import skin` must not require it. `build.py` imports
  `skin.clean.clean` directly. Same containment as yaml and jsonschema in `skinning/skin/parameters.py`,
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
the cladding on the live bake; `skinning/skin/clean.py`'s `_sheets` already finds them, but it is the wrong
place to fix them, because by then the substrate face they came from is gone.

**Do not "fix" this in `clean`.** Its job is what the plane is covered by; it cannot know that a
particular covered sliver was never wanted. The notch will come back symmetric when the offset
stops inverting triangles, and not before.

## The notch is fixed at source, and `clearance` was right all along (2026-08-21)

Duncan, on the diagnosis above: *"Fix it."*

`skinning/skin/offset.py` gains `_tiling`, run on the kept faces before any lap is placed. A face whose
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
  `skinning/skin/offset.py` keeps the dependency it had.

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
with nothing buried in anything. In `skinning/skin/clean.py` it is not: `build()` **measures the raw
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
pinch is produced by the rules and not by hand. 110 tests, ~6.6 s. `skinning/skin/offset.py` and `RULES`
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

## The turn-down: what is actually in the way (2026-08-25)

*(Built on 2026-08-26 — see "The turn-down: a band that turns keeps its own price". Everything
below still reads true except the construction, which the build replaced with a simpler one, and
the search for a gate, which ended somewhere this section did not expect. Kept because it is the
diagnosis the build was written from.)*

**Attempted, reverted, nothing committed.** What follows is what the attempt established, so the
next session starts from here rather than from the guess this file used to carry.

Duncan, having read the built bake back: *"Apart from the missing skirt turn-down the geometry is
accurate as is."* So the square 230 mm notch that cause 1 produced is **right**, and his
2026-08-22 *"V62 should remain where it is"* — which put the rim at `y = 4.785` — is superseded.
Do not restore the 400 mm rim or the diagonal.

### It is not missing code. It is switched off.

The arris the turn-down springs from **already qualifies** in `_lap`'s seam loop: the slot's cheek
is `covered`, the parapet's inner face is `lappable` and uncovered. But `_across` returns a
**horizontal** direction there, so `reach` prices the band at `out` — and the cladding declares
`out: 0.0`.

This file said the opposite, in *"The cheek lining is wrong"*: *"What is **not** the blocker, so
nobody needs to raise it: `out: 0.0`. That gate is on the run-on alone."* **That is wrong.** There
are two `reach` gates; the one in the seam loop is the live one, and it is the whole of why the
skirt stops at the slot.

Verified as a what-if — a full copy of the parameter file, per the documented discipline — with
`out: 0.115`. The turn-down **appears**, at `y 4.755…4.870` and `y 5.100…5.215`. Two things came
with it, which is why authoring `out` is not the answer: the band stops at `z = 14.603`, 23 mm
above the sill's offset at `14.580`; and the drip's rim reverts from square at `4.870` to a miter
running out to `4.755` — the geometry Duncan had just approved. (`check_seeds` also refuses
`0.2`, as 25× the membrane's `0.008`.)

### Duncan's decision, 2026-08-25: option B

Put to him as A (author the cladding an `out`) or B (**a band that turns keeps its own pricing
instead of being re-priced by its direction**), he chose **B**. It leaves `out: 0.0` alone and does
not disturb the rim. It does revise his own dichotomy — *"down is a drip, up or sideways is an
upstand"* — by saying that dichotomy prices a lap that **starts**, and is the wrong question about
one that merely turns a corner.

### The construction is solved. Record it.

A band's quad is `seg(V[a], V[b], root(a) + step, root(b) + step, …)` — from the **skin's own
edge** to the outer line. That is why the skirt reads 112 mm deep on a 30 mm `drop`: `85 + 30`,
less the coping's slope. Three things follow, all confirmed by measurement:

- **Price the turned band by the band it continues** — `drop`, not `out`.
- **Root it on the substrate**, with `drip_at`, as a drip is. The datum is a property of the band,
  not of the direction it happens to run in.
- **`drip_at` must exclude the plane the band steps away from.** Offsetting out along a plane's
  normal and then stepping back along it are the same displacement counted twice. For a drip this
  excludes nothing — the step is vertical and no skinned wall is horizontal, so no drip moves by a
  bit — but the turn-down steps horizontally and its arris lies on a skinned vertical plane facing
  exactly that way. Mitered onto it, the band is set out from a line 85 mm *inside* the opening
  instead of from the opening's own edge. Without this it comes out 30 mm wide; with it, `115 mm`
  (`y 4.755…4.870`), which is what the what-if independently produced.

### What defeated it: the gate, not the geometry

The test for *"this arris is the same band turning"*. Two versions, both **over-firing at building
corners rather than at the scupper**:

1. *Shares a vertex with a placed band on the same receiving plane.* Fires at every corner where a
   drip's arris ends. Cladding `clearance 79.9703 → 30.0000 mm`, separation `71.973 → 22.000`.
2. *…and no band exists at that vertex on another plane.* Intended to say "the band already
   carries on out of the plane, so it must not also turn within it". **Made no difference** —
   still 30 mm. The assumption that a corner's two drips share a union vertex index was not
   checked before it was coded, and is the likely reason.

Both leave spurious sideways bands 30 mm off the substrate at `(8.05, 2.935, 13.07)` and
`(10.595, 7.57, 13.07)` — the Unit8 and Headhouse wall ends, nowhere near the scupper. Also two
failing tests, `..._complementary_walls_and_never_meet` and `..._cut_at_its_datum...`.

### The reading to start from

At a building corner the drip's arris ends and a perpendicular arris meets it there **exactly as
at the scupper** — the two are indistinguishable by anything local to the vertex. What differs is
that at the corner the band is *already continuing*, onto the next wall's plane, because
`drip_at` solves their shared arris on both planes at once; at the scupper it has nowhere to go,
the only neighbour being a covered cheek.

So the rule wants to be **"a band turns within its own plane only where it does not carry on out
of it"** — the priority `carry_on` already applies, with turning read as a *fourth* answer after
run-on and fold. That places it **in `carry_on`, not in the seam loop**, because only `carry_on`
knows a run has failed to continue. This file has warned against "a fourth case bolted onto the
stop condition" — that warning was written before any of this was measured, and the measurements
now argue for exactly that shape.

Two things to check before writing any of it, both of which the failed attempt skipped:

- whether a building corner's two drip bands actually share a union vertex index, or only a
  position;
- what `_room` reports along the turned direction at the corner, since a band that has no room is
  refused anyway and may need no gate at all.

## Cause 2 fixed: a knife has a side (2026-08-25)

**All four of Duncan's corrections now hold.** The cheek lining is his target quad exactly, on
both cheeks:

```
(7.995, 4.87, 14.84009) ── (8.585, 4.87, 14.819018)      the coping, sloped
(7.995, 4.87, 14.580)   ── (8.585, 4.87, 14.580)         the sill's offset, flat
```

...plus `(8.585, 14.707)`, the skirt's outer edge, which he said stays.

### The question this step posed, and the answer

*"Whether an uncovered face's plane should still constrain a vertex when it pulls it inside
`distance` — the same test `_trim_beside` makes, applied at solve time to a plane instead of after
the fact to a triangle."* Written as a candidate and measured, as this file said to. The answer is
**yes — but the test is not "inside `distance`", it is "the far side of a knife", and the side is
read per body.**

Three versions were built and measured, and the two that failed are why the third is shaped as it
is:

1. **Drop the plane of any knifed face, everywhere.** Broke 18 tests: a knifed face is an ordinary
   face along the rest of its length, and stripping its plane leaves vertices nowhere near the
   contact under-constrained.
2. **Drop it only at the vertices the knifed face shares with its covered mate.** Narrow enough to
   pass, and it fixed v67 — `z 14.5036 → 14.585034` — but **not v66**, which is where the defect
   actually was. v66 carries the taper's end face and *not* the parapet's inner face, so it shares
   no vertex with the mate and the knife's own "touching" test never reaches it. The bottom edge
   still kinked at `x = 8.415`.
3. **Substitute the mate's normal instead of dropping the plane.** The vertex still *lies on* that
   plane — what is wrong is only which way it offsets. Substituting keeps every vertex exactly as
   determined as it was, needs no arbitration, and reaches the vertices where only the far face is
   incident. That is v66, and it moves to `x = 8.585`.

### Per body, and this is the load-bearing part

Version 3 fixed the cladding and **broke the membrane**: `clearance 7.8808 → 0.2732 mm`, 10
crossings into the substrate, 2 samples inside a part. Reading which side a skin is on **per
face** says the wrong thing whenever one skin covers both sides of the knife — and that is the
ordinary case here, because the membrane runs over the roof taper *and* laps down the parapet's
inner face. Face-wise it looks like the parapet's side, and it got pushed 8 mm into the parapet.

Per **body** separates them with nothing authored: a skin is on the far side of a knife only if it
dresses **nothing** of the body that face belongs to. The cladding covers no face of
`Roof_Headhouse_InsulationTaper.1`, so the taper's end plane is read from the parapet's side. The
membrane covers its top, so the rule does not fire for the membrane at all — its numbers are
character for character what they were.

### Measured

| | before | after |
|---|---|---|
| cladding clearance | 3.6593 mm | **79.9703 mm** |
| skin separation | 4.337 mm | **71.9734 mm** |
| membrane × cladding crossings | 2 | **0** |
| cladding folds (live) | 4 | **2** |
| membrane, everything | — | unchanged |

Zero crossings, nothing buried, no self-crossings, on all three substrates. The build prints no
warning anywhere.

**79.9703 mm is not 85, and that is correct.** It is the figure this file derived from Duncan's own
target quad before any of it was built — the reveal's mouth sits directly on the headhouse roof,
so no correct panel can stand 85 mm off everything there. `clearance` cannot tell that from a
fold, which is exactly why it was demoted to a printed number three days ago. Had it still been
the verdict, fixing cause 2 would have *started* a warning rather than ending one. The generic
per-skin clearance assertion in `test_import.py` therefore exempts the cladding on this bake, and
says that this is geometry rather than a defect.

`_trim_beside`, backed out on 2026-08-25 as treating a symptom, is **not** wanted back: the miter
it cut is now correct where it stands.

### What review caught in it

`/code-review high` found seven things, all verified and fixed. The one worth recording is a
**comment describing the mechanism that was rejected**: the block in `planar_offset` still said
*"supplies no plane at all"* and *"narrow to the vertices the knife actually touches"*, which is
version 2 above — and a maintainer who implemented what it prescribed would have restored the
3.6593 mm clearance. That is the documentation-asserts-what-the-code-does-not failure CLAUDE.md
names as invisible to a test by construction, written **while** the measurements that disproved it
were still on screen. The comment now states the substitution, that it reaches every vertex of the
far face, and the consequence of that reach.

The other six: `_knifed` credited with reading the knife's side, which `_knife_side` does;
`planar_offset`'s new `owner` argument undocumented, where omitting it silently reverts the
geometry; a stale comment in `cladding_faces` still asserting the cheek geometry is wrong;
`_opposed` dividing a zero-length normal to NaN, which compares False and so *misses* the
contradiction it exists to catch; `_cut`'s unit-normal precondition unstated while its docstring
invites new callers; and `measure._candidate_pairs` allocating the whole n×m×3 box comparison,
which the live bake never notices and the student-house's ~80 parts would — a 20 000-triangle
self-test would want ~2.4 GB per intermediate. It is evaluated in row slices now, which changes no
answer.

## Cause 1 fixed: the cheek set grows up the stack (2026-08-25)

Duncan's corrections 1 and 2 — *"V5 should be at V4, V52 should be at V49"* — are satisfied
exactly, on both cheeks:

| | wanted | built |
|---|---|---|
| head, west | `(7.995, 14.84009)` | `7.995, 14.84009` |
| head, east | `(8.585, 14.819018)` | `8.585, 14.819018` |

### What it was, and what was not done about it

The slot cuts through the cap plates as well as the parapet, and this cap is **two bodies** split
by the slot — `CapPlate-Headhouse-E` and `E2`. `_opening` pairs cheeks per body and each plate has
exactly one reveal, so neither reveal ever became a cheek and the lining stopped at `z = 14.718`,
34 mm below the coping. Union faces 198/199 and 200/201 read `cheek False`.

**The per-body pairing is untouched**, which was the whole difficulty: its docstring rules
per-element out for two independent reasons that both still hold — group by element and the two
plates' reveals face each other so the coping reads as a cheek pair, *and* the cornice's two ends
become an away-facing pair on the sill's own region so the sill reads as a thickness. So the fix
is not to the pairing but **after** it: a vertical face reached from a cheek by walking adjacency
**without leaving its plane** is that cheek continuing. It runs to a fixed point, so a stack
deeper than one lift follows. Nothing authored.

**Contiguity is the bound, and the first version got that wrong.** It grew on the shared plane
plus a plan overlap, with nothing requiring the two regions to touch — which `/code-review high`
correctly named as the `_meets_region` mistake reintroduced: *"a building shares a plane right up
a stack… matching on the plane once turned the membrane's parapet skirt out into thin air"*. It
was inert on all three bakes, because those four faces are the only ones in the whole union
sharing a cheek plane — and an inert-today wrong rule is exactly what this file exists to catch.
The walk crosses the parapet/plate boundary because the two genuinely are one surface there —
union face 198 is adjacent to cheek 255, 199 to 198, 201 to cheek 258, 200 to 201 — and stops at
the edge of it because there is nothing coplanar to step onto. The plan-overlap arithmetic went
with it, and a second finding about comparing projections taken along two regions' own normals
went with that.

### The ordering that matters, and it was measured

The growth runs **after the floor is computed**, and that is not incidental. A grown cheek reaches
*above* the coping the slot cuts through, and the floor test asks whether a cheek stands over an
upward face. Grow first and the wall's own coping becomes the floor of an opening — which
`cladding_faces` subtracts, so the coping would silently leave the cladding. Checked before the
line was written.

### What it caught, exactly

Four faces on the live bake and nothing else: 198/199 on `CapPlate-Headhouse-E` (plane 39, +y) and
200/201 on `E2` (plane 40, −y), both spanning `x 8.080…8.500`, `z 14.718…14.752`, directly above
the parapet's own cheeks on the same planes. Those four are the *only* faces in the whole union
sharing a cheek plane, so there was nothing else for it to sweep. Floor unchanged at three faces.

### What moved, and what did not

Both skins take the cheeks, so the membrane grew them too and now **covers** those reveals where
it used to lap onto them: its coplanar overlap falls 69945 → 13530 mm² on walls-and-caps and
226868 → 173172 mm² on the live bake, raw triangles 76 → 68 and 153 → 145. The rig has no opening
and does not move by a bit. The verdict is unchanged on all three: nothing buried, no
self-crossings, no crossings into the substrate, and the same **2** skin-to-skin pairs — which are
cause 2 and were never this.

### What is still wrong, and it is now isolated

The lining's **bottom** edge. It should run flat at `z = 14.580` from `x = 7.995` out to `8.585`;
it kinks at `8.415` and dives to `14.503618`. Those are exactly v66 and v67 — **cause 2**, the
scupper knife — with nothing else left on top of them. `clearance` still reads 3.6593 mm and the
two skins still cross at 2 pairs, both for that one reason.

## The clearance verdict (2026-08-25)

Duncan, asked the standing question and given four options: **"Take D."** So `clearance` is
demoted to a printed number, and what `build.py` asserts is now `measure.intersects` (does a
surface pass through another) plus `measure.buried` (is a sample inside a part).

### Why it had to be answered now rather than later

The `_trim_beside` revert brought the warning back at 3.6593 mm. That reading is **right** — it
names cause 2. But it would not have gone away when cause 2 was fixed: Duncan's own target quad
samples at **79.97 mm against an 85 mm offset**, inherently, because the reveal's mouth sits
directly on the headhouse roof and no correct panel can stand 85 mm off everything there. A
verdict that fires on the geometry you asked for is one nobody reads, which is how the cornices
warning sat in this file as a "known false alarm" for weeks while being **correct**.

### What the two checks are

`intersects(a, b)` counts the **triangle pairs that pass through each other**, by Möller's method:
two non-parallel planes meet in a line, each triangle meets that line in an interval, and the
pairs cross when those intervals overlap in **positive length**. `buried(parts, skin)` counts the
samples — vertices and face centroids, the same ones `clearance` takes — that lie inside a part,
which is the signed half `intersects` cannot give.

**It was written twice, and the first version was wrong in two ways that a review caught.** Both
are worth keeping because both are about the same thing: deciding a crossing from *edge-piercing
tests* forces a choice at the triangle's boundary, and there is no right choice.

- Excluding the boundary misses every crossing that passes through a shared edge of the other
  mesh. Two boxes overlapping in a quadrant read **zero** — and axis-aligned geometry on a 1 µm
  lattice produces exactly that shape, so this was not a corner case here.
- Including it reads a **graze** as a crossing: a surface resting along another's boundary edge
  read 6 on a hand-made pair.

The interval overlap has no such choice to make, and that is why it replaced the edge test rather
than being tuned. Two further things it still has to get right, both measured:

- **Sharing a segment is not passing through one.** Two triangles meeting along a common edge
  share its whole length and penetrate nowhere — a box resting on a box, a lap landing flush on
  the face it laps onto. So the shared segment's midpoint must be clear of all six edges: interior
  to **both** triangles, not either. `either` reads the graze above as a crossing again.
- **Coplanar is decided by distance, never by the angle between the normals.** A sliver's normal
  is noisy where its vertices are not: the clean pass leaves a 0.13 × 275 mm triangle in the
  membrane whose normal is **1.4e-11** off its plane's, and any angle threshold tight enough to
  mean anything reads that as two planes meeting in a line — then two coplanar overlapping
  triangles come back as a crossing. Three bogus self-crossings on the live bake, which is
  CLAUDE.md's *"do not tighten them"* arriving for the second time. The test is `|d| <= tol` on
  the corners against the other's plane.

**What it gives up, stated plainly.** Requiring the interior of both misses a crossing whose
intersection curve runs along mesh edges *the whole way* — two boxes of identical cross-section
slid along one axis read zero, measured. That needs the curve to follow edges of **both** meshes
at once, where the edge test failed on the far commoner case of one. `buried` covers the substrate
side of it regardless, being signed and exact.

The self-test skips only pairs sharing an **edge**. Skipping every pair with a corner in common
made it blind to 553 of the live membrane's 1157 candidate pairs — and a lap folding back through
the panel it springs from shares exactly the arris vertex with it. A pair merely touching at that
corner overlaps in zero length, so nothing needs special-casing.

### What it measured, and the thing nobody had checked

| | membrane self / vs substrate / buried | cladding, same | membrane × cladding |
|---|---|---|---|
| rig | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| walls-and-caps | 0 / 0 / 0 | 0 / 0 / 0 | **2** |
| extended cornices (live) | 0 / 0 / 0 | 0 / 0 / 0 | **2** |

Triangle **pairs**, so the count depends on the tiling where the fact of a crossing does not. Only
zero-or-not is the verdict.

**The two skins cross, and until now nobody had measured it.** The `crossings` column in the table
above carried `0 / 0` forward from before the cheeks were clad; the revert commit left it honestly
blank for exactly this reason, and the blank turns out to have been the right call. The crossings sit on the cheek lining's two planes — `y = 4.87` and `y = 5.1`, the offsets of
the two cheeks — at `z = 14.50796`, just above the sill:

```
(8.575337, 4.87, 14.50796)   (8.585, 4.87, 14.50796)
(8.575337, 5.10, 14.50796)   (8.585, 5.10, 14.50796)
```

That is **cause 2** again, seen from the other side: the raked bottom edge cuts down through the
membrane lining the scupper. Which is the argument for the new verdict made for it — it fires on
the real defect, names where, and will go to **0** when the knife is fixed, where `clearance`
would have gone on warning at 79.97 mm forever. `test_import.py` pins it for now.

The verdict is taken on the **written** mesh as well as the raw one, which is the one place this
departs from measure-raw/write-cleaned. Everything printed above a verdict is a property of the
offset and stays on the raw emission; a verdict is a statement about what ships, and `clean`
invents a gusset — surface that is, by the module's own words, *"not the offset of any substrate
face"*. A gusset spanning a tear across a substrate feature would otherwise go out unexamined.
The two agree on all three bakes today.

### What it does not do

It gives up detecting a surface that is merely **too close** — nearer the substrate than
`distance` without crossing anything. That is a real loss and it was Duncan's to accept: option C
(keep the verdict against a per-skin authored floor) was the alternative, and it was rejected
because the floor would be a judgement about intent rather than a fact about the geometry, and
would need re-authoring on every substrate change. `clearance` still prints, so the number is
still in front of you; it just no longer decides.

## The cheek lining is wrong, and what it is (2026-08-22)

Duncan, reading `build/Cladding.obj` back in Blender on the live bake, on the **north** cheek:

> *"The geometry is incorrect. At the north cheek for example, V52 should be at V49, V5 should be
> at V4. V62 (on the skirt) should also be on the cheek plane (y=4.87). E72 should be at the
> height of V6 and extend to x=8.585."*

Vertex numbers are the exported OBJ's own order, which is what Blender shows: `skinning/skin/export.py`
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

*(Superseded 2026-08-25 — see "The turn-down: what is actually in the way". The reading below is
what was believed before it was measured, and it is wrong about the blocker.)*

**It is not the fold `_lap` already places, and that is the whole difficulty.** A fold turns onto
the *departing* face — here the cheek, plane `y = 4.870`. This return stays in the skirt's **own**
plane, `x = 8.585`, and runs down it. None of `carry_on`'s three answers at a free end covers
that: the same plane carries on, another face meets it at an arris, or nothing.

~~What is **not** the blocker, so nobody needs to raise it: `out: 0.0`. That gate is on the run-on
alone and deliberately so — a fold is priced by `reach(into)` and bills `drop` when it turns
downward, precisely so the cladding is not denied every corner it turns.~~ **Wrong, and measured
wrong on 2026-08-25.** There are two `reach` gates. The one in `_lap`'s **seam loop** prices every
arris before any of `carry_on` runs, and `out: 0.0` there is exactly what stops the turn-down —
the band leaves that arris horizontally. Setting `out` in a what-if makes the turn-down appear.

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
2. ~~**Cause 1**, the lining stopping at the parapet.~~ **Done 2026-08-25**, and the derivation
   proposed here is the one that landed unchanged: *grow* the cheek set — a vertical region on the
   same plane, facing the same way as a cheek already found and overlapping it in plan, is that
   cheek continuing. `_opening`'s per-body pairing is untouched. See *"Cause 1 fixed: the cheek
   set grows up the stack"*.
3. ~~**Cause 2**, the knife.~~ **Done 2026-08-25** — see *"Cause 2 fixed: a knife has a side"*.
   The candidate this step asked for was written and measured, and the answer to its question is
   **yes, but per body**. Original text follows.

   **Cause 2**, the knife. `_reconcile` and the most delicate thing in the module, and the one
   that decides whether `_trim_beside` ever comes back. Be precise about which vertex is which:
   only **v67** is `_reconcile`'s doing. **v66** is not a contradiction at all — its planes are
   not opposed and the parapet's east face does not touch it. It is the "solved over the whole
   body" invariant working as written, with the roof taper's end plane pulling the vertex 85 mm
   *inward*. The question v66 poses is whether an uncovered face's plane should still constrain a
   vertex when it pulls it inside `distance` — the same test `_trim_beside` makes, applied at
   solve time to a plane instead of after the fact to a triangle. Write it as a candidate and
   measure it; do not design it further on paper.
4. **The turn-down.** The last of the four. Attempted and backed out on 2026-08-25, then
   **built on 2026-08-26** — see *"The turn-down: a band that turns keeps its own price"*. The
   framing in this list, and in the paragraph on correction 3 above, is superseded by it.

## The turn-down: a band that turns keeps its own price (2026-08-26)

**Built and landed.** Duncan's step 4 and the last of the four cheek corrections. The skirt now
turns down each side of the scupper: a band 115 mm wide on `x = 8.585`, from the coping's offset
at `z = 14.819` down to `z = 14.585`, mitered into the drip it continues at `(y 4.755, z 14.707)`,
and not returned across the bottom. Mirrored at `y 5.100…5.215`. That is *"the skirt should turn
downwards on each side of the scupper"* (2026-08-22) as asked.

The 115 mm is 85 across the reveal it laps out of plus its own 30 mm drip, which is the width the
2026-08-25 what-if independently produced from the other direction.

**The bottom took two goes.** The first build stopped at `z = 14.585`, because that is where the
band's *receiving* face stops: the parapet's inner face is buried by the roof taper's end below
`z = 14.5036`, 8.6 mm above the sill, so `v67` is the last arris vertex the receiving plane has.
The lining beside it reaches 14.580 (`V[66]`), which left a 5 mm sliver open where the two meet.
Duncan, shown it: *"E84, 86 should be 5 mm lower, even with E70, 71."* See *"The band runs to the
end of the arris"* below — it now reads 14.580 on both sides.

### The two checks the previous attempt skipped

Both were named in that section, both were measured first, and both mattered.

**A building corner's two drips share a union vertex index**, not merely a position. On the live
bake: v13, v26, v51, v82, v113, v124, v130 each carry two drip bands on two planes, and each band
takes its seam endpoint from the same index, so `inner()` hands both the identical offset point.
That means `carry_on`'s existing free-end guard — *"a run is only free at its end if nothing else
turns the same way there"* — already fires at every corner and at neither side of the scupper. The
failed gate over-fired **because it was in the seam loop**, which runs before any of that and
knows nothing about runs. Moving the question into `carry_on` was the whole of the fix the
previous section predicted, and it cost no gate of its own.

**`_room` along the turned direction** reads 1934.9999 mm at v71 and v72 and **0 mm at v67**, the
lower corner, because the roof falls toward the scupper and its line rises away under the band —
by 4.96 mm over the band's 115 mm, and 1.29 mm over the 30 mm that actually laps the substrate. So
`_room` refuses the corners nowhere and refuses the lower half of the turn-down. Asked at both
ends the way a lap that *starts* is, the turn stops 138 mm above the sill.

That moved where it is asked rather than whether: **at the end the band arrives from**. A turned
band follows the boundary of the face it laps onto, so its far end sits on that boundary, and
requiring the boundary to carry on past its own corner is the wrong question.

Be honest about what that costs, as `/code-review high` was on 2026-08-26: it is a **weaker**
guard, not a differently-aimed one. `_room` at the far end answers *"the face corners here"* with
the same zero it uses for *"the face runs out here"*, and nothing in the code separates them — so
the far end is not guarded at all, and a receiving face that genuinely stopped short there would
take a band hanging over nothing. That contradicts *"a continuation runs only where the whole of
it lands on substrate"* in the direction of laxity. No substrate here poses it, and the repair on
offer is a threshold on how far short is tolerable, which is not a derivation. Named as a limit
instead.

### The measurement that settled the gate, which nobody had asked for

There are **four** free drip-run ends on the live cladding with a deferred arris at them, not two.
Besides the scupper's `v72` and `v74` there are `v42` at `(8.08, 2.85, 13.096)` and `v116` at
`(10.68, 7.54, 13.096)` — which are exactly where the 2026-08-25 attempt left its two spurious
bands. Nothing local to those vertices distinguishes them from the scupper: each is a covered face
meeting the receiving plane at right angles at a free end of a drip run.

What distinguishes them is **which way the covered face looks**. At the scupper the lined cheek
faces *back* along the turn, so the skin's own edge stands 85 mm on the far side of the arris and
the band spans the gap: `gap = (substrate arris − skin edge) · t = +85 mm`, width `85 + 30`. At
`v42` the covered face is `Headhouse-E`'s facade and it faces *along* the turn, so the skin
already stands 85 mm out that way: `gap = −85 mm`, width `−55 mm`, and the outer line falls behind
the edge it would spring from. There is no band, and refusing a negative width is the entire gate.

It is not a special case bolted on. The band is *defined* as running from the skin's own edge to
`drop` past the substrate arris; a negative width is that band not existing. Where `drop` is the
longer of the two the width is the difference, which is exactly the part of the drip the skin does
not already cover — pinned by the second new test, which runs one substrate at two drops.

**It bites on a drip and nowhere else**, which `/code-review high` found the same day and which
this section originally overstated as *"the entire gate"*. The test is on the **datum**: a band
measured from the skin's own edge has no gap to close, its width is `want` whatever the arris
does, and the check reduces to `want > 0`. Demonstrated by the review with a cladding of
`drop: 0.0, out: 0.03` — the turn then fires at `v42` and `v116`, the two vertices the gate exists
to refuse, each passing at `+0.03`, and the band it places is a 30 mm flange on `y = 2.935` at
`x 7.965…7.995`. Left as it is rather than repaired: every turn on all three substrates today is a
drip (the cladding's; the membrane defers nothing to turn onto), so what a turning **upstand**
should be refused at is undecided, and inventing the answer here would be guessing at a case no
substrate poses. Worth revisiting the first time one does.

### The construction, simpler than the one recorded

2026-08-25 recorded three moves: price the turned band by the band it continues, root it on the
substrate with `drip_at`, and make `drip_at` exclude the plane the band steps away from. The first
is right and is what landed. The other two collapse into one line:

```python
gap = (body.vertices[v] - V[v]) @ t if drip else 0.0
return V[v] + (gap + want) * t
```

The outer line lies `want` past the substrate arris along `t` and stays on the skin's own edge in
every other direction. Measuring the gap **along `t`** is what strikes out the plane the band
steps away from — it cancels the offset component along `t` whatever produced it, which is
precisely what excluding that plane from the miter was for. And keeping the other components on
the skin's edge is what the recorded construction was missing: `drip_at` leaves `z` on the
substrate, so `drip_at(72) + step` puts the band's outer corner at `z = 14.737` against an inner
edge at `14.819` — an 82 mm skew, a flap rather than a strip.

**It is deliberately not applied to a drip that starts**, although the two agree along `t` by
construction for every downward drip (`drip_at`'s displacement is horizontal, so its `z` is the
substrate's). They disagree in **plan**, and the rig is where: at four cladding drip ends, `V` is
mitered onto a vertical plane that `skinned_wall` does not contain, and `drip_at` is not — 85 mm
apart. Measured over every drip end on all three substrates before deciding: the two agree to
`0.000 nm` on unit8 and headhouse and to `1.2 nm` on the rig's membrane, and differ by `85 mm` at
four of the rig's cladding drip ends. So unifying them would have moved the rig, and the rig is
not moved.

### What it cost, and what it did not move

Two lines of build output change, on the two bakes that have a scupper, and nothing else:

```
-  clearance 79.9703 mm | cleaned: 0 mm2 of coplanar overlap removed, 24 collinear vertices dissolved, 132 -> 84 triangles, 56 -> 44 border edges
+  clearance 75.0194 mm | cleaned: 2530 mm2 of coplanar overlap removed, 26 collinear vertices dissolved, 144 -> 88 triangles, 56 -> 44 border edges
```

The **rig is untouched** and the **membrane is untouched on all three substrates** — every
residual, clearance, fold count and separation figure is unchanged, to the digit. The membrane
cannot reach the rule at all: it authors `out: 0.205`, so its seam loop defers nothing and there
is nothing for a turn to continue onto. The build warns on nothing on any of the three.

`clearance` falls 79.9703 → 75.0194 and the separation 71.973 → 67.018, and **neither is a
defect**. The sample taking the low reading is now the turn-down's own bottom-outer corner at
`(8.585, 4.755, 14.580)`, which stands 75.0194 mm over the headhouse roof taper, where the
lining's corner 115 mm inboard — the old low sample — stands 79.9703. It is the same geometry read
at a point that did not exist before, and it is the documented `clearance` exception again: the
reveal's mouth sits on the roof, so no correct panel stands 85 mm off everything there. Both
figures are re-pinned in `test_the_baked_headhouse_reads_and_skins`.

The 2530 mm² is **two bowties**, and they are the miter behaving as designed rather than a defect.
The drip's outer line is 112 mm below its seam while the first link of the turn is 101 mm long, so
the corner where the two outer lines meet falls past that link's far end and its quad crosses
itself. `clean` dissolves it and the summed area comes back exactly equal to the area covered.
The cladding's *old* pair of bowties had a different cause — a tiling the offset inverted — and
stays fixed at source by `_tiling`. `/code-review high` flagged that `skin_over` therefore returns
a raw mesh with a self-crossing outline in it, where `_retiled` and the ear clipper treat exactly
that as a hard error. The inconsistency is real and it is **older than this change** — the
membrane has shipped four of them since 2026-08-21, and `build()` measures raw and writes cleaned
precisely because of it. The repair on offer, clamping the miter parameter to the shorter of the
two links, would move those four as well, so it is not a change to make while landing a turn-down.

Live bake, after. From `build.py` (`dissolve=True`): membrane 145 → 115 triangles and 59 → 29
border edges, cladding 144 → 88 and 56 → 44. From `audit.py`, which calls `clean` with
`dissolve=False` and so reports different counts for the same meshes: membrane 145 → 142 and
59 → 38, cladding 144 → 130 and 56 → 54, T-junctions 15 → 0 and 6 → 4. **Do not quote one as the
other** — an earlier draft of this section did, and a reader re-running `audit.py` to check would
have read a regression that is not there (`/code-review high`, 2026-08-26). Three new tests, 124
in ~8 s.

### The band runs to the end of the arris

Duncan, shown the first build: *"E84, 86 should be 5 mm lower, even with E70, 71."* E84 and E86
are the turn-down's bottom edges, `z = 14.585`; E70 and E71 the cheek lining's, `z = 14.580`.

**Why it stopped short.** The turn walks arrises at its free end, and an arris is a candidate only
where the face beyond it is one the skin may lap onto. At `v67 = (8.5, 4.785, 14.5036)` the
receiving face runs out: the parapet's inner face is buried by the roof taper below that level.
The edge `v66`–`v67` that carries on down to the sill is shared by the cheek — **covered** — and
by `f91`, the taper's end face on plane 16, which is `x = 8.5` facing the other way. That is the
scupper knife, and `_knifed` refuses it by name, correctly: a lap *onto* a knife has no offset for
its vertices.

**Why the band may run there anyway.** It is not lapping onto that face. It stays on its own
receiving plane, and `_knife_side` has already put `V[66]` and `V[67]` on the covered side of the
knife — both at `x = 8.585`, which is cause 2's fix from 2026-08-25 doing exactly what it was
built to do. So the offset surface carries on even though the substrate face does not, and the
band follows the **covered** face, because the band is that face's flashing. The seam has to lie
on the band's own offset plane at both ends, which is the test the fold already makes and is what
would refuse this if `_knife_side` had chosen the other side — the vertices would be 170 mm away.

Three things bound it, and they are what stop it reaching into the rest of the model:

- **only a band that has itself turned.** The three older answers are what a band that has not
  turned gets; without this the rule would reach for an arris at the free end of every drip.
- **the seam must be crossways to the band.** An arris running along the lap direction is the
  band's own outer edge, not its next seam.
- **`_room` is not asked, and cannot be.** The receiving face is by definition absent past its own
  corner, so asking would refuse every continuation this exists for. What stands in for it is the
  offset-plane test above. This is the same limit `/code-review high` named for the turn itself,
  reached deliberately rather than by omission.

The chain then stops at `v66` on its own: the only other arris there is the cheek's bottom edge,
which runs along the lap direction and is refused as the band's own outer edge.

Pinned by `test_the_skirt_turns_down_to_the_sill_on_the_live_bake`, on the bake rather than on a
synthetic rig. A miniature of this shape raises in `_reconcile` — the knife is the point of it —
unless the lap predicate is contrived to dress one side and not the other, which is the bake's own
condition and not a general one. Both sides asserted, because defects here have read correctly on
one side and not the other before.

### What is deliberately left

**A skin that authors a non-zero `out` gets the seam loop's upstand at that arris, not a turn.**
The rule revives only an arris the seam loop declined *for price*, so `out: 0.0` is what exposes
it. That keeps `_room`'s all-or-nothing intact for every band the seam loop actually considered,
and it is the honest limit: a skin that says it laps sideways is taken at its word. It is also
what makes the membrane provably unmoved. If a future skin wants both, the question to ask is
whether the seam loop should defer *every* candidate that turns out to continue a band — which is
the gate this section spent two sessions failing to write, and it should not be reopened without a
substrate that needs it.

## The masonry skin: a cornice at the top says the wall is clad on its own account (2026-08-26)

Duncan, re-opening the separate east-facade cladding:

> A vertical exterior wall with a cornice at the top (excludes scupper cornices) is clad with a
> separate skin at a seeded offset. Look up the seed from the student-house parameters file
> (allowance is the term we used). E48,31 in the current bake will no longer be angled and instead
> drop straight down. The cornice is also full width, if that is more convenient than cornice at
> the top.

This **replaces** the plan recorded above of naming the east facade by its `-X` normal and its
proximity to `x = 0`. That plan was always in tension with *"cladding system is authored, not
derived"*; this one is not in tension with it at all, because the cornice does not say what the
wall is clad **in**. It says the wall is clad **on its own account**, at its own allowance. Which
masonry — brick on the street front, block on the firewall — stays a material on the part.

### The seed, and a cross-check nobody set up

`cladding.allowance.street-front: 0.15` — "brick veneer + cavity"
(`student-house-parameters.yaml:309`); east is Street Front
(`student-house-topology.yaml:17`). It is **copied** into `skin-parameters.yaml`, not read:
nothing here imports anything from that repo, which was Duncan's condition.

The substrate agrees from the other direction, and this was not planned. `Cornice-Unit8-E` is
modelled 170 mm deep. The same file authors `cornice.projection.street-front: 0.020`. So
150 + 20 = 170: the cornice was drawn to oversail a 150 mm cladding face by exactly 20 mm, and the
built masonry face lands where the drawing already expected it. A test asserts the 20 mm against
the substrate's own bounds rather than against the parameter.

### Height, not width

Both discriminators Duncan offered work, and they are not close:

| | cornice top | host top | cornice run | host run |
|---|---|---|---|---|
| `Cornice-Unit8-E` | 13.0766 | **13.0766** | y 2.430…11.300 | **y 2.430…11.300** |
| `Cornice-Headhouse-E` | 14.495 | 14.718 | y 4.685…5.285 | y 2.850…7.120 |

Height is the test, because it carries the reason: a band flush with the wall's top makes the
whole face below one cladding zone, where one partway up the face is the scupper's outflow drip
and *interrupts* a zone rather than ending one. Width would work today and says nothing about why.

It is one bounds comparison inside `group_cornices`, which already knows the host: the cornice
gets `CORNICE` as before and the host now gets `TOP_CORNICE`.

### What it cost, and what it did not

`masonry_faces` is `exterior & tagged(TOP_CORNICE, True)`; `cladding_faces` subtracts the same
mask; `RULES` gains `{"keep": masonry_faces, "lap": None}`. No new mechanism — the stamp is
`group_caps`'s move and the predicate composes `wall_faces` like every other rule.

Three seams had to give, all of them found by running it rather than by reading:

- **`check_seeds` refused 0.15**, exactly 5x `Cladding.drop` at 0.030. The allowance is the
  authored number of the two, so the drop moved: **0.030 → 0.033**. 0.028 and 0.035 also clear;
  0.040 collides with `Membrane.distance`. The 3 mm is visible in two pinned figures — the live
  bake's cladding clearance 75.0194 → 74.8903 mm and the membrane/cladding separation
  0.0670180 → 0.0668889 — and in the scupper turn-down's band, which the test now derives from
  `spec["drop"]` instead of writing out, because a seed moves and a figure derived from one should
  move with it.
- **An empty skin is not a buildable skin.** The rig and `headhouse-walls-parapets-caps-...obj`
  carry no cornice at all, so the masonry selects nothing there and must still not break the
  build. Measured, on the rig: with `base` set, `_trim_below` raises first and blames the datum,
  which is fine; with `base: null` it builds a 0-face mesh and then `clean`, `clearance`,
  `buried`, `separation` and `write_obj` **all** raise on a shape of `(0,)`. So `build()` asks
  `covered(spec, faces)` first and prints what it skipped. Loud, and cheap — the `Faces` it needs
  is the one `check_facades` was already handed.
- **`check_facades` could not see this at all.** It asks the authored *tag*, and the masonry set
  is derived out of the tagged rainscreen set, so it passes whatever the carve-out does —
  including passing while a facade is skinned twice or not at all. `check_cladding` is the
  skin-level half: no facade in both, none in neither. Kept as a second function rather than
  folded in, because the two-facade fixture in the tests poses a facade tagged for a system **no
  skin builds** — legitimate at the tag, a failure at the skins — and that fixture is now what
  pins both readings.

The one exterior thing no cladding skin claims is a **cornice's own faces**, which is the
2026-08-19 decision rather than an omission. Measured across both bakes: exactly 8 such faces, both
cornices, and nothing else.

### The bake

```
Cladding   offset 85 mm  | lap 33/0 mm | residual 9.71e-16 | clearance  74.8903 mm | 56 border edges
Masonry    offset 150 mm | lap 0/0 mm  | residual 1.08e-15 | clearance 150.0002 mm |  4 border edges
           Membrane/Cladding separation  66.889 mm
           Membrane/Masonry  separation 194.031 mm
           Cladding/Masonry  separation 150.000 mm
```

No warnings on any of the three. The masonry is one n-gon / 2 triangles, area 5.935664 m2 against
5.935664 m2 covered, no overlap for `clean` to remove and no T-junctions. It stands at
`x = -0.150` and stops at `z = 12.8566` = 13.0066 − 0.150, tucked under the cornice's underside.

**E31 and E48 do drop straight down**, and they do it at `x = 0`. The old profile at each end of
the east run was (−0.255, 13.0766) → (0, 13.0766) → (−0.085, 12.9216) → (−0.085, 12.265), the
middle leg being the 45° step in under the cornice. It is now (−0.255, 13.0766) → (0, 13.0766) →
(0, 12.265) — the rainscreen carrying round onto the wall's end and dying on the wall's own face.
This paragraph read `x = 0.400` for one revision, which was the first cut giving the masonry the
wall's ends; see *"The corner, demonstrated rather than described"* below for what replaced it.

Worth being exact about *why* the old edge was angled, because it is not what it looks like. The
vertex at (0, y, 13.0766) is **interior** to the merged coplanar face in the `y` plane — both the
parapet's top and the cornice's top are buried under the cap plate, so the only plane incident
there is the `y` plane itself and the vertex moves in `y` alone. Its neighbour at the cornice's
underside arris (0, y, 13.0066) is a genuine three-plane corner and moves the full offset in `x`.
A vertical substrate edge therefore came out raked. What removed it is that the vertex is no
longer a corner of the rainscreen's outline: with the `x = 0` plane held at offset **zero**, both
it and the arris vertex below stay at `x = 0` and the edge between them is vertical. The masonry
has no returns to inherit it.

### What `/code-review high` caught, and all four were real

- **A skipped skin left last run's OBJ in `build/`.** The stale sweep globbed `Substrate_*.obj`
  only, which was right while every authored skin always built. `covered` makes absence routine,
  and `build/Masonry.obj` was found sitting there after a walls-and-caps build, holding 150 mm
  geometry offset from a different substrate. `display.reload()` reads the manifest and so was
  never fooled, but the OBJ is the artefact a person opens. The sweep now also covers `RULES`
  names — and only those, so nothing else in `build/` is touched.
- **`group_cornices` gated its stamps on the regrouping.** `if owner is None: continue` skipped
  `CORNICE` and `TOP_CORNICE` as well as the join, and `substrate.polyhedron` stamps no
  `"object"` at all — so on every transcribed substrate and every synthetic fixture a cornice was
  not stamped a cornice, and `cladding_faces` would have wrapped it instead of stopping below it.
  Inert on the three substrates today (the rig poses no cornice pair at all, checked), which is
  exactly why nothing noticed. The stamps now come first and unconditionally.
- **`masonry_faces` never reads `FACADE`**, so its own docstring's *"which masonry stays authored
  on the part"* named a join that did not exist. It cannot be made, and that is the honest
  answer rather than an oversight: every part of every substrate carries one system, so
  intersecting with the tag would **empty** this skin rather than select within it. What was
  wrong was leaving the hole unnamed. `check_cladding` now raises where the corniced walls of one
  substrate do not all carry the same system — the exact moment the cornice stops being enough,
  and the condition the student-house's two corniced walls will pose.
- **`separation_check` returned `inf`** where `separation(*built)` used to throw, so a caller
  asserting `gap > threshold` would pass vacuously on a substrate that built one skin or none. It
  raises now, naming the count.

Two things the review raised and did not count, both already named in the code: the turn gate at
`skinning/skin/offset.py:1400` is inert for a band measured from the skin's own edge, and `_gussets` would
raise `KeyError` rather than refuse by name on a self-intersecting border piece. No substrate
poses either. `audit.py` is untracked and outside `git diff` — its `live_skins()` does not apply
the `covered` gate, which is harmless only while its `BAKE` is hard-coded to the bake that has
cornices.

### The corner, demonstrated rather than described (2026-08-26)

The first cut gave the masonry the whole of `Parapet-Unit8-E`'s exterior set — its face **and**
the ends a corner grows in — and stopped the rainscreen at `x = 0.400`, the body join. Duncan:

> Almost there, but not quite. I have modified the -Y end of the masonry cladding to demonstrate
> the expected result. The part of the masonry cladding which turns the corner is deleted. E0 has
> been moved in the Y direction to align with the plane of the metal cladding. In the metal
> cladding, E90 is moved -x to align with the exterior plane of the wall.

Read off his edit, that is five coordinates, and **one rule reproduces all five**:

> A skin mitres onto a neighbouring **facade** at that facade's own cladding offset — unless the
> neighbour stands further out than this skin, where it stops at the substrate face instead.

| | planes at the vertex | lands at | Duncan |
|---|---|---|---|
| masonry end | `x=0 @ 0.150`, `y=2.43 @ 0.085` | (−0.150, 2.345) | v0, v1 |
| masonry top | + `z=13.0066 @ 0.150` | z 12.8566 | v0 |
| masonry foot | + `z=12.35 @ 0.150` | z 12.2000 | v1 |
| metal end | `y=2.43 @ 0.085`, `x=0 @ **0**` | (0, 2.345) | v26, v27 |
| metal foot | + `z=12.35 @ 0.085` | z 12.2650 | v27 |

The asymmetry is the whole content of it and it is physical: the brick is 65 mm proud of the
metal, so the brick runs through the corner and its end is exposed flush with the metal's face,
while the metal dies on the wall behind it — at `x = 0`, the back of the cavity. *"The outer
system owns the corner"*, in arithmetic. Duncan's own reason: *"Its thickness will need to be
drawn at some point… the ends of the bricks will be exposed on both ends and not covered by metal
cladding."*

`masonry_faces` is correspondingly narrowed to the face the cornice **overhangs** — `TOP_CORNICE`
now holds the direction the band stands proud in, and the test is the half-space `n · outward > 0`
so a wall at a plan angle still reads. The wall's ends go back to the rainscreen, which is what
carries it round the corner to the wall face.

### What that cost in `skinning/skin/offset.py`

`planar_offset` gains `offsets`, a per-face distance, `None` for every ordinary offset.
`_vertex_planes` is `_vertex_normals` with the plane's own move alongside its normal; the old name
is a one-line wrapper and every existing caller is untouched.

**This is not the per-face offset deleted on 2026-08-15.** That was per-face freedom *within* a
cladding mesh, and its reason — *"a different allowance is a different skin"* — is exactly what is
being honoured here: every face a skin **covers** still moves by one `distance`. What is new is
that a face it merely **mitres against** may move by someone else's, which is the existing
invariant *"vertices on the edge of a selection sit on the miter they would have had if the
neighbours were skinned too"* finally meeting a neighbour that really is skinned.

Two things the rule had to get right, both found by running it, not by reading:

- **A skin that clads no facade takes no facade miter.** The first version applied to the membrane
  too, and it raised at once: the `y = 2.43` plane wanted 0.008 and 0.0 at one vertex. Derived
  rather than listed — the test is whether the skin covers any of the exterior set at all, and the
  membrane covers none of it.
- **The decision is per plane, not per face.** At the corner the `y = 2.43` plane carries the
  parapet's end and the wall beside it (rainscreen) *and* `Cornice-Unit8-E`'s own end (clad by
  nobody). Per face, the cornice's end kept the masonry's 0.150 while the parapet's end took
  0.085 — one plane, two distances, one vertex, and `_vertex_planes` raised. It should raise:
  a plane is one surface and one system finishes it. So a plane any other cladding skin dresses
  moves at that skin's distance over the whole of it, and the raise stays for the case it is
  really about — two systems claiming one plane.

`_vertex_planes` also carries a new refusal of its own, which is that raise: *two offsets on one
plane at vertex N*. It is the loud form of the failure this whole mechanism could otherwise
produce silently.

### The corner as built

```
Masonry    offset 150 mm | residual 1.08e-15 | clearance 150.0002 mm | 4 border edges
           Cladding/Masonry separation 150.000 mm
```

One quad: `x = −0.150`, `y 2.345…11.385`, `z 12.200…12.8566` — Duncan's `-Y` edit exactly, and the
`+Y` end mirrored to it. The rainscreen's ends drop straight down at `x = 0` on both elevations.
The 150 mm between them is the brick and its cavity, left open.

Two small things, both measured and both left:

- The rainscreen keeps a redundant collinear vertex at `z = 12.9216` on each of those vertical
  ends — the cornice's underside arris. `clean`'s dissolve declines it because the three points
  are 1.5e-7 m off collinear, not the 1e-9 `STRAIGHT_TOL`. That is manifold3d's float32 in the
  union: **an offset of zero holds a vertex where the union put it**, so nothing re-projects it,
  and 1.9e-7 m is well inside the ~5e-7 m accuracy floor everything here already sits on. It
  leaves no T-junction and no area.
- `clearance` on the masonry reads 150.0002 mm, 0.2 µm over its own offset, for the same reason.

### The second review round, and one finding that was not a deferral

Five findings, all real; the first changed what gets built.

- **`masonry_faces` selected per body, and a corniced wall built in lifts hard-failed.** The
  cornice touches only the topmost lift, so the panel below it stayed rainscreen on the *same*
  facade plane — and that plane was then asked for 0.085 and 0.150 at one vertex.
  `_vertex_planes` refused, which is the right answer to the wrong input. I had recorded the
  stack as *deferred until an export poses it* on the strength of it merely under-claiming; it
  does not under-claim, it stops the build, and a synthetic panel + parapet + cornice poses it in
  fifteen lines. **So it is built**: the face the cornice overhangs is grown along the surface,
  contiguously, the same move `_opening` makes for a cheek. Inert on all three substrates — the
  live bake's wall is one lift and its cap plate is coplanar with the cornice rather than with the
  wall, which is why it escaped.
- **`_skin_from`'s `distance` override had gone half-dead.** With `offsets` on every spec,
  `planar_offset` reads that in preference for every plane row, so an override moved the laps and
  `metadata["offset_distance"]` while leaving the surface where the spec put it. No caller passed
  it — every what-if here is already `dict(spec, ...)` — so the parameter is gone rather than
  mended.
- **`facade_offsets`' docstring overclaimed.** It applies the neighbour's offset per plane
  *intersected with what this skin does not cover*, and a plane carrying both still splits and
  still raises. That is not papered over: a face a skin covers moves by that skin's distance by
  definition, so the readings are irreconcilable and two systems finishing one surface wants a
  decision. Said plainly now, with the growth above as the reason the case does not arise here.
- **`cladding_laps` said widening it was "the whole of the change". It is not, any more.**
  `_lap` reads a receiving face's offset plane as `plane + distance`, the skin's own scalar, which
  was true of every receiver until `facade_offsets` began moving a neighbour's facade by somebody
  else's allowance or by zero. Widen the predicate to every vertical face and the cladding may lap
  onto a facade the masonry dresses, where that assumption is 85 mm out — measured by doing it,
  `clearance` 74.89 → 8.62 mm. Unreachable today, because `interior` faces are never in the
  exterior set `facade_offsets` moves. Recorded at `cladding_laps`, where the conversation will
  start, rather than fixed on a substrate that cannot test it.
- **A wall corniced on both faces kept whichever cornice came last.** A plain assignment in a
  loop, silently leaving the other elevation rainscreen. It raises now: two masonry elevations on
  one wall is two skins, not one direction.

One thing the review did not catch and running it did: the new fixture helper was called `_lift`,
which `tests/test_offset.py` already uses for something else, and three unrelated tests went red.

### What is deliberately left

**The masonry stays a surface.** Duncan, 2026-08-26: *"Leave the masonry cladding as a surface for
now. We will discuss the best strategy to thicken it once we have the planar geometry correct."*
So the 150 mm at each corner is an open joint by design, not a defect to close, and the question
of how the brick is extruded back over its cavity is not answered here.

~~**The stack is untested.**~~ **Built 2026-08-26**, on review — see above. It was recorded here
as deferred on the reading that a host-part stamp merely under-clads a wall in lifts. It does not:
the panel below shares the parapet's facade plane, and one plane cannot take two offsets, so the
build stops. `_grow_coplanar` along the contiguous plane is what it always wanted, and the
synthetic fixture that poses it is fifteen lines. The bound left standing is contiguity itself:
two systems contiguous **and** coplanar would be over-claimed, and `check_cladding`'s
two-materials raise is what would catch it.

**The second masonry is not built.** The student-house has two corniced walls: the brick street
front at `0.150` and the mitoyen firewall at `0.140 + 0.020` cavity. Two allowances are two skins,
and which a wall takes is the `FACADE` material tag — the mechanism is already there and nothing
in the bake carries the second stamp. This narrows the old *"the brick skin is not built"* open
item rather than closing it: what is still missing is a substrate that poses **two** systems on
**two** corniced walls at once.

**The deck export has not been run.** Duncan, 2026-08-26: it should run on one. Nothing here
assumes it will — the deck-9 opening carries a **mouth** cornice (`cornice.projection.court-facing`),
which is the scupper kind and should be refused by the flushness test, but that is a prediction
until an export is read.

## A review round on the ledge branch: one fix, two divergences written down (2026-08-27)

`/code-review high` over the branch diff and the working tree. Three findings, all real as
statements about the code; one of them is a defect and is fixed, and the other two are places
where two readings of one sentence have drifted apart without any substrate here noticing. Both
are now stated where the code is, because the alternative is that they are rediscovered by a
review a third time.

### A face with no area was an unsatisfiable hard constraint

`_opposed` was hardened earlier on this branch to drop a zero-length normal — *"a face with no
area states no plane"* — but `_vertex_planes` still returned that `[0, 0, 0]` row, and
`planar_offset`'s constraint loop turned it into an equation: `abs(n_z) < tol` reads a zero normal
as **level**, so it went into `hard` with rhs `distance`. The row says `0 . t = distance`.

It does not move a vertex, and that is what makes it worth fixing rather than shrugging at. The
solve still places the surface correctly; what it destroys is the readout. `offset_residual` is
`max|H t - h|`, so it is pinned at `distance` and can never fall below it, and being a max it then
**masks** a genuine violation anywhere else in the body. The residual is the one number this build
asserts nothing about but everybody reads: above ~1e-9 means something broke.

Measured on a unit cube with one degenerate face appended:

| | `offset_residual` |
| --- | --- |
| clean | 2.26e-17 |
| one degenerate face | 0.01 — `distance`, exactly |

Dropped in `_vertex_planes` now, where `faces` and `normals` are still in step so `offsets` keeps
its per-face join. The live bake is unmoved to the digit: 145 -> 115 and 142 -> 86 triangles,
clearance 7.8808 and 74.8903 mm, the same four folds. No substrate here poses a degenerate face —
the two guards this branch already grew are the evidence that manifold3d's float32 hands them
over — so the property is pinned by a test on a cube rather than by a bake.

### The ledge test is wider in `_rules` than in `cladding_faces`, and stays wider

`cladding_faces` asks two things of a ledge: the roof runs into it, **and** the wall carries on
above it. `_rules` asks only the first. The second half is not decoration — a coping beside an
*ungrouped* cornice shares an edge with that cornice's top, and a lone cornice classifies `ROOF` —
so on the first half alone such a coping reads as a ledge, and in `_rules` that elects the whole
wall `climbed`. `membrane_faces` would then take its interior face, its tops and its cheeks off an
election no roof made.

Measured both ways on all five substrates: the elected element set is **identical** (rig 2, deck
bakes 8 and 4, headhouse 4, live bake 8), and the divergent face set `tops & ~under & meets` is
empty on every one of them — no wall top that a roof face touches is the top of its own element
anywhere here. So it is latent, and it is recorded at `_rules` with the condition that would make
it bite and the direction to fix it in: add `& under` there, and do **not** narrow
`cladding_faces` to match, where the second half is load-bearing today.

### The `< 3` fallback in `clean` restores the duplicates it just removed

The ring dedup added on this branch is right and fixes the 0.910 m² L-ring. Its fallback — fewer
than three distinct points, so put them all back — hands `_corners` the very pathology the dedup
removes: with `one[k - 1] == one[k]` the cross product is exactly zero and the ring registers no
corner at the point it doubles back from. Deduped, the same point comes back with `span == 0` and
**is** registered, which is the conservative answer. The cost of the permissive one is a
T-junction, which is what this pass exists not to make.

It fires. Once, on the live bake's membrane: an `[a, b, a]` spur between (8.072, 5.293, 14.619)
and (8.072, 5.177, 14.503). So the question is not hypothetical and was measured rather than
argued — run both ways, `clean(dissolve=True)` gives **identical** output on all three skins, 145
-> 113 triangles, 59 -> 35 border edges, 15 -> 0 T-junctions, the same area to 1e-6 mm², because `a`
takes its corner vote from another ring anyway. (`build.py` says 145 -> 115 for the same skin: it
also asks for `close`, and the tear takes two gussets.) Left as it is, with the finding written at
the branch. If a substrate ever poses a spur whose point has no other vote, **drop the ring** —
it encloses nothing, so dropping removes the false vote without deleting surface, where restoring
keeps a vertex that nothing corners at.

### One thing the review raised that is not a finding

`_lap` still reads a receiving face's offset plane as `planes[far, 3] + distance`, the skin's own
scalar, while `facade_offsets` now moves a plane by a **neighbour's** allowance or by zero. That
is the limit already recorded at `cladding_laps` on 2026-08-26, with the measurement that keeps it
unreachable (0 of 2, 0 of 12, 0 of 102, 0 of 138 receivers). Repeated here only because two
independent readers have now found it: it is the thing that breaks first if `cladding_laps` ever
widens past `interior`.

## The module split: rules, pipeline, rig (2026-08-28)

Opus 5 over in the student-house asked to leave this code here and import it, rather than copy it
across when the skinning modules are swapped. Nothing about `skinning/skin/` stood in the way — it imports
trimesh, numpy, manifold3d, shapely, yaml and jsonschema and nothing of ours, so it was already
portable. `build.py` was the whole of the problem: roughly 1700 of its 2055 lines were the rules
the student-house actually wants, and they sat in a repo-root script beside the transcribed
`PART_N` substrate, `BUILD_DIR`, the printed report and a `__main__`. There was no way to import
the derivations without importing the rig.

So the file is now three, drawn where the migration cuts:

- **`skinning/rules.py`** — the domain tags, every face rule, `RULES`, `classifier`, `skins`, the two
  `check_*` guards, and `TOL`. It is deliberately **not** under `skinning/skin/`: the invariant is that
  `skinning/skin/` never learns what a wall or a membrane is, and moving the rules in there to make them
  importable would have bought portability by spending the one boundary the module has.
- **`skinning/pipeline.py`** — `prepare`, `run`, `_skin_from`, `covered`. This is the seam. `run(parts,
  params)` takes plain data, reads no file, writes no file and prints nothing.
- **`build.py`** — the rig, and now only the rig: `PART_N`, `current_substrate`,
  `separation_check`, `build()` and `__main__`. 367 lines.

**`prepare` is the part that had already been written three times.** `build()`, `separation_check`
and `audit.live_skins` each carried their own copy of *group_cornices → group_caps → union →
Faces*, and `build()`'s copy had the two `check_*` calls the others lacked. That duplication is
what says the seam was in the right place before anyone drew it; all three now call `prepare`, and
`audit.py` picked up the `covered` guard it never had.

**`run` returns a result per *authored* skin, not per built one.** A skin whose rules select no
face of this substrate is a real condition — the masonry needs a wall a cornice finishes, and two
of the four substrates have none — and the caller has to be able to name it. So a skipped skin
comes back as `{"name", "spec", "raw": None, "mesh": None}` in parameter-file order, and `build()`
prints the line it always printed. Returning only the successes would have made the skip silent at
exactly the seam that exists to keep it loud.

Each result carries **both** meshes, `raw` and `mesh`. That is the measured-raw / written-clean
split from *"Cleaning a mesh"* moved out of `build()` intact rather than re-decided: a measurement
is a property of the offset, a verdict is a statement about what ships.

**`skins(params)` runs before `prepare`, deliberately.** The name join is where a parameter file
and `RULES` are checked against each other, and `prepare` re-stamps `metadata["object"]` on the
caller's parts. Failing the join first keeps a bad parameter file from mutating a substrate on its
way to raising — which is also the order `build()` had, and preserving it is what kept
`test_a_supplied_params_dict_is_validated_too` reading the error it was written for.

**The check that it moved nothing.** The printed report and every OBJ and manifest byte-identical
on all four substrates — rig, both deck bakes, headhouse, unit8 — plus the same 150 tests passing
as before. `md5sum` over `build/` before and after, five substrates each. That is the check to
repeat after touching any of the three modules, and it is cheap: five `python3 build.py` runs.

**`tests/test_seam.py` pins the direction of the dependency**, 150 → 154. `rules` and `pipeline`
may not import `build`, `skinning/skin/` may import none of the three, and `run` refuses anything that is
not a params dict. Read off the AST rather than by importing, because the import that would slip
through is a deferred one inside a function body: it never runs in the suite, never runs in the
build, and would still have to be unpicked on the far side of the migration. Nothing else in the
repo would notice — that is the point of writing it down as a test rather than as a paragraph.

### The review round on the split

`/code-review high`, six findings, five taken. It verified the central claim independently and
better than I had: an AST-level comparison of every top-level function and assignment between
`HEAD:build.py` and the three new modules, which came back identical except `build()`,
`separation_check()` and one docstring.

- **`prepare` had neither guard.** `run` refuses a non-dict and validates through `skins()`;
  `prepare` read `params["classify"]` and `params["fall"]` with no check at all, and it is an
  advertised entry point that `audit.py` already calls directly. So an unvalidated `topo["skin"]`
  with `fall: 1.4` would have gone straight through it — the 64.215 → 558.849 mm failure
  `parameters.resolve` exists to stop, re-opened at the new seam. Both entries now take
  `_params`, which validates a dict and refuses a path or a `None`. `parameters.validate` and not
  `resolve`, because `resolve(None)` reads the file.
- **`skinning/rules.py` claimed "nothing here reads a file".** `skins(params=None)` resolves against
  `skin-parameters.yaml`, which about fifteen tests rely on. The default is deliberate and
  documented at the function; the module docstring was the thing that was wrong, and it now says
  so and names the hazard — `rules.skins()` in a host repo returns *this* repo's numbers and
  raises nothing.
- **A raise used to lose every earlier skin's report.** Building the whole set up front meant that
  when the cladding hit `_reconcile` or the runaway guard, the membrane's residual, clearance and
  fold lines — already computed — never printed. On a rig whose loudest failures are exactly those
  raises, that is the diagnostic disappearing when it is wanted. `run` now returns `(faces,
  iterator)` and yields per skin, with the guard and the name join kept **eager** in `run` itself
  and the loop in `_each`: a generator function runs no line of its body until it is iterated, so
  inlining it would have moved a bad-parameter error away from the call. Checked by stubbing a
  raise into the cladding — the membrane's three lines print, then the raise.
- **`audit.live_skins` called `prepare` before `skins`**, reversing the order this same change
  documents as deliberate two files away. Fixed; it costs nothing and it is the ordering that
  keeps a bad parameter file from mutating the parts on its way to raising.
- **NOTES' own `## Layout` table was the wrong map** — it still sent readers to `build.py` for the
  rules, and listed neither new module nor three of the test files. CLAUDE.md tells every reader
  to open this file first, so that table is load-bearing. Rewritten.

**Not taken: `separation_check` cleans every skin and uses only `raw`.** True, and measured at
67 ms on the rig, where it is called by one test. The suggested fix is to bypass `run` for
`prepare` + `_skin_from` the way `audit.py` does — but picking `raw` out of a result is the seam
being *used correctly*, not misused, and a second path would need its own copy of the ordering
discipline that the finding above just caught `audit.py` getting wrong. One path through the seam
is worth 67 ms. Revisit if `separation_check` is ever pointed at a live bake.

What this did **not** do was make any of it installable: no `pyproject.toml`, three generic
top-level names that would collide in a host repo, and five undeclared dependencies. That was left
deliberately separate, the import mechanism being Duncan's call. He took it the same day — see
*"Packaging it"* below.

## Packaging it (2026-08-28)

Duncan chose to nest: one package, with the rig left outside it, and `skinning` as the name.

```
skinning/            skin/ (geometry) + rules.py + pipeline.py
build.py audit.py    the rig and the scratch script, at the root, not in the package
skin-parameters.yaml this rig's numbers, at the root
```

Intra-package imports are **relative** (`from .skin import parameters`), so the package can be
renamed or vendored without touching a line inside it; everything outside imports through
`skinning.`. `pip install -e .` and the wheel both work, and the wheel carries exactly the ten
package files and nothing else — no tests, no `build.py`, no bakes.

**The install found a real defect that nothing here could have.** `skinning/skin/parameters.py`
resolved both its paths from the repo root, so an installed copy raised `FileNotFoundError` on its
*first call*: `rules.skins()` -> `resolve` -> `validate` -> `_schema()` reads the JSON Schema, and
the schema had never been shipped. The suite could not see it — the suite runs in the repo, where
the root is right there — and neither could the build. It took building the wheel, installing it
into a clean venv and skinning a bake from a neutral directory.

The fix draws a line the two files had blurred by both sitting at the root. **The schema is code
and ships inside the package**; it is the shape `rules.py` consumes, exactly as the `RULES` table
is, and every validation path reads it. **The parameter file is data and stays at the root**; it is
this rig's authored numbers, it migrates into the host's own file, and an installed copy has no
business defaulting to skin-test's numbers. So `SCHEMA_PATH` is now `Path(__file__).parent / ...`
with no reach outside the package at all, `DEFAULT_PATH` keeps the one repo-root escape there is,
and `load` raises a `ParameterError` naming the situation rather than letting a `FileNotFoundError`
out with a path inside site-packages. `tests/test_seam.py` asserts that escape is the *only* one.

Verified by doing it: the wheel installed into a venv, imported from `/tmp`, and run over the unit8
bake gives 115 / 84 / 2 triangles and residuals 8.67e-17 / 9.71e-16 / 1.08e-15 — the same figures
the in-repo build prints for that substrate.

All six dependencies are declared and required. The containment is real —
`skinning/skin/clean.py` is the only importer of shapely, `skinning/skin/parameters.py` the only
importer of yaml and jsonschema, so `skinning.skin` alone would run on trimesh, numpy and
manifold3d — but `skinning.pipeline` reaches both, and an extra that the package's own entry point
needs is not an extra. `bpy` is nobody's dependency and `blender/display.py` is not in the package.

One incidental fix: `pythonpath = ["."]` in `[tool.pytest.ini_options]`, so a bare `pytest` works.
It never did — only `python3 -m pytest`, whose `-m` inserts the working directory — and that is why
"run pytest from the repo root" had been documented rather than fixed.

**The toolchain on this machine cannot install it, and that took a review round to establish.**
`[build-system] requires = ["setuptools>=61"]` does get a modern setuptools into pip's isolated
build environment — but the *pip* doing the installing has to be modern too, and this machine's is
22.0.2. Measured: `python3 -m pip install --target … .` takes the legacy `setup.py install` path
anyway and writes an `UNKNOWN-0.0.0` dist-info **containing no package at all**, exit code 0, no
error; `pip install -e .` fails outright, setuptools 59 having no PEP 660 `build_editable` hook.
Under pip 26 in a venv both work and the wheel is correct. The silent one is the dangerous one, and
the first draft of the `pyproject.toml` comment asserted the opposite in as many words. Install into
a venv, or `pip install -U pip` first. A wheel build also drops `skinning.egg-info/` at the root and
a `bdist.*` inside `build/`, next to the OBJs; both are gitignored now.

**`manifold3d>=2` was two minor versions too low.** `offset._tiling` and `clean` both call
`triangulate(..., allow_convex=False)`, deliberately, and that keyword does not exist before 3.1.
Verified against real wheels rather than changelogs: 2.5.1 is `(polygons, precision=-1)`, 3.0.0 is
`(polygons, epsilon=-1)`, and both raise `TypeError` on the keyword; 3.1.0 is the first with
`allow_convex`. A host resolving 2.x or 3.0 — an existing pin, an older interpreter with no new
wheels — would have installed cleanly and failed on the first cleaned skin. Floor is `>=3.1` now.

**`tests/test_seam.py` had two holes of its own, both in the direction of passing.** `_imports`
skipped every relative import, which was right for the rig test and wrong for the geometry one: in
the flat layout the violation it exists to catch was `from rules import ...`, level 0, and was
caught; inside the package it is `from ..rules import ...`, level 2, and went straight through. And
the "one escape" test scanned the *text* for `parents[` and `parent.parent`, which in files this
prose-heavy false-positives on a docstring and misses a real escape spelled
`os.path.dirname(os.path.dirname(...))` or a `sys.path` insert. Both read off the AST now, and both
were checked by posing the violation: a `from ..rules import CORNICE` in `offset.py` and a nested
`dirname` in `measure.py` each fail the suite where they did not before.

## Six skins: a membrane per roof, and the masonry in two (2026-08-28)

Duncan: *"separating the membrane into three, one for each roof, and the masonry facades
separated in two, one for the brick facade, and another for the firewall."*

    Membrane-Deck9      offset   8 mm | residual 1.02e-16 | clearance  7.3148 mm | 111.4072 m2
    Membrane-Headhouse  offset   8 mm | residual 1.70e-16 | clearance  7.8811 mm |  32.6849 m2
    Membrane-Unit8      offset   8 mm | residual 1.02e-16 | clearance  7.9199 mm |  93.2893 m2
    Cladding            offset  85 mm | residual 1.80e-15 | clearance 17.9998 mm | 591.5588 m2
    Masonry-Brick       offset 150 mm | residual 1.94e-15 | clearance 86.8850 mm | 111.2459 m2
    Masonry-Firewall    offset 161 mm | residual 1.89e-15 | clearance 18.0278 mm | 159.8653 m2

The scupper's gusset — 2 tears, 3459.1 mm2 — is now the **headhouse** zone's, which is where the
scupper is, and the folds each skin reports are the same four union vertices they always were.

**Nothing moved.** The three membranes sum to 237.3814 m2 and the two masonries to 271.1112 —
the two figures the single skins printed, to the last decimal. Face for face, the emitted
polygons are **identical on four of the five substrates**; on the floors bake one vertex differs
in its eighth decimal (`y = 2.84984703` against `2.84984707`, 40 nm — float noise in a
least-squares system solved over a smaller soft set), and the firewall's panel stands 11 mm
further out because its allowance is a different number. That is the whole of the geometric
difference.

One number does move and it is worth understanding: the coplanar overlap `clean` dissolves falls
from 344 797 mm2 on the one membrane to 260 748 across the three. That is not surface — it is
**redundant cover**, a plane the lap rule reached twice from two sides of what is now a zone
boundary and reaches once from within a zone. The written meshes are identical either way, which
is what says it was redundant.

### How it is authored, and why the two splits are not the same shape

A rule set stopped being one skin. `RULES` entries now declare a **`select`** — the metadata key
they are instantiated on — and a parameter entry says which instance it is: a value binds one,
`'*'` fans the rule set out over the substrate.

    - name: Membrane        rules: Membrane   select: '*'      # one per roof_zone
    - name: Cladding        rules: Cladding   select: null
    - name: Masonry-Brick   rules: Masonry    select: brick    distance: 0.150
    - name: Masonry-Firewall rules: Masonry   select: block    distance: 0.161

The asymmetry is the point and it is `check_seeds`. Three membranes are **one allowance on three
roofs**: authored as three entries they would repeat 0.008 / 0.062 / 0.205 and collide as equal
seeds, and the seed rule is right — nothing distinguishes them but where they are. So the numbers
are authored once and the *substrate* says how many skins that is. The two masonries are two
allowances, so they are two entries with two sets of numbers, and no rule has to be bent.

The cost is that the number of skins is a property of the substrate: `skins()` takes the `Faces`
view as well as the numbers, and `pipeline.run` calls it after `prepare`. Everything the file
can be wrong about is still checked before any geometry runs — that is `check_skins`, which `run`
calls first, for the same reason the join always came first: `prepare` re-stamps
`metadata["object"]` on the caller's parts, and a bad file should not have mutated a substrate on
its way to raising.

Names come from the tag: `Membrane-Deck9`, `-Unit8`, `-Headhouse` on the whole building,
`Membrane-Rig` on the rig, `Membrane-Headhouse` alone on the headhouse bake. The stale-file sweep
in `build()` had to widen to match — `Membrane-Deck9.obj` is a name neither `RULES` nor the
parameter file spells, and a bake of another substrate leaves one behind.

### The membrane: one authored stamp, everything else derived

`ROOF_ZONE` is stamped on the **roof parts only** — `build.stamped` reads it off `Roof_<zone>_<layer>`
with a regex, so a new roof needs no table edit — and the walls follow from the geometry that was
already there: `_climbed` is `_rules`' own election, asked of one zone's roof faces instead of all
of them. Measured on the whole building: three zones, four parapets each, **no element elected
twice**, and the three keep sets are exactly the 156 faces the one skin selected.

The derivation was tried first and it works: the roof face set has exactly three connected
components here (7, 7 and 5 faces), one per roof. It is not what shipped, for two reasons — a
component has no name to author a skin against, and a roof that arrived in two pieces would
silently become two zones. `check_roofs` is the other half of that: a roof face whose part carries
no zone raises, because the fan-out enumerates the zones it *finds* and a missing stamp would
subtract a membrane from the build without a word.

One thing did change and it is worth writing down. The **raw** emission per zone is not the joint
skin's raw emission cut up: on the unit8 bake the headhouse zone comes out two vertices short of
symmetric at the scupper, where the joint skin was symmetric. It is redundant cover, not surface —
`_lap` legitimately covers part of a plane twice, and which of two overlapping quads lands where
is not mirrored — and `clean` dissolves it either way, which is why the *written* meshes are
identical face for face. `test_the_scupper_comes_out_symmetrical_on_the_live_bake` now asks the
written mesh, which is the surface Duncan's *"the scupper is symmetrical"* is about.

### The masonry: the guard became the selector

`check_cladding` has raised since 2026-08-26 if the corniced walls of one substrate carried more
than one `FACADE` value — *"one masonry skin is one allowance, so a substrate posing two needs a
skin each, selected on the tag as well as on the cornice"*. That is exactly what was built:
`masonry_faces(faces, fall, system)` takes the material off the **corniced host**, and the two
grown sets are 13 and 33 of the 46 faces the unfiltered rule claims, disjoint.

It is the *host's* material that selects, not each face's, and that is the growth's own argument
read again. 20 of the firewall's 33 faces are ends of `L*-alleyback-W`, `L*-courtfacing-E` and
`Lobby-*` — every one of them stamped `rainscreen`, because a return at a corner is a face on the
elevation it lands in. Filtering per face would have dropped precisely those.

### What the split forced: the rainscreen is the residue

This is the one real change of rule, and it was not optional. `cladding_faces` read
`facades_of(faces, RAINSCREEN, fall)`, which was identical to "every exterior facade the masonry
does not claim" for as long as every part carried one tag. Stamp the street front `brick` and the
two part company **at the corners**: that wall's 20 return-ends leave the rainscreen set with it,
7.795 m2 of facade claimed by nobody, and `check_cladding` refuses the substrate as *"claimed by
neither"*. A per-part tag cannot say that a wall's end is clad in whatever clads the elevation it
lands in.

So the rainscreen claims the residue. Measured both ways on the whole-building bake: with it, the
cladding is 591.5588 m2 / 138 triangles / one fold — exactly what it was; without it, 583.7635 and
149. On every substrate where all parts are rainscreen the two readings are the same, which is why
the other four bakes are unaffected.

What the residue then cannot notice is a wall stamped `brick` that no cornice reaches: the cladding
takes it and says nothing, where before it was claimed by neither skin and refused. So the tag is
read back against the skins — `check_cladding` raises on a wall carrying a masonry material with no
face in that masonry's skin. The claim the old check made is unchanged; only the sentence that
catches it moved.

### The firewall's 161 mm

The block is drawn 0.140 with a 20 mm cavity, which makes 0.160 — and 0.160 is exactly
**20x `Membrane.distance`**, which `check_seeds` refuses. Duncan chose to move the new number
rather than the membrane, the way `reveal` went 0.016 -> 0.018 on 2026-08-27 for the same reason:
the millimetre lives in the cavity, which is a site dimension. `Masonry-Firewall.distance` is
0.161, and the deck bakes' masonry panel therefore stands 11 mm further out than it did — the one
intended geometric difference in this whole change.

### What the review caught (2026-08-28)

`/code-review high` over the branch and the working tree, five findings, four acted on and one
rejected with a reason. Worth recording because two of them are about the *shape* of the change
rather than about a line.

**The build got 3.3x slower, and that was structural.** 2m14s on the whole-building bake against
41s for the three-skin build it replaced. Not the skins — the **derivations**: every skin's
`facade_offsets` evaluates every *other* skin's `keep`, so six skins ask for `wall_faces`,
`_rules` and `_opening` about thirty times each, and `rise` walks every element's stack while
`_under_cover` casts a ray off every roof face. Instrumented on the deck bake: 45 `wall_faces`,
540 `rise`, 14 `_under_cover` in one build. Fixed by memoising the three on the `Faces` they were
read from — `_derived`, which hands the value back as a **copy** so a caller writing into a mask
cannot corrupt what the next one reads. `Faces` already caches `roles` and `elements` on the same
footing, and the scope is the same: re-stamp metadata and you need a new `Faces`. Now **55.8s**,
the remainder being six skins to solve and clean where there were three. The printed report and
every OBJ are identical with it and without it on all five substrates.

**A check that could not fail.** `check_cladding` asserted that the per-system masonry sets add up
to the unfiltered one. They cannot fail to: `_grow_coplanar` is a reachability closure over a
fixed adjacency, so growing the union of the seeds *is* the union of the growths, and the loop
above it has already refused any host whose material is not a masonry. Deleted, and the sentence
saying why is what stands there now — a check that looks maintained and cannot fire is worse than
none. The **disjointness** check beside it is real and stays: two elevations growing into one
another along a shared plane is a substrate condition, not an arithmetic identity.

**`facade_offsets` was last-writer-wins across `others`.** It assigned per sibling skin with no
conflict test, so a plane carrying the facades of two *different* neighbouring systems took
whichever came last in the list. Latent while there were two siblings and one of them clad no
facade; not latent with five, two of them masonries at 0.150 and 0.161. Now collected per plane
before anything is written and raised on disagreement, the same shape `skin_offsets` already had
for the reveal and the flush stop. **No substrate here poses it** — every OBJ is unchanged — so
the guard is structural rather than measured, which is the same footing as its neighbour.

**One finding rejected.** The review proposed tightening the "a masonry-stamped wall is reached by
its masonry" check from *"some face of this wall"* to *"every exterior face of this wall"*, to
catch a wall whose facade is reached only in part. The strict form is wrong here and would refuse
every corniced wall on the live bake: a wall's **ends** are exterior and are not in its masonry —
they are faces on the neighbouring elevation, clad by whoever clads that elevation, which is the
whole of the residue argument (`Parapet-Unit8-E` has 20 such). The gap it names is real but is a
per-plane question, and the answer to it already exists downstream: a plane carrying two
allowances raises in `skin_offsets`. Left as it is, deliberately.

**And a dead binding.** `for (a, b), rs in zip(edges, sheet)` in the torn-edge loop never read
`rs` — the test is on the ends' rises, which is the whole of the rule. Dropped, with a line saying
which test is live, because the surrounding comment reads as though the per-edge sheet were part
of it.

## Open items

- ~~**The scupper mouth and the cornice ends are bare.**~~ Closed 2026-08-21 by the extended
  cornice, which removed the knife rather than weakening `_reconcile` — see that section. The
  `_reconcile` narrowing described here is **unnecessary rather than untaken** and should stay
  untaken.
- ~~**A fourth bake is in the tree, superseded, uncovered, and it warns.**~~ **Deleted
  2026-08-25 on Duncan's instruction.** `unit8-parapets-caps-clt-insulation-headhouse-cornices.obj`
  was the export he replaced on 2026-08-21 with the *extended* cornice — see *"The extended
  cornice, and the scupper finished"* — so it still carried the knife at the scupper mouth that
  the extension removed. Nothing read it: no test named it and it appeared in no table here. The
  new verdict found it was the only substrate crossing the substrate — membrane **8**, cladding
  **5**, plus 4 skin-to-skin pairs — and a spot check confirmed those were **geometrically real**,
  not false positives: a membrane triangle on `x = 8.072` passing through the scupper drip solid
  spanning `x 7.98…8.08, y 4.785…5.185, z 14.425…14.495`. The old defect preserved in the old
  substrate. It is in git history if it is ever wanted. Found by `/code-review high skinning/skin/`.
  **"all three substrates" throughout this file means rig, walls-and-caps and extended-cornices**,
  and now there are only three.
- **The south-junction sliver**, 205 x 7.3 mm, left by the continuation. See above; it needs the
  lap to clip against its neighbour rather than emit whole quads.
- ~~**Coplanar laps overlap, and it skews the area**~~ — membrane 0.180%, cladding 0.311%, plus
  six bowtie quads. **Decided 2026-08-21: emit then clean.** `skinning/skin/clean.py` is specified at the
  top of this file. **Built 2026-08-21** — see *"The pass as built"*: area is now exactly the
  area covered, on both skins. The two source-level alternatives are measured and ruled out; the
  *cause* — the lap emitting whole quads that overlap — stays open above.
- ~~**The membrane has one hole: the scupper outlet**~~ — **closed 2026-08-22** by
  `clean(mesh, close=m)`, on Duncan's decision. See *"The gusset as built"*. Every other border
  component in either skin is a legitimate free edge — the skin's own perimeter — and three
  conditions keep them that way.
- ~~**`clearance` cannot tell "stops short of a feature" from "folds through itself".**~~
  **Closed 2026-08-25 — Duncan took option D:** demote `clearance` to a printed number, and make
  the verdict `measure.intersects` plus `measure.buried`. See *"The clearance verdict"* for what
  was weighed and what the new checks measured. The reasoning that stood here for weeks is
  unchanged and was never the blocker; what forced the decision was that the warning would fire
  **forever**, because the cheek lining Duncan asked for reads 79.97 mm against an 85 mm offset
  inherently. `clearance` is still printed, and a low reading is still worth looking at.
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
- ~~**The brick skin is not built.**~~ **Narrowed 2026-08-26** by the masonry skin — see that
  section. A separate cladding skin at its own allowance now builds on the live bake, keyed on a
  cornice that finishes its wall rather than on the `BRICK` tag. What is left of the item is the
  **second** system: the student-house has two corniced walls, brick at 0.150 and the mitoyen
  firewall at 0.140 + 0.020 cavity, and two allowances are two skins. The mechanism for choosing
  between them is the `FACADE` material tag, which already exists and which nothing in any bake
  stamps. It still needs a substrate that poses two systems on two corniced walls at once; the
  two-facade fixture in `tests/test_offset.py` is half of that condition in miniature, and is now
  also what pins `check_cladding`'s "claimed by neither" reading.
- **Which skin caps a masonry wall?** `cladding_faces` takes *every* wall top regardless of
  facade system, so a masonry wall gets a rainscreen coping. Plausible — brick with a metal cap
  is normal, and the live bake now builds exactly that over `Parapet-Unit8-E` — but it is an
  assumption, not a rule Duncan gave. The 2026-08-16 "both cap it" decision settles who caps a
  wall and not which *system* does, so this survives it unchanged. It became **visible** on
  2026-08-26 where it was previously hypothetical: the coping over the masonry facade is
  rainscreen, at 85 mm, over a facade at 150 mm.
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
  check from the scratch script into `skinning/skin/measure.py` as `intersects(a, b)` and asserting
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
