"""OBJ export that writes planar faces as n-gons rather than triangles.

trimesh is triangles-only, so a box lives in memory as 12 triangles and exports
as 12 triangles — which is what Blender then shows in edit mode. Here each
facet (a group of coplanar, connected triangles) is written as a single face
built from its boundary loop, so a box round-trips as 6 quads.

Collinear vertices on a loop are kept: dropping one that a neighbouring facet
still corners on would leave a T-junction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


def _loop(edges: np.ndarray) -> list[int] | None:
    """Order boundary edges into one closed vertex loop, or None if not one."""
    adjacent: dict[int, list[int]] = {}
    for a, b in edges:
        adjacent.setdefault(int(a), []).append(int(b))
        adjacent.setdefault(int(b), []).append(int(a))
    if any(len(v) != 2 for v in adjacent.values()):
        return None  # holed facet, or edges meeting three ways

    start = int(edges[0][0])
    loop, previous, current = [start], start, adjacent[start][0]
    while current != start:
        loop.append(current)
        a, b = adjacent[current]
        previous, current = current, b if a == previous else a
    return loop if len(loop) == len(adjacent) else None


def _newell(points: np.ndarray) -> np.ndarray:
    return np.cross(points, np.roll(points, -1, axis=0)).sum(axis=0)


def faces_as_ngons(mesh: trimesh.Trimesh) -> list[list[int]]:
    """Facet boundary loops, plus any triangle that belongs to no facet."""
    ngons, merged = [], set()
    for facet, edges in zip(mesh.facets, mesh.facets_boundary):
        loop = _loop(edges)
        if loop is None:
            continue  # leave this facet's triangles as they are
        if _newell(mesh.vertices[loop]) @ mesh.face_normals[facet[0]] < 0:
            loop.reverse()  # wind counter-clockwise about the outward normal
        ngons.append(loop)
        merged.update(int(f) for f in facet)
    ngons += [f.tolist() for i, f in enumerate(mesh.faces) if i not in merged]
    return ngons


def write_obj(mesh: trimesh.Trimesh, path: str | Path, name: str = "mesh") -> Path:
    path = Path(path)
    lines = [f"o {name}"]
    lines += [f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in mesh.vertices]
    lines += ["f " + " ".join(str(i + 1) for i in face) for face in faces_as_ngons(mesh)]
    path.write_text("\n".join(lines) + "\n")
    return path
