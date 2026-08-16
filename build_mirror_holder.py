"""Build the parametric uc2v4 mirror holder and verify it against the
Inventor ground truth STEP in ./extracted/.

Usage:
    uv run --with cadquery --with trimesh --with rtree --with scipy \
        python build_mirror_holder.py [--no-verify]

Same mesh-domain comparison as build_uc2v4.py (Inventor-written STEP files
break OCC booleans, so b-rep XOR is not usable as an oracle). The module is
loaded by path rather than as a package so it keeps working regardless of
how uc2v4's intra-package imports are currently spelled.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh

HERE = Path(__file__).parent
OUT = HERE / "generated"
GT = HERE / "extracted" / "PRT_-_2111_-_MASINSMIRHOLUPP_-_C.step"

SAMPLES = 60000
TESS_TOL = 0.01


def load_round_holder():
    pkg = HERE / "uc2v4"
    sys.path.insert(0, str(pkg))
    spec = importlib.util.spec_from_file_location("round_holder", pkg / "round_holder.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # dataclasses resolves annotations via sys.modules
    spec.loader.exec_module(mod)
    return mod


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


def deviation(src, dst, n):
    pts, _ = trimesh.sample.sample_surface(src, n)
    _, dist, _ = trimesh.proximity.closest_point(dst, pts)
    return pts, dist


def cluster_report(pts, dist, threshold, label):
    bad = dist > threshold
    if not bad.any():
        print(f"    {label}: no deviations > {threshold} mm")
        return
    p, d = pts[bad], dist[bad]
    seen = {}
    for c, (pt, dv) in zip(map(tuple, np.round(p / 4.0).astype(int)), zip(p, d)):
        if c not in seen or dv > seen[c][1]:
            seen[c] = (pt, dv)
    print(f"    {label}: {bad.sum()}/{len(dist)} samples > {threshold} mm, "
          f"max {d.max():.3f} mm; worst spots:")
    for pt, dv in sorted(seen.values(), key=lambda t: -t[1])[:6]:
        print(f"      {dv:6.3f} mm at ({pt[0]:7.2f}, {pt[1]:7.2f}, {pt[2]:7.2f})")


def report(mine: cq.Workplane, gt_path: Path) -> None:
    a = fused_solid(mine)
    b = fused_solid(cq.importers.importStep(str(gt_path)))
    va, vb, aa, ab = a.Volume(), b.Volume(), a.Area(), b.Area()
    print(f"  volume  mine {va:10.2f}  gt {vb:10.2f}  delta {va - vb:+8.2f} mm^3"
          f"  ({(va - vb) / vb * 100:+.3f} %)")
    print(f"  area    mine {aa:10.2f}  gt {ab:10.2f}  delta {aa - ab:+8.2f} mm^2")

    t0 = time.time()
    ma, mb = to_mesh(a), to_mesh(b)
    for label, m in (("mine", ma), ("gt", mb)):
        lo, hi = m.bounds
        print(f"  bbox {label:4s} [{lo[0]:.3f},{lo[1]:.3f},{lo[2]:.3f}]"
              f" .. [{hi[0]:.3f},{hi[1]:.3f},{hi[2]:.3f}]")
    pts_a, d_a = deviation(ma, mb, SAMPLES)
    pts_b, d_b = deviation(mb, ma, SAMPLES)
    print(f"  deviation mine->gt: mean {d_a.mean():.4f}  p99 {np.percentile(d_a, 99):.4f}"
          f"  max {d_a.max():.3f} mm")
    print(f"  deviation gt->mine: mean {d_b.mean():.4f}  p99 {np.percentile(d_b, 99):.4f}"
          f"  max {d_b.max():.3f} mm  ({time.time() - t0:.0f}s)")
    cluster_report(pts_a, d_a, 0.1, "mine->gt > 0.1")
    cluster_report(pts_b, d_b, 0.1, "gt->mine > 0.1")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rh = load_round_holder()

    print("=== uc2v4_mirror_holder")
    t0 = time.time()
    part = rh.build_mirror_holder()
    print(f"  built in {time.time() - t0:.1f}s")
    cq.exporters.export(part, str(OUT / "uc2v4_mirror_holder.step"))
    cq.exporters.export(part, str(OUT / "uc2v4_mirror_holder.stl"), tolerance=0.02)

    print("=== uc2v4_base_holder (blank)")
    blank = rh.build_base_holder()
    cq.exporters.export(blank, str(OUT / "uc2v4_base_holder.step"))
    cq.exporters.export(blank, str(OUT / "uc2v4_base_holder.stl"), tolerance=0.02)
    print(f"  blank volume {blank.val().Volume():.2f} mm^3")

    if "--no-verify" not in sys.argv and GT.exists():
        print("=== verification")
        report(part, GT)


if __name__ == "__main__":
    main()
