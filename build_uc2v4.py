"""Build the parametric uc2v4 inserts and verify them against the Inventor
ground truth STEP exports in ./extracted/.

Usage:
    uv run --with cadquery --with trimesh --with rtree --with scipy \
        python build_uc2v4.py [--no-verify]

The Inventor-written STEP files silently break OCC booleans (tolerance
abuse), so verification happens in the mesh domain: both b-reps are
tessellated and compared by surface-deviation sampling in both directions.
Known, intentional model omissions (engraved label text, notch rim fillets)
show up as attributable deviation clusters and are listed per part.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cadquery as cq

try:
    import numpy as np
    import trimesh
except ImportError:  # pip install '.[verify]'; --no-verify builds without them
    np = trimesh = None

from uc2v4 import build_lens_insert, build_master_insert

HERE = Path(__file__).parent
OUT = HERE / "generated"
GT = {
    "uc2v4_master_insert": HERE / "extracted" / "PRT_-_2123_-_MASLCK_-_V04_-_B.step",
    "uc2v4_lens_insert": HERE / "extracted" / "PRT_-_2027_-_INSLEND43F-50_-_V04.step",
}

SAMPLES = 60000
TESS_TOL = 0.01


def fused_solid(wp: cq.Workplane) -> cq.Solid:
    solids = wp.solids().vals()
    s = solids[0]
    for extra in solids[1:]:
        s = s.fuse(extra)
    return s


def to_mesh(shape: cq.Shape) -> trimesh.Trimesh:
    verts, tris = shape.tessellate(TESS_TOL)
    m = trimesh.Trimesh(vertices=[v.toTuple() for v in verts], faces=tris)
    m.merge_vertices()
    return m


def deviation(src: trimesh.Trimesh, dst: trimesh.Trimesh, n: int):
    pts, _ = trimesh.sample.sample_surface(src, n)
    _, dist, _ = trimesh.proximity.closest_point(dst, pts)
    return pts, dist


def cluster_report(pts, dist, threshold: float, label: str):
    """Group offending samples into coarse spatial clusters and print them."""
    bad = dist > threshold
    if not bad.any():
        print(f"    {label}: no deviations > {threshold} mm")
        return
    p, d = pts[bad], dist[bad]
    cells = np.round(p / 4.0).astype(int)  # 4 mm grid
    seen = {}
    for c, (pt, dv) in zip(map(tuple, cells), zip(p, d)):
        best = seen.get(c)
        if best is None or dv > best[1]:
            seen[c] = (pt, dv)
    # merge to the N worst distinct cells
    worst = sorted(seen.values(), key=lambda t: -t[1])[:6]
    print(f"    {label}: {bad.sum()}/{len(dist)} samples > {threshold} mm, "
          f"max {d.max():.3f} mm; worst spots:")
    for pt, dv in worst:
        print(f"      {dv:6.3f} mm at ({pt[0]:7.2f}, {pt[1]:7.2f}, {pt[2]:7.2f})")


def report(name: str, mine: cq.Workplane, gt_path: Path) -> None:
    a = fused_solid(mine)
    b = fused_solid(cq.importers.importStep(str(gt_path)))

    va, vb = a.Volume(), b.Volume()
    aa, ab = a.Area(), b.Area()
    print(f"  volume  mine {va:10.2f}  gt {vb:10.2f}  delta {va - vb:+8.2f} mm^3"
          f"  ({(va - vb) / vb * 100:+.3f} %)")
    print(f"  area    mine {aa:10.2f}  gt {ab:10.2f}  delta {aa - ab:+8.2f} mm^2")

    t0 = time.time()
    ma, mb = to_mesh(a), to_mesh(b)
    for label, m in (("mine", ma), ("gt", mb)):
        lo, hi = m.bounds
        print(f"  bbox {label:4s} [{lo[0]:.3f},{lo[1]:.3f},{lo[2]:.3f}]"
              f" .. [{hi[0]:.3f},{hi[1]:.3f},{hi[2]:.3f}]")

    pts_a, d_a = deviation(ma, mb, SAMPLES)   # my surface vs gt
    pts_b, d_b = deviation(mb, ma, SAMPLES)   # gt surface vs mine
    print(f"  deviation mine->gt: mean {d_a.mean():.4f}  p99 {np.percentile(d_a, 99):.4f}"
          f"  max {d_a.max():.3f} mm")
    print(f"  deviation gt->mine: mean {d_b.mean():.4f}  p99 {np.percentile(d_b, 99):.4f}"
          f"  max {d_b.max():.3f} mm  ({time.time() - t0:.0f}s)")
    cluster_report(pts_a, d_a, 0.1, "mine->gt > 0.1")
    cluster_report(pts_b, d_b, 0.1, "gt->mine > 0.1")


def _require_verify_deps() -> None:
    if trimesh is None or np is None:
        sys.exit("verification needs trimesh/rtree/scipy: pip install '.[verify]' (or pass --no-verify)")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    verify = "--no-verify" not in sys.argv
    if verify:
        _require_verify_deps()

    for name, builder in (("uc2v4_master_insert", build_master_insert),
                          ("uc2v4_lens_insert", build_lens_insert)):
        print(f"=== {name}")
        t0 = time.time()
        part = builder()
        print(f"  built in {time.time() - t0:.1f}s")
        cq.exporters.export(part, str(OUT / f"{name}.step"))
        cq.exporters.export(part, str(OUT / f"{name}.stl"), tolerance=0.02)
        print(f"  wrote {OUT / (name + '.step')}")
        if verify:
            if not GT[name].exists():
                sys.exit(f"ground truth missing: {GT[name]}\n(pass --no-verify to build without checking)")
            report(name, part, GT[name])


if __name__ == "__main__":
    main()
