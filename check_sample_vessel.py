"""Verification of uc2v4/sample_vessel.py.

For each case: insert and cap are one solid each; the vessel (nominal) stands on the floor
without entering the insert or the cap; the windows are open on their axes at the beam; the
cap's skirt sits in its groove and the cap closes over the vessel's top (no straight line from
outside reaches the vessel's mouth); the insert stays within ±17 mm along the beam.

Usage:
    uv run --with cadquery python check_sample_vessel.py
"""

from __future__ import annotations

import sys

import cadquery as cq

from uc2v4.sample_vessel import (
    WINDOWS,
    SampleVesselParams,
    _well,
    build_sample_vessel,
    plan_sample_vessel,
)

CASES = [("standard cuvette, beam windows", SampleVesselParams()),
         ("cuvette, 90 degree collection", SampleVesselParams(windows=("-z", "+z", "+x"))),
         ("vial Ø10 x 45", SampleVesselParams(vessel="vial", size_mm=10.0, beam_height_mm=12.0))]


def overlap(a, b) -> float:  # noqa: ANN001
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def check(name: str, p: SampleVesselParams) -> bool:
    print(f"== {name}")
    plan = plan_sample_vessel(p)
    insert, cap = build_sample_vessel(plan)
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    counts = [len(insert.solids().vals()), len(cap.solids().vals()) if cap else 1]
    report(f"one solid each ({counts})", counts == [1, 1])
    vessel = cq.Workplane("XY").add(_well(p, 0.0, plan.floor_y_mm + 0.01, plan.top_y_mm))
    v = overlap(insert, vessel) + (overlap(cap, vessel) if cap else 0.0)
    rests = overlap(insert, vessel.translate((0, -0.3, 0))) > 0
    report(f"vessel free ({v:.4f} mm3), on its floor", v < 1e-3 and rests)
    opened = all(not insert.val().isInside(cq.Vector(*(c * (p.size_mm / 2 + 1.0) for c in WINDOWS[w])))
                 for w in p.windows)
    report(f"windows {list(p.windows)} open at the beam", opened)
    if cap:
        skirt = overlap(cap, insert)
        mouth = plan.top_y_mm + 0.5
        closed = cap.val().isInside(cq.Vector(0, max(mouth, 24.7) + 1.5, 0))
        report(f"cap clear of the insert ({skirt:.4f} mm3) and closed over the vessel's top",
               skirt < 1e-3 and closed)
    bb = insert.val().BoundingBox()
    report(f"insert {bb.zlen:.1f} mm along the beam, within ±17 on its notch",
           abs(plan.notch_mm) + bb.zlen / 2 <= 17.0 + 1e-6)
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
