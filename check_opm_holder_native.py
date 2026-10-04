"""Verify the NATIVE Inventor launch holder (openuc2-opmsimulator/build_opm_holder_ipt.py) against the
CadQuery reference it was built from.

    uv run --with cadquery python check_opm_holder_native.py \
        "../openuc2-opmsimulator/INVENTOR/PRT - 9103 - OPMLNCHOL - V04.stp" generated/opm_launch

Inventor's STEP export breaks OCC booleans (see the repo notes), so everything here is
point sampling on the imported solid:

1. one solid, bounding box = the plan's body;
2. the RMS groove is a RIGHT-handed helix (points along a right-handed helix through the
   groove are void, along a left-handed one they are material);
3. thread bite: material where the objective's 20.32 mm ridges go, none inside 19.8 mm;
4. beam path, cylinder slot, collimator bores and clip slot are void where they should be,
   the clamp screw holes pass and their heads are recessed;
5. the native part agrees with the CadQuery holder on random samples (mismatches allowed
   only at the thread, whose profile is modelled differently).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import cadquery as cq


def inside(shape, x, y, z, tol=1e-4) -> bool:
    return bool(shape.isInside(cq.Vector(x, y, z), tol))


def main(argv) -> int:
    stp = Path(argv[1]) if len(argv) > 1 else Path("../openuc2-opmsimulator/INVENTOR/PRT - 9103 - OPMLNCHOL - V04.stp")
    gen = Path(argv[2]) if len(argv) > 2 else Path("generated/opm_launch")
    plan = json.loads((gen / "opm_launch_plan.json").read_text())
    p = plan["params"]
    nat = cq.importers.importStep(str(stp)).val()
    ref = cq.importers.importStep(str(gen / "opm_launch_holder.step")).val()
    ok_all = True

    def check(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"  {'OK  ' if cond else 'FAIL'} {name} {detail}")

    print(f"=== {stp.name}")
    bb = nat.BoundingBox()
    check("one solid", len(nat.Solids()) == 1, f"({len(nat.Solids())})")
    check("body extents", abs(bb.xmin - p["front_x"]) < 0.05 and abs(bb.xmax - p["back_x"]) < 0.05
          and abs(bb.ymax - p["width"] / 2) < 0.05 and abs(bb.zmax - p["height"] / 2) < 0.05,
          f"x {bb.xmin:.2f}..{bb.xmax:.2f} y {bb.ymin:.2f}..{bb.ymax:.2f} z {bb.zmin:.2f}..{bb.zmax:.2f}")

    # --- thread handedness
    pitch, front, lead = p["rms_pitch"], p["front_x"], p["lead_in"]
    hb = p["thread_depth"] + p["crest_flat"] / 2
    x0 = front + lead + hb + pitch / 2                       # first groove centre (builder convention)
    r = (p["crest_r"] + p["bore_r"]) / 2

    def helix_material(handed):
        return [inside(nat, x0 + t, r * math.cos(math.pi / 2 + handed * 2 * math.pi * t / pitch),
                       r * math.sin(math.pi / 2 + handed * 2 * math.pi * t / pitch), 1e-3)
                for t in [k * pitch + pitch / 4 for k in range(3)]]
    R, L = helix_material(+1), helix_material(-1)
    check("RMS groove right-handed", not any(R) and all(L), f"(right-helix material {R}, left-helix material {L})")

    # --- thread bite
    random.seed(7)

    def fraction(rad, n=300):
        hits = 0
        for _ in range(n):
            x = front + lead + 0.3 + random.random() * (p["thread_len"] - lead - 0.6)
            a = random.random() * 2 * math.pi
            hits += inside(nat, x, rad * math.cos(a), rad * math.sin(a))
        return hits / n
    f_major, f_minor = fraction(p["rms_major"] / 2), fraction(9.90)
    check("thread bites a 20.32 barrel", 0.5 < f_major < 0.95, f"(material fraction at r 10.16: {f_major:.2f})")
    check("thread frees a 19.8 barrel", f_minor == 0.0, f"(material fraction at r 9.90: {f_minor:.2f})")

    # --- voids where they belong
    t = plan["rms_thread"]
    check("beam bore clear", not any(inside(nat, x, 0, 0) for x in (t["to_x"] + 1, p["col_front_x"] - 1))
          and not any(inside(nat, x, 4.5 * math.cos(a), 4.5 * math.sin(a)) for x in (t["to_x"] + 1, p["col_front_x"] - 1) for a in (0.3, 2.1, 4.0)))
    xc = 0.5 * (p["cyl_x0"] + p["cyl_x1"])
    check("cylinder slot open to +y", not inside(nat, xc, 0.0, 0.0) and not inside(nat, xc, p["width"] / 2 - 0.5, 5.5)
          and inside(nat, xc, -(p["cyl_h"] / 2 + p["fit"]) - 0.5, 0.0) and inside(nat, xc, 0.0, p["cyl_len"] / 2 + p["fit"] + 0.5))
    rb, rf = p["col_body_d"] / 2 + p["fit"], p["col_flange_d"] / 2 + p["fit"]
    check("collimator body bore", not inside(nat, p["col_front_x"] + 3, rb - 0.1, 0) and inside(nat, p["col_front_x"] + 3, rb + 0.15, 0))
    check("collimator seat step", inside(nat, p["col_front_x"] - 0.3, 5.5, 0))
    check("flange bore to the back", not inside(nat, p["back_x"] - 0.5, rf - 0.1, 0) and inside(nat, p["col_flange_x"] + 1, rf + 0.15, 0))
    xk = p["clip_x"] + p["clip_t"] / 2 + p["fit"]
    check("clip slot", not inside(nat, xk, -(p["clip_reach"] + p["fit"]) + 0.3, 0) and not inside(nat, xk, p["width"] / 2 - 0.3, p["clip_half_h"] - 0.3)
          and inside(nat, xk, -(p["clip_reach"] + p["fit"]) - 0.4, 0) and inside(nat, xk, 0.0, p["clip_half_h"] + p["fit"] + 0.4))
    for x, z in p["screws_xz"]:
        check(f"clamp screw at x={x:g} z={z:g} passes", not any(inside(nat, x, y, z) for y in (-p["width"] / 2 + 0.5, 0.0, p["width"] / 2 - 0.5)))
        check(f"  head recess d{p['head_cbore_d']} x {p['head_cbore_depth']}", not inside(nat, x + p["head_cbore_d"] / 2 - 0.3, p["width"] / 2 - p["head_cbore_depth"] + 0.3, z)
              and inside(nat, x + p["head_cbore_d"] / 2 - 0.3, p["width"] / 2 - p["head_cbore_depth"] - 0.4, z))
    # long-edge chamfer: the corner of the body is gone
    check("long-edge chamfer", not inside(nat, (p["front_x"] + p["tail_from_x"]) / 2, p["width"] / 2 - 0.2, p["height"] / 2 - 0.2))

    # --- sampled agreement with the CadQuery holder, outside the thread
    n_pts, mism, mism_thread = 4000, 0, 0
    random.seed(11)
    for _ in range(n_pts):
        x = bb.xmin + random.random() * (bb.xmax - bb.xmin)
        y = bb.ymin + random.random() * (bb.ymax - bb.ymin)
        z = bb.zmin + random.random() * (bb.zmax - bb.zmin)
        if inside(nat, x, y, z) != inside(ref, x, y, z):
            if x < t["to_x"] + 0.3 and math.hypot(y, z) < p["bore_r"] + p["lead_in"] + 0.6:
                mism_thread += 1
            else:
                mism += 1
    check("matches the CadQuery holder", mism <= n_pts * 0.003,
          f"({mism} of {n_pts} samples differ outside the thread, {mism_thread} at the thread)")
    print(f"volumes: native {nat.Volume():.0f} mm3, CadQuery {ref.Volume():.0f} mm3")
    print("ALL OK" if ok_all else "SOME CHECKS FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    code = main(sys.argv)
    sys.stdout.flush()
    os._exit(code)                # CadQuery segfaults at interpreter exit on this machine
