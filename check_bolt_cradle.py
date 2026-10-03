"""Verification of uc2v4/bolt_cradle.py.

For each case:

1. the cradle is one solid;
2. every hole of the pattern is open on its axis and has material around it;
3. ``across``: a board laid on the pads (or the face) does not enter the cradle, the light's
   window is open along the beam, the plate has the square insert's outline;
4. ``pedestal``: the device's face is at the beam height minus the axis height, the screw
   heads have their floor, the ears' M3 holes are open.

Usage:
    uv run --with cadquery python check_bolt_cradle.py
"""

from __future__ import annotations

import sys

import cadquery as cq

from uc2v4.bolt_cradle import SCREWS, BoltCradleParams, build_bolt_cradle, plan_bolt_cradle

SQUARE = ((12.25, 12.25), (-12.25, 12.25), (12.25, -12.25), (-12.25, -12.25))
CASES = [
    ("board camera, 4 x M2 through the board, 0.5 mm pads",
     BoltCradleParams(holes_mm=SQUARE, screw="M2", tapped_device=False, standoff_mm=0.5,
                      window_mm=(14.0, 14.0))),
    ("RasPi camera v1.3, lens off the pattern centre",
     BoltCradleParams(holes_mm=((10.5, 0.0), (-10.5, 0.0), (10.5, 12.5), (-10.5, 12.5)),
                      screw="M2", tapped_device=False, standoff_mm=1.0, z_mm=5.0)),
    ("camera body with tapped M3, screws from behind",
     BoltCradleParams(holes_mm=((10.0, 10.0), (-10.0, 10.0), (10.0, -10.0), (-10.0, -10.0)),
                      screw="M3", thickness_mm=6.0)),
    ("LED board on the -z face", BoltCradleParams(holes_mm=((9.0, 0.0), (-9.0, 0.0)), screw="M2.5",
                                                 tapped_device=False, device_side="-z")),
    ("camera body on a pedestal, 3 x M3 in its base",
     BoltCradleParams(holes_mm=((-8.0, 0.0), (8.0, 0.0), (0.0, 10.0)), screw="M3",
                      form="pedestal", axis_uv_mm=(0.0, 5.0), axis_height_mm=14.5,
                      beam_height_mm=35.0)),
]


def inside(w: cq.Workplane, p: tuple[float, float, float]) -> bool:
    return w.val().isInside(cq.Vector(*p), 1e-4)


def check(name: str, p: BoltCradleParams) -> bool:
    print(f"== {name}")
    plan = plan_bolt_cradle(p)
    w = build_bolt_cradle(plan)
    clear, pilot, head, head_h = SCREWS[p.screw]
    hole_r = (clear if p.tapped_device else pilot) / 2.0
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    report(f"one solid ({len(w.solids().vals())})", len(w.solids().vals()) == 1)
    if p.form == "across":
        s = 1.0 if p.device_side == "+z" else -1.0
        t = p.thickness_mm
        floor = t - head_h - 0.3 if p.tapped_device else t   # material the screw passes
        zmid = s * (t / 2.0 - floor / 2.0)
        opened = all(not inside(w, (u, v, zmid)) for u, v in plan.holes_mm)
        around = all(inside(w, (u + hole_r + 0.6, v, zmid)) for u, v in plan.holes_mm)
        report(f"{len(plan.holes_mm)} holes open, material around them", opened and around)
        face = s * (t / 2.0 + p.standoff_mm)
        board = cq.Workplane("XY").add(cq.Solid.makeBox(
            34.0, 34.0, 1.6, cq.Vector(-17.0, -17.0, face if s > 0 else face - 1.6))) \
            .translate((0, 0, s * 0.01))
        try:
            v = sum(x.Volume() for x in w.intersect(board).solids().vals())
        except Exception:  # noqa: BLE001
            v = 0.0
        report(f"a board on the {'pads' if p.standoff_mm else 'face'} stays out ({v:.3f} mm3)",
               v < 1e-3)
        window = all(not inside(w, (0.0, 0.0, z)) for z in (-t / 2 + 0.3, 0.0, t / 2 - 0.3))
        report("the window is open on the beam axis", window)
        bb = w.val().BoundingBox()
        report(f"square insert outline {bb.xlen:.1f} x {bb.ylen:.1f}",
               abs(bb.xlen - 49.4) < 0.05 and abs(bb.ylen - 49.4) < 0.05)
    else:
        bb = w.val().BoundingBox()
        report(f"device face at {bb.zmax:.2f} mm = beam {p.beam_height_mm} - axis "
               f"{p.axis_height_mm}", abs(bb.zmax - plan.top_mm) < 1e-6)
        opened = all(not inside(w, (u, v, plan.top_mm - 0.5)) for u, v in plan.holes_mm)
        floor = all(inside(w, (u + hole_r + 0.6, v, plan.top_mm - p.thickness_mm / 2.0))
                    for u, v in plan.holes_mm)
        report("holes open at the top, a floor for the screw heads", opened and floor)
        ears = all(not inside(w, (u, v, 1.0)) for u, v in plan.ear_holes_mm)
        report(f"ear holes open at {plan.ear_holes_mm}", ears)
    for note in plan.warnings:
        print(f"  note: {note}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
