"""Verification harness for uc2v4/lens_cartridge.py.

For each case it checks the things that would actually bite on the bench:

1. each half is exactly one solid (printable as one piece);
2. the two halves do not overlap each other (they meet on the joint plane);
3. the *nominal* lens (no clearance) does not collide with either half —
   i.e. the pocket really is a negative of the lens at the requested pose;
4. the lens sits where it was asked to, measured back out of the geometry in
   the cube frame;
5. both halves stay inside the base-holder envelope, so they still drop into
   the molded master inserts.

Usage:
    uv run --with cadquery python check_lens_cartridge.py
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).parent


def load(name: str):
    pkg = HERE / "uc2v4"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    spec = importlib.util.spec_from_file_location(name, pkg / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


lc = load("lens_cartridge")

CASES = [
    ("centred 1-inch biconvex",
     lc.Lens(25.4, 3.5, 51.5, -51.5), lc.Pose(z_mm=0.0), lc.CartridgeParams()),
    ("offset in x/y, snapped to +5 notch",
     lc.Lens(12.7, 2.5, 25.8, -25.8), lc.Pose(x_mm=3.0, y_mm=-2.0, z_mm=6.1),
     lc.CartridgeParams()),
    ("thick plano-convex, extended front",
     lc.Lens(25.4, 6.0, 30.9, math.inf), lc.Pose(z_mm=-4.8),
     lc.CartridgeParams(extension_front_mm=3.0, extension_back_mm=3.0)),
    ("tilted 6 deg",
     lc.Lens(12.7, 3.0, math.inf, -25.0), lc.Pose(x_mm=1.5, z_mm=10.2, ry_deg=6.0),
     lc.CartridgeParams(extension_front_mm=2.0, extension_back_mm=2.0)),
    ("free slide (smooth master), exact z",
     lc.Lens(25.4, 3.5, 51.5, -51.5), lc.Pose(z_mm=7.3),
     lc.CartridgeParams(snap_to_notch=False)),
]


def solid_of(wp: cq.Workplane) -> cq.Solid:
    vals = wp.solids().vals()
    s = vals[0]
    for extra in vals[1:]:
        s = s.fuse(extra)
    return s


def check(name, lens, pose, params) -> bool:
    print(f"=== {name}")
    plan = lc.plan_cartridge(lens, pose, params=params)
    front, back = lc.build_cartridge(plan)
    ok = True

    nf, nb = len(front.solids().vals()), len(back.solids().vals())
    print(f"  solids: front={nf} back={nb}", "OK" if nf == nb == 1 else "FAIL")
    ok &= (nf == nb == 1)

    fs, bs = solid_of(front), solid_of(back)
    overlap = fs.intersect(bs).Volume()
    print(f"  half-to-half overlap: {overlap:.6f} mm^3",
          "OK" if overlap < 1e-6 else "FAIL")
    ok &= overlap < 1e-6

    # nominal lens, posed exactly as asked, in the cartridge frame
    nominal = lc._place(lc.lens_solid(lens, 0.0).val(), plan)
    clash = 0.0
    for half in (fs, bs):
        clash += half.intersect(nominal).Volume()
    print(f"  lens-vs-holder collision: {clash:.6f} mm^3",
          "OK" if clash < 1e-6 else "FAIL")
    ok &= clash < 1e-6

    # Where did the lens' *reference point* end up in the cube frame? This is
    # what closes the loop notch + residual == request. (The centroid is not
    # the reference point for an asymmetric lens, so it cannot be used here.)
    marker = cq.Solid.makeSphere(0.05, pnt=cq.Vector(0, 0, 0), angleDegrees1=-90)
    c = lc._place(marker, plan).Center()
    got = (c.x, c.y, c.z + plan.joint_z_mm)
    want = (pose.x_mm, pose.y_mm, pose.z_mm)
    err = max(abs(a - b) for a, b in zip(got, want))
    print(f"  lens reference cube-frame: ({got[0]:.3f}, {got[1]:.3f}, {got[2]:.3f})"
          f"  requested ({want[0]:.3f}, {want[1]:.3f}, {want[2]:.3f})"
          f"  err={err:.4f} mm", "OK" if err < 5e-3 else "FAIL")
    ok &= err < 5e-3

    # Snugness: the pocket must be a close negative, not a cavern. A lens grown
    # by well over the fit clearance has to interfere.
    fat = lc._place(lc.lens_solid(lens, params.fit_clearance_mm * 3.0).val(), plan)
    grip = sum(half.intersect(fat).Volume() for half in (fs, bs))
    print(f"  pocket snugness (oversized lens must clash): {grip:.4f} mm^3",
          "OK" if grip > 1e-3 else "FAIL")
    ok &= grip > 1e-3

    seat = params.seat(0.0, params.master_thickness_mm / 2.0)
    rmax = seat.max_radius + 0.6          # noses stand ~0.45 proud of the cone
    for label, half in (("front", fs), ("back", bs)):
        bb = half.BoundingBox()
        r = max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax))
        inside = r <= rmax + 1e-6
        print(f"  {label} envelope: r={r:.3f} <= {rmax:.3f}",
              "OK" if inside else "FAIL")
        ok &= inside

    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
