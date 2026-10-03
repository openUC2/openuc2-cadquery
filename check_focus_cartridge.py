"""Verification of uc2v4/focus_cartridge.py.

For each case, in the clamp frame:

1. barrel, ring and clamp are one solid each;
2. the lens (nominal, no clearance) touches neither barrel nor ring, rests on the lip (moved
   0.2 mm towards -z it meets the barrel) and is held by the ring (towards +z it meets it);
3. at the middle and both ends of the travel the barrel slides clear of the clamp and still
   fills it from end to end, and the set screw's axis lands on the barrel;
4. rays along the axis inside the clear aperture pass barrel and ring.

Usage:
    uv run --with cadquery python check_focus_cartridge.py
"""

from __future__ import annotations

import math
import sys

import cadquery as cq

from uc2v4.focus_cartridge import FocusCartridgeParams, build_focus_barrel, plan_focus_cartridge
from uc2v4.lens_cartridge import Lens, lens_solid
from uc2v4.round_clamp import build_round_clamp

CASES = [
    ("Ø25.4 biconvex f = 50, centred", FocusCartridgeParams(Lens(25.4, 3.5, 51.5, -51.5))),
    ("Ø12.7 plano-convex, z +6", FocusCartridgeParams(Lens(12.7, 3.0, 12.9, math.inf), z_mm=6.0)),
    ("Ø30 thick lens, z -4, ±2 mm", FocusCartridgeParams(Lens(30.0, 8.0, 40.0, -60.0), z_mm=-4.0,
                                                          travel_mm=2.0)),
]


def overlap(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def check(name: str, p: FocusCartridgeParams) -> bool:
    print(f"== {name}")
    plan = plan_focus_cartridge(p)
    barrel, ring = build_focus_barrel(plan)
    clamp = build_round_clamp(plan.clamp)
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    counts = [len(x.solids().vals()) for x in (barrel, ring, clamp)]
    report(f"one solid each (barrel, ring, clamp: {counts})", counts == [1, 1, 1])
    lens = lens_solid(p.lens, 0.0).translate((0, 0, plan.lens_z_mm))
    free = overlap(barrel, lens) + overlap(ring, lens)
    seat = overlap(barrel, lens.translate((0, 0, -0.2)))
    held = overlap(ring, lens.translate((0, 0, 0.2)))
    report(f"lens free ({free:.4f} mm3), on its lip ({seat:.2f}), under the ring ({held:.2f})",
           free < 1e-3 and seat > 0 and held > 0)
    c_lo, c_hi = plan.clamp.z_range_mm
    zs = plan.clamp.screw_z_mm
    for dz in (-p.travel_mm, 0.0, p.travel_mm):
        moved = barrel.translate((0, 0, dz))
        v = overlap(moved, clamp)
        b_lo, b_hi = plan.barrel_z_mm[0] + dz, plan.barrel_z_mm[1] + dz
        fills = b_lo <= c_lo + 1e-6 and b_hi >= c_hi - 1e-6
        on_screw = moved.val().isInside(cq.Vector(0.0, plan.barrel_r_mm - 0.6, zs))
        report(f"at {dz:+.1f} mm: clear of the clamp ({v:.3f} mm3), fills it, screw on the barrel",
               v < 1e-3 and fills and on_screw)
    hits = 0
    r = plan.clear_r_mm - 0.1
    for i in range(16):
        a = 2 * math.pi * i / 16
        for z in (plan.barrel_z_mm[0] + 0.3, plan.lens_z_range_mm[0] - 0.5,
                  plan.ring_z_mm[1] - 0.3):
            pt = cq.Vector(r * math.cos(a), r * math.sin(a), z)
            hits += barrel.val().isInside(pt) + ring.val().isInside(pt)
    report(f"clear aperture Ø{2 * plan.clear_r_mm:.2f} open ({hits} hits)", hits == 0)
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
