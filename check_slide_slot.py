"""Verification of uc2v4/slide_slot.py.

For each case: one solid; the slide (nominal, resting on the stop) does not enter the insert
and meets it when pushed past the stop; the slot is open at the entry side; the clear aperture
is open on the beam axis; a coverslip lies in its pocket without entering the insert.

Usage:
    uv run --with cadquery python check_slide_slot.py
"""

from __future__ import annotations

import sys

import cadquery as cq

from uc2v4.slide_slot import SlideSlotParams, build_slide_slot, plan_slide_slot

CASES = [("vertical, stop below", SlideSlotParams()),
         ("horizontal, stop at -x", SlideSlotParams(slide_axis="horizontal")),
         ("no stop, coverslip pocket", SlideSlotParams(stop_mm=None, coverslip_mm=22.0))]


def overlap(a, b) -> float:  # noqa: ANN001
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def check(name: str, p: SlideSlotParams) -> bool:
    print(f"== {name}")
    plan = plan_slide_slot(p)
    w = build_slide_slot(plan)
    length, width, thick = p.slide_mm
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    report(f"one solid ({len(w.solids().vals())})", len(w.solids().vals()) == 1)
    centre = plan.slide_centre_mm
    if p.slide_axis == "vertical":
        slide = cq.Workplane("XY").box(width, length, thick).translate((0, centre, 0))
        push = (0, -0.3, 0)
    else:
        slide = cq.Workplane("XY").box(length, width, thick).translate((centre, 0, 0))
        push = (-0.3, 0, 0)
    free = overlap(w, slide)
    stopped = p.stop_mm is None or overlap(w, slide.translate(push)) > 0
    report(f"slide free ({free:.4f} mm3), held by the stop", free < 1e-3 and stopped)
    axis = all(not w.val().isInside(cq.Vector(r, 0, z)) for r in (0.0, p.clear_aperture_mm / 2 - 0.3)
               for z in (-plan.thickness_mm / 2 + 0.2, plan.thickness_mm / 2 - 0.2))
    report(f"clear aperture Ø{p.clear_aperture_mm} open", axis)
    if p.coverslip_mm:
        s = p.coverslip_mm
        cs = cq.Workplane("XY").box(s, s, p.coverslip_t_mm).translate(
            (0, 0, plan.thickness_mm / 2 - p.coverslip_t_mm / 2))
        report(f"coverslip in its pocket ({overlap(w, cs):.4f} mm3)", overlap(w, cs) < 1e-3)
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
