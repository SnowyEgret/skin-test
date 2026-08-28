"""Every number in NOTES.md's mesh tables, measured: triangles, summed area against
the area actually covered, border edges, T-junctions, non-manifold edges, and
self-crossing n-gons, before and after `clean`.

Scratch, not part of the build — added at the end of 2026-08-21 and committed on
2026-08-26. It reads `rules` and `pipeline`, so it will bit-rot the moment those
move. (It read `build`'s internals until 2026-08-28, when the rules and the
pipeline seam came out of it into their own modules; `live_skins` had grown its
own copy of the prologue and now calls `pipeline.prepare` for it.) (This said "**Untracked on purpose** … for Duncan to `git add` or delete"
until 2026-08-27, by which time it had been added and the sentence described a
file that no longer existed. Found on review.)

    python3 audit.py        # from the repo root

Measure on the in-memory skin, never on a reloaded OBJ: the n-gon writer emits
self-crossing loops for a raw skin and they re-triangulate differently on the way
back in, which reads as 132.9 m2 against the true 126.2.
"""
import sys
from pathlib import Path

import numpy as np
import trimesh

# this script's **own** directory, not a hard-coded checkout. An absolute path
# here shadows the copy it is run from, so `python3 audit.py` in a worktree, a
# scratch copy or a bisect checkout silently measured `/home/duncan/skin-test`
# and reported numbers for code that was not under test. Found on review,
# 2026-08-27, by a reader who hit exactly that
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline
import rules
from skin import substrate, parameters
from skin.export import faces_as_ngons

BAKE = "unit8-parapets-caps-clt-insulation-headhouse-extended-cornices.obj"

def live_skins():
    parts = substrate.from_obj(BAKE, metadata={rules.FACADE: rules.RAINSCREEN})
    params = parameters.resolve(None)
    # the name join first, for the reason `pipeline.run` does it in this order:
    # `prepare` re-stamps `metadata["object"]` on the parts, and a parameter file
    # that fails the join should not have mutated a substrate on its way to raising
    specs = rules.skins(params)
    faces = pipeline.prepare(parts, params)
    # raw, deliberately: this script measures before and after `clean` itself,
    # so it wants what `skin_over` emitted rather than what `pipeline.run` ships
    return {
        spec["name"]: pipeline._skin_from(spec, parts)
        for spec in specs
        if pipeline.covered(spec, faces)
    }

def borders(m):
    return len(trimesh.grouping.group_rows(m.edges_sorted, require_count=1))

def nonmanifold(m):
    groups = trimesh.grouping.group_rows(m.edges_sorted, require_count=None)
    return [g for g in groups if len(g) > 2]

def tjunctions(m):
    """Vertices sitting on the interior of a border edge they are not part of."""
    edges = m.edges_sorted[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)]
    V = m.vertices
    n = 0
    for a, b in edges:
        p, q = V[a], V[b]
        d = q - p
        L = np.linalg.norm(d)
        if L == 0:
            continue
        t = (V - p) @ d / (L * L)
        on = np.linalg.norm(V - (p + np.outer(t, d)), axis=1)
        inside = (t > 1e-9) & (t < 1 - 1e-9) & (on < 1e-6)
        n += int(inside.sum())
    return n

def selfcrossing_ngons(m):
    """n-gons whose boundary loop crosses itself, and the count of n-gons."""
    bad = 0
    ngons = faces_as_ngons(m)
    for loop in ngons:
        if len(loop) < 4:
            continue
        pts = m.vertices[loop]
        nrm = np.cross(pts, np.roll(pts, -1, axis=0)).sum(axis=0)  # Newell
        if np.linalg.norm(nrm) == 0:
            continue
        nrm = nrm / np.linalg.norm(nrm)
        u = np.cross(np.eye(3)[np.argmin(np.abs(nrm))], nrm)
        u = u / np.linalg.norm(u)
        v = np.cross(nrm, u)
        flat = np.column_stack([(pts - pts[0]) @ u, (pts - pts[0]) @ v])
        from shapely.geometry import LinearRing
        try:
            if not LinearRing(flat).is_simple:
                bad += 1
        except Exception:
            bad += 1
    return len(ngons), bad

def true_area(m):
    """Area actually covered: union each plane in 2D, either way up."""
    from skin.clean import _groups, _basis
    from shapely.ops import unary_union
    from shapely.geometry import Polygon
    total = 0.0
    for rep, group in _groups(m):
        u, v = _basis(rep[:3])
        origin = rep[:3] * rep[3]
        polys = []
        for tri in m.faces[group]:
            p = m.vertices[tri]
            polys.append(Polygon(np.column_stack([(p - origin) @ u, (p - origin) @ v])))
        total += unary_union(polys).area
    return total

def report(name, m):
    ng, bad = selfcrossing_ngons(m)
    print(f"  {name:<10} tris {len(m.faces):>4} | area {m.area:.6f} | true {true_area(m):.6f}"
          f" | border {borders(m):>3} | T-junc {tjunctions(m):>3}"
          f" | non-manifold {len(nonmanifold(m)):>2} | n-gons {ng:>3} ({bad} self-crossing)")

if __name__ == "__main__":
    from skin.clean import clean
    skins = live_skins()
    for name, m in skins.items():
        print(name)
        report("before", m)
        c = clean(m)
        report("after", c)
        print(f"             overlap removed {c.metadata['overlap_removed'] * 1e6:.0f} mm2")
