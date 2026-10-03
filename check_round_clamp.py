"""Verification of uc2v4/round_clamp.py.

For each case, in the cube frame (the clamp's joint plane at its notch):

1. the clamp is one solid;
2. the body (nominal Ø, no clearance) does not touch it;
3. it meets the two master inserts no more than the plain base-holder disc does (the
   lens cartridge's seat: about 75 mm³ each, at the cone);
4. the set-screw hole runs from the bore out through the wall, and the wall gives the
   screw at least 4 mm of thread;
5. it stays in the cube: round parts within ±18.6 mm (r ≤ 19.2), a boss within ±17 mm;
6. the screw head is inside the face port, so a hex key reaches it.

Usage:
    uv run --with cadquery python check_round_clamp.py
"""

from __future__ import annotations

import math
import sys

import cadquery as cq

from uc2v4.master_insert import MasterInsertParams, build_master_insert
from uc2v4.round_holder import build_base_holder
from uc2v4.round_clamp import (
    MIN_THREAD_MM,
    PORT_HALF_MM,
    SCREWS,
    RoundClampParams,
    seat,
    build_round_clamp,
    plan_round_clamp,
)

CASES = [
    ("Ø11 laser module, centred", RoundClampParams(body_d_mm=11.0)),
    ("Ø12 fibre collimator, joint +7", RoundClampParams(body_d_mm=12.0, z_mm=6.5)),
    ("Ø25.4 lens tube, joint -8", RoundClampParams(body_d_mm=25.4, z_mm=-8.0)),
    ("Ø30 LED tube, M4", RoundClampParams(body_d_mm=30.0, screw="M4")),
    ("Ø34 body, boss for the screw", RoundClampParams(body_d_mm=34.0, z_mm=-3.0)),
    ("Ø8 body 4 mm off the axis", RoundClampParams(body_d_mm=8.0, offset_mm=(4.0, 0.0))),
]


def overlap(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        common = a.intersect(b)
        return sum(s.Volume() for s in common.solids().vals())
    except Exception:  # noqa: BLE001 — OCC raises on an empty common
        return 0.0


def inside(shape: cq.Workplane, point: tuple[float, float, float]) -> bool:
    return shape.val().isInside(cq.Vector(*point), 1e-4)


def check(name: str, params: RoundClampParams) -> bool:
    print(f"== {name}")
    plan = plan_round_clamp(params)
    t = params.master_thickness_mm
    j = plan.joint_z_mm
    clamp = build_round_clamp(plan).translate((0, 0, j))
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    report(f"one solid ({len(clamp.solids().vals())})", len(clamp.solids().vals()) == 1)
    dx, dy = params.offset_mm
    body = cq.Workplane("XY").add(cq.Solid.makeCylinder(
        params.body_d_mm / 2.0, 80.0, cq.Vector(dx, dy, -40.0), cq.Vector(0, 0, 1)))
    v = overlap(clamp, body)
    report(f"body Ø{params.body_d_mm} clear of the clamp (overlap {v:.3f} mm³)", v < 1e-3)

    notched_back = plan.notched_half == "back"
    masters = []
    for side, rib in ((-1.0 if notched_back else 1.0, True), (1.0 if notched_back else -1.0, False)):
        insert = build_master_insert(MasterInsertParams(corner_rib=rib))
        if side > 0:
            insert = insert.rotate((0, 0, 0), (1, 0, 0), 180)
        masters.append(insert.translate((0.0, 0.0, j + side * t / 2.0)))
    front = build_base_holder(seat())
    disc = front.union(cq.Workplane("XY").add(front.val().mirror("XY"))).translate((0, 0, j))
    v = sum(overlap(clamp, m) for m in masters)
    ref = sum(overlap(disc, m) for m in masters)
    report(f"master inserts: overlap {v:.2f} mm3, the plain disc's {ref:.2f} mm3", v <= ref + 1.0)

    pilot, boss_r, head_r = SCREWS[params.screw]
    a = math.radians(params.screw_angle_deg)
    u = (math.cos(a), math.sin(a))
    zs = j + plan.screw_z_mm
    r_in = plan.bore_r_mm + 0.3
    r_out = max(plan.sleeve_r_mm, plan.boss_top_mm) - 0.3
    hole_open = not any(inside(clamp, (dx + r * u[0], dy + r * u[1], zs))
                        for r in (r_in, (r_in + r_out) / 2.0, r_out))
    wall = max(plan.sleeve_r_mm, plan.boss_top_mm) - plan.bore_r_mm
    in_wall = inside(clamp, (dx + (r_in + r_out) / 2.0 * u[0] + (pilot / 2.0 + 0.4) * -u[1],
                             dy + (r_in + r_out) / 2.0 * u[1] + (pilot / 2.0 + 0.4) * u[0], zs))
    report(f"screw hole open from the bore, {wall:.2f} mm of wall around it",
           hole_open and in_wall and wall >= MIN_THREAD_MM - 1e-6)

    bb = clamp.val().BoundingBox()
    reach = max(abs(bb.zmin), abs(bb.zmax))
    sleeve_reach = max(abs(j + plan.z_range_mm[0]), abs(j + plan.z_range_mm[1]))
    boss_ok = (not plan.boss_r_mm) or abs(zs) + boss_r <= 17.0 + 1e-6
    report(f"in the cube: sleeve to {sleeve_reach:.2f} mm (≤ 18.6, r {plan.sleeve_r_mm:.2f} "
           f"≤ 19.2), clamp to {reach:.2f} mm, boss within ±17: {boss_ok}",
           sleeve_reach <= 18.6 + 1e-6 and plan.sleeve_r_mm <= 19.2 + 1e-6 and boss_ok)
    report(f"screw head at {abs(zs):.2f} mm, inside the ±{PORT_HALF_MM:g} mm port",
           abs(zs) + head_r <= PORT_HALF_MM + 1e-6)
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
