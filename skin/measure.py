"""Distance queries between the skin and its substrate."""

from __future__ import annotations

import numpy as np
import trimesh


def clearance(parts, skin: trimesh.Trimesh) -> float:
    """Smallest gap between the skin surface and the substrate surface.

    Sampled at the skin's vertices and face centroids, against every part. For a
    sound planar offset this equals the offset distance (touched at face
    centres, exceeded at corners); a smaller value means the skin has folded
    through itself where the offset outran the substrate's local feature size.

    Parts are concatenated rather than unioned: the skin lies outside the solid,
    so its distance to any interior face is never less than its distance to the
    outer surface, and the shared faces cannot produce a false alarm.
    """
    if isinstance(parts, trimesh.Trimesh):
        parts = [parts]
    samples = np.vstack([skin.vertices, skin.triangles.mean(axis=1)])
    # queried per part: concatenating leaves coincident duplicate triangles on
    # every shared face, and closest_point trips over the ties they produce
    return min(float(trimesh.proximity.closest_point(p, samples)[1].min()) for p in parts)


def separation(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    """Smallest distance between two skins, sampled both ways.

    Sampled at vertices and face centroids, so it is a close upper bound rather
    than an exact minimum — an edge crossing between samples would read high.
    Good enough to confirm two skins are nowhere near colliding.
    """
    def one_way(p, q):
        samples = np.vstack([p.vertices, p.triangles.mean(axis=1)])
        return float(trimesh.proximity.closest_point(q, samples)[1].min())

    return min(one_way(a, b), one_way(b, a))
