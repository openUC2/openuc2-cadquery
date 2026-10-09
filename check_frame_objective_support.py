"""Check the FRAME objective support against its rules and, given the CAD, against FRAME-0402/0408.

    uv run python check_frame_objective_support.py [--cad "FRAME - 0402 ... .stp" 16.4 ...] [--step 1.0]

Without --cad it builds the RMS, M25 and labelled variants and checks the plan rules and the
parfocal solve; with --cad it also compares each STEP (moved to the support frame: slot axis at
x 14.9, sled top at z 12.5 in the CAD) with the model at the given height.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import cadquery as cq

from uc2v4.frame_objective_support import (
    ObjectiveFacts,
    ObjectiveSupportParams,
    build_objective_support,
    parfocal_heights,
    plan_objective_support,
)

failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


def _inside(shape: cq.Shape, pts: list[tuple[float, float, float]]) -> list[bool]:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    out = []
    for p in pts:
        cls.Perform(gp_Pnt(*p), 1e-6)
        out.append(cls.State() == TopAbs_IN)
    return out


def compare(cad_path: str, height: float, step: float = 0.5) -> None:
    """Symmetric difference by sampling a grid (OCC's boolean fails on the CAD's coil thread)."""
    cad = cq.importers.importStep(cad_path).val().translate(cq.Vector(-14.9, 0, -12.5))
    model = build_objective_support(plan_objective_support(ObjectiveSupportParams(height_mm=height))).val()
    bc, bm = cad.BoundingBox(), model.BoundingBox()
    n = lambda lo, hi: [lo + step * (i + 0.5) for i in range(int((hi - lo) / step))]
    pts = [(x, y, z) for x in n(bc.xmin, bc.xmax) for y in n(bc.ymin, bc.ymax) for z in n(bc.zmin, bc.zmax)]
    a, b = _inside(cad, pts), _inside(model, pts)
    cell = step ** 3
    only_cad = sum(1 for i, j in zip(a, b) if i and not j) * cell
    only_model = sum(1 for i, j in zip(a, b) if j and not i) * cell
    box_ok = all(abs(a - b) < 0.05 for a, b in zip(
        (bc.xmin, bc.xmax, bc.ymin, bc.ymax, bc.zmin, bc.zmax),
        (bm.xmin, bm.xmax, bm.ymin, bm.ymax, bm.zmin, bm.zmax)))
    print(f"     CAD {cad.Volume():.0f} mm3, model {model.Volume():.0f}, only in CAD {only_cad:.0f}, "
          f"only in model {only_model:.0f}")
    check(box_ok, f"{cad_path.split('/')[-1]}: same bounding box at height {height}")
    check(only_cad + only_model < 0.06 * cad.Volume(),
          f"{cad_path.split('/')[-1]}: differs by under 6 % of its volume (thread form, label)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cad", nargs=2, action="append", metavar=("STEP", "HEIGHT"), default=[])
    ap.add_argument("--step", type=float, default=1.0, help="sampling grid for --cad, mm")
    args = ap.parse_args()

    rms = ObjectiveSupportParams(height_mm=16.4)
    plan = plan_objective_support(rms)
    check(abs(plan.bore_d_mm - 20.5) < 1e-9 and abs(plan.boss_d_mm - 25.4) < 1e-9,
          "RMS: Ø20.5 bore and Ø25.4 boss, as FRAME-0402")
    check(not plan.pockets, "RMS: the screw heads sit beside the boss")
    part = build_objective_support(plan).val()
    bb = part.BoundingBox()
    check(abs(bb.ymax - 15.856) < 0.01 and abs(bb.zmax - 16.4) < 1e-6, "RMS: lugs reach y 15.86, top at 16.4")

    m25 = replace(rms, thread="M25x0.75", height_mm=8.0)
    p25 = plan_objective_support(m25)
    check(p25.pockets and len(build_objective_support(p25).solids().vals()) == 1,
          "M25: the wider boss gets screw pockets and stays one solid")
    try:
        plan_objective_support(replace(rms, thread="M32x0.75"))
        check(False, "M32: refused (the bore reaches the sled's screws)")
    except ValueError:
        check(True, "M32: refused (the bore reaches the sled's screws)")
    try:
        plan_objective_support(replace(rms, height_mm=4.0))
        check(False, "a support below the flange + thread is refused")
    except ValueError:
        check(True, "a support below the flange + thread is refused")

    # OCC's Volume() is unreliable once the thread's ruled faces meet the engraving; count faces.
    labelled = build_objective_support(plan_objective_support(replace(rms, label="4x"))).val()
    check(len(labelled.Faces()) > len(part.Faces()) + 10 and labelled.isValid(), "the label is engraved")

    four = replace(rms, objective=ObjectiveFacts(45.0, 17.3, 4.5))
    plane, heights = parfocal_heights([four, four])
    check(abs(plane - 61.4) < 1e-9 and heights == [16.4, 16.4], "two PF-45 objectives: the CAD's 16.4 mm")
    apo = replace(rms, thread="M25x0.75", objective=ObjectiveFacts(60.0, 1.0, 4.9))
    plane, (h4, h60) = parfocal_heights([four, apo])
    check(abs((h4 + 45) - (h60 + 60)) < 0.1 and h60 >= plan_objective_support(replace(apo, height_mm=h60)).min_height_mm,
          f"PF 45 + PF 60: one plane at {plane:.1f} mm, heights {h4:.1f} / {h60:.1f}")

    for path, height in args.cad:
        compare(path, float(height), args.step)
    print("\nall checks passed" if not failures else f"\n{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
