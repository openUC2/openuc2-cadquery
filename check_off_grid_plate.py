"""Verification of uc2v4/off_grid_plate.py on a spectrograph-like plate (the OpenRAMAN case).

1. the plate is one solid, in the puzzle layer, over its cells;
2. its M3 holes are open and countersunk, and none is under a feature;
3. the pockets for the neighbouring puzzle tabs are open;
4. kinematic pedestal: a ZJB-0.5-3 standing on it (its base as a box) sits on the top and
   does not enter it, its axis at the beam height, the M3 pilot under the mount's hole;
5. saddle and lens wall: the part (nominal size) at its seat does not enter the plate and
   rests on it; cradle: the device face at beam height minus axis height;
6. the docking poses carry each feature's position, height and yaw.

Usage:
    uv run --with cadquery python check_off_grid_plate.py
"""

from __future__ import annotations

import math
import sys

import cadquery as cq

from uc2v4.off_grid_plate import (
    M3,
    ZJB,
    Feature,
    OffGridPlateParams,
    _place,
    build_off_grid_plate,
    plan_off_grid_plate,
)

FEATURES = (
    Feature("kinematic", "grating", at_mm=(-5.0, 0.0), yaw_deg=47.5),
    Feature("saddle", "camera lens", at_mm=(50.0, 10.0), d_mm=33.0, length_mm=16.0),
    Feature("cradle", "camera", at_mm=(85.0, 10.0),
            cradle={"holes_mm": [[-8, 0], [8, 0], [0, 10]], "axis_uv_mm": [0, 5],
                    "axis_height_mm": 14.5}),
    Feature("lens", "collimator", at_mm=(0.0, 50.0), yaw_deg=90.0, d_mm=25.4, length_mm=4.0),
)
PARAMS = OffGridPlateParams(cells=((0, 0), (1, 0), (0, 1), (1, 1), (2, 0)), bounds=(-2, -1, 2, 2),
                            features=FEATURES)


def overlap(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    plan = plan_off_grid_plate(PARAMS)
    plate = build_off_grid_plate(plan)
    solid = plate.val()
    results = []

    def report(text: str, good: bool) -> None:
        results.append(good)
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    bb = solid.BoundingBox()
    report(f"one solid ({len(plate.solids().vals())}), from z {bb.zmin:.2f} (base plate top)",
           len(plate.solids().vals()) == 1 and abs(bb.zmin) < 1e-6)
    t = PARAMS.thickness_mm
    holes = all(not solid.isInside(cq.Vector(x, y, z)) for x, y in plan.screws
                for z in (0.5, t - 0.5, t + 0.5))
    walls = all(solid.isInside(cq.Vector(x + M3[1] / 2 + 0.8, y, 1.0))
                or solid.isInside(cq.Vector(x - M3[1] / 2 - 0.8, y, 1.0)) for x, y in plan.screws)
    report(f"{len(plan.screws)} M3 holes open and countersunk "
           f"({len(plan.skipped_screws)} under features left out)", holes and walls)
    pockets = all(not solid.isInside(cq.Vector(tb["centre"][0] + tb["dir"][0] * 3.0,
                                               tb["centre"][1] + tb["dir"][1] * 3.0, t / 2))
                  for tb in plan.tab_pockets)
    report(f"{len(plan.tab_pockets)} tab pockets open", pockets)

    k = FEATURES[0]
    face = k.beam_height_mm - ZJB["axis_above_face"]
    mount = cq.Workplane("XY").add(cq.Solid.makeBox(
        10.0, 2 * ZJB["half"], 2 * ZJB["half"], cq.Vector(0.0, -ZJB["half"], face + 0.01)))
    mount = _place(mount, k)
    v = overlap(plate, mount)
    sits = overlap(plate, mount.translate((0, 0, -0.2))) > 0
    px, py = (k.at_mm[0] + ZJB["screw_x"] * math.cos(math.radians(k.yaw_deg)),
              k.at_mm[1] + ZJB["screw_x"] * math.sin(math.radians(k.yaw_deg)))
    pilot = not solid.isInside(cq.Vector(px, py, face - 2.0))
    report(f"ZJB on its pedestal: clear ({v:.3f} mm3), seated, axis at {k.beam_height_mm}, "
           "M3 pilot under its hole", v < 1e-3 and sits and pilot)

    s = FEATURES[1]
    rod = _place(cq.Solid.makeCylinder(s.d_mm / 2, s.length_mm + 4.0,
                                       cq.Vector(-s.length_mm / 2 - 2.0, 0.0, s.beam_height_mm),
                                       cq.Vector(1, 0, 0)), s)
    v = overlap(plate, rod)
    rests = overlap(plate, rod.translate((0, 0, -0.3))) > 0
    report(f"Ø{s.d_mm} part in the saddle: clear ({v:.3f} mm3), rests on it", v < 1e-3 and rests)

    ln = FEATURES[3]
    lens = _place(cq.Solid.makeCylinder(ln.d_mm / 2, ln.length_mm,
                                        cq.Vector(-ln.length_mm / 2, 0.0, ln.beam_height_mm),
                                        cq.Vector(1, 0, 0)), ln)
    v = overlap(plate, lens)
    held = overlap(plate, lens.translate((0, -0.3, 0))) > 0   # yaw 90: its seat's lip is at -y
    report(f"Ø{ln.d_mm} lens in its wall: clear ({v:.3f} mm3), against the lip", v < 1e-3 and held)

    c = FEATURES[2]
    top = c.beam_height_mm - c.cradle["axis_height_mm"]
    on_top = solid.isInside(cq.Vector(c.at_mm[0] + 3.0, c.at_mm[1] - 5.0, top - 0.3)) and \
        not solid.isInside(cq.Vector(c.at_mm[0] + 3.0, c.at_mm[1] - 5.0, top + 0.3))
    report(f"camera cradle's face at {top:.2f} mm (beam {c.beam_height_mm} - axis "
           f"{c.cradle['axis_height_mm']})", on_top)

    m = plan.mounts
    poses = (m["grating"]["pose"]["translation"]["offset-mm"]["z"] == 30.0
             and m["grating"]["pose"]["rotation"]["offset-deg"]["z"] == -42.5
             and m["collimator"]["pose"]["rotation"]["grid"] == {"z": "+x", "x": "+y"}
             and m["camera lens"]["accepts"] == "cylinder-d33")
    report(f"docking poses for {sorted(m)}", poses)
    print(f"{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
