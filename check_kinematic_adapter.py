"""Verification of uc2v4/kinematic_adapter.py against the ZJB-0.5-3 as CAD-new models it.

For each case, in the mount frame (mount axis +x):

1. the adapter is one solid;
2. it does not enter the mount's moving plate: the stub sits in the Ø12.8 bore, 0.1 mm off the
   lip, and fills it to the front face where the mount grips it;
3. the optic, at its pose, is clear of the adapter and rests in its pocket;
4. a transmissive adapter lets rays along the mount axis through its clear opening;
5. the adapter reaches no further from the mount axis than the plan says.

Usage:
    uv run --with cadquery python check_kinematic_adapter.py
"""

from __future__ import annotations

import math
import sys

import cadquery as cq

from uc2v4.kinematic_adapter import (
    KinematicAdapterParams,
    _optic_solid,
    _to_mount,
    build_kinematic_adapter,
    plan_kinematic_adapter,
)

CASES = [
    ("grating 25 x 25 x 6", KinematicAdapterParams(optic_wh_mm=(25.0, 25.0), optic_t_mm=6.0)),
    ("mirror Ø25.4 x 6", KinematicAdapterParams(optic_d_mm=25.4, optic_t_mm=6.0)),
    ("dichroic 35.6 x 25.2 x 1 at 45°",
     KinematicAdapterParams(optic_wh_mm=(35.6, 25.2), optic_t_mm=1.0, tilt_deg=45.0)),
    ("filter Ø25 x 5, transmissive",
     KinematicAdapterParams(optic_d_mm=25.0, optic_t_mm=5.0, transmissive=True)),
    ("mirror Ø25.4 x 6 at 20°", KinematicAdapterParams(optic_d_mm=25.4, optic_t_mm=6.0,
                                                       tilt_deg=20.0)),
    ("Ø10 x 2 in the bore, transmissive",
     KinematicAdapterParams(optic_d_mm=10.0, optic_t_mm=2.0, transmissive=True)),
]


def mount_plate(m) -> cq.Workplane:  # noqa: ANN001
    """The moving plate with its bore, from the numbers measured on the CAD-new part."""
    plate = cq.Workplane("XY").add(cq.Solid.makeBox(
        m.front_x_mm - 12.5, 2 * m.half_mm, 2 * m.half_mm, cq.Vector(12.5, -m.half_mm, -m.half_mm)))
    bore = cq.Solid.makeCylinder(m.bore_d_mm / 2, m.front_x_mm - m.lip_x_mm + 1.0,
                                 cq.Vector(m.lip_x_mm, 0, 0), cq.Vector(1, 0, 0))
    opening = cq.Solid.makeCylinder(m.opening_d_mm / 2, 2.0, cq.Vector(12.0, 0, 0),
                                    cq.Vector(1, 0, 0))
    return plate.cut(cq.Workplane("XY").add(bore)).cut(cq.Workplane("XY").add(opening))


def overlap(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001 — OCC raises on an empty common
        return 0.0


def check(name: str, p: KinematicAdapterParams) -> bool:
    print(f"== {name}")
    plan = plan_kinematic_adapter(p)
    adapter = build_kinematic_adapter(plan)
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    report(f"one solid ({len(adapter.solids().vals())})", len(adapter.solids().vals()) == 1)
    m = p.mount
    v = overlap(adapter, mount_plate(m))
    bb = adapter.val().BoundingBox()
    report(f"clear of the mount's plate (overlap {v:.3f} mm3), stub from x {bb.xmin:.2f} "
           f"(lip {m.lip_x_mm})", v < 1e-3 and abs(bb.xmin - (m.lip_x_mm + 0.1)) < 1e-6)
    stub_at_face = adapter.val().isInside(cq.Vector(m.front_x_mm - 0.5, plan.stub_r_mm - 0.3, 0))
    report("the stub fills the bore up to the front face", stub_at_face)

    optic = cq.Workplane("XY").add(_to_mount(_optic_solid(p, -0.02, p.optic_t_mm), plan))
    v = overlap(adapter, optic)
    seat = cq.Workplane("XY").add(_to_mount(_optic_solid(p, -0.1, p.optic_t_mm), plan)
                                  .translate(-cq.Vector(*plan.optic_normal) * 0.3))
    report(f"the optic is clear of the adapter ({v:.4f} mm3) and rests on its pocket floor "
           f"({overlap(adapter, seat):.2f} mm3 when pushed 0.3 mm in)",
           v < 1e-3 and overlap(adapter, seat) > 0.0)

    if plan.clear_r_mm:
        hits = 0
        for i in range(24):
            a = 2 * math.pi * i / 24
            for r in (0.0, 0.5 * plan.clear_r_mm, plan.clear_r_mm - 0.1):
                for x in (m.lip_x_mm + 0.5, m.front_x_mm + 0.5, plan.x_range_mm[1] - 0.2):
                    hits += adapter.val().isInside(cq.Vector(x, r * math.cos(a), r * math.sin(a)))
        report(f"rays along the axis through the Ø{2 * plan.clear_r_mm:.1f} opening: {hits} hits",
               hits == 0)
    side = max(abs(bb.ymin), abs(bb.ymax), abs(bb.zmin), abs(bb.zmax))
    report(f"reaches {side:.2f} mm from the axis, plan radius {plan.radius_mm:.2f}",
           side <= plan.radius_mm + 0.1)
    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
