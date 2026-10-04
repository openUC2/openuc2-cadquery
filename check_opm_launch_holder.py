"""Verification harness for the dvOPM launch holder (uc2v4/opm_launch_holder.py).

Builds the holder, its two side-slid retainers and the arc-rail bracket from an
opm_layout.json and asserts, in the BREP domain, what would bite on the bench:

1. every part is one valid solid;
2. the objective's RMS thread is there (a Ø20.32 barrel bites the crests, a Ø19.8
   one turns freely) and the beam bore is clear from the collimator to the objective;
3. the collimator drops in from the back and is stopped by the step at its seat,
   its flange passes the counterbore, and the fork clip - slid in from the side -
   blocks it from coming back out;
4. the cylinder lens seats on the axis through the side slot, the key fills the slot
   behind it, and the lens cannot move along the axis;
5. the two M3 clamp screws pass through the body clear of every bore;
6. for every medium of the layout, the screw positions (from the kinematics) fall
   inside the bracket's arc slots - the manual angle range is really reachable.

Usage:
    uv run --with cadquery python check_opm_launch_holder.py [opm_layout.json]
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
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


lh = load("opm_launch_holder")


def ok(flag: bool) -> str:
    return "OK" if flag else "FAIL"


def clash(a: cq.Shape, b: cq.Shape) -> float:
    """Volume of a ^ b; an empty intersection comes back from OCC as a null shape."""
    try:
        return a.intersect(b).Volume()
    except ValueError as exc:
        if "Null" in str(exc):
            return 0.0
        raise


def cyl_x(r, x0, x1, y=0.0, z=0.0):
    return cq.Solid.makeCylinder(r, x1 - x0, cq.Vector(x0, y, z), cq.Vector(1, 0, 0))


def collimator_solid(p, shift_x=0.0):
    """The Taobao collimator at its seat (body front at col_front), stepped Ø12/Ø14/Ø7.9."""
    t = p.t
    x0 = t["col_front"] + shift_x
    body = cyl_x(p.col_body_d / 2, x0, x0 + (t["col_flange"] - t["col_front"]))
    flange = cyl_x(p.col_flange_d / 2, x0 + (t["col_flange"] - t["col_front"]), x0 + (t["col_nose"] - t["col_front"]))
    nose = cyl_x(p.col_nose_d / 2, x0 + (t["col_nose"] - t["col_front"]), x0 + (t["col_back"] - t["col_front"]))
    return body.fuse(flange).fuse(nose)


def cyl_lens_solid(p, shift=(0.0, 0.0, 0.0)):
    t = p.t
    return cq.Solid.makeBox(p.cyl_ct, p.cyl_h, p.cyl_len,
                            cq.Vector(t["cyl_near"] + shift[0], -p.cyl_h / 2 + shift[1], -p.cyl_len / 2 + shift[2]))


def main() -> None:
    layout_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "openuc2-opmsimulator" / "opm_layout.json"
    layout = json.loads(layout_path.read_text())
    p = lh.plan_from_layout(layout)
    parts = lh.build_all(p)
    results = []

    print("=== solids")
    good = True
    for name, wp in parts.items():
        s = wp.val()
        n = len(wp.solids().vals())
        print(f"  {name:16s} {n} solid, valid={s.isValid()}, volume {s.Volume():.0f} mm^3", ok(n == 1 and s.isValid()))
        good &= n == 1 and s.isValid()
    results.append(good)
    holder = parts["holder"].val()
    t = p.t

    print("=== objective thread and beam bore")
    good = True
    x0, x1 = p.front + p.lead_in + 0.5, p.front + p.thread_len - 0.5
    # thin helical faces confuse OCC's intersect; the material a barrel removes is robust
    v0 = holder.Volume()
    bite = v0 - holder.cut(cyl_x(lh.RMS_MAJOR_MM / 2, x0, x1)).Volume()
    free = v0 - holder.cut(cyl_x(p.crest_r - 0.05, x0, x1)).Volume()
    print(f"  Ø{lh.RMS_MAJOR_MM} barrel bites the crests: {bite:.1f} mm^3", ok(bite > 5.0))
    print(f"  Ø{2 * (p.crest_r - 0.05):.2f} barrel turns freely: {free:.2e} mm^3", ok(free < 1e-6))
    beam = clash(holder, cyl_x(1.0, t["col_front"] - 0.5, p.front - 0.5))
    print(f"  Ø2 beam path collimator -> objective clear: {beam:.2e} mm^3", ok(beam < 1e-6))
    good &= bite > 5.0 and free < 1e-6 and beam < 1e-6
    results.append(good)

    print("=== collimator")
    good = True
    seated = clash(holder, collimator_solid(p))
    pushed = clash(holder, collimator_solid(p, shift_x=-1.0))
    print(f"  seated collimator vs holder: {seated:.2e} mm^3", ok(seated < 1e-6))
    print(f"  pushed 1 mm further in, the step stops it: {pushed:.2f} mm^3", ok(pushed > 1.0))
    # insertion from the back: the flange swept from its seat to the back face
    sweep = cyl_x(p.col_flange_d / 2, t["col_flange"], p.back + 1.0)
    ins = clash(holder, sweep)
    print(f"  flange passes the counterbore from the back: {ins:.2e} mm^3", ok(ins < 1e-6))
    clip = parts["collimator_clip"].val()
    c_clip = clash(holder, clip)
    blocked = clash(clip, collimator_solid(p, shift_x=+1.0))
    print(f"  clip slides in clear of the holder: {c_clip:.2e} mm^3", ok(c_clip < 1e-6))
    print(f"  clip blocks the collimator from backing out: {blocked:.2f} mm^3", ok(blocked > 1.0))
    good &= seated < 1e-6 and pushed > 1.0 and ins < 1e-6 and c_clip < 1e-6 and blocked > 1.0
    results.append(good)

    print("=== cylinder lens")
    good = True
    lens = cyl_lens_solid(p)
    seated = clash(holder, lens)
    axial = clash(holder, cyl_lens_solid(p, (0.5, 0, 0)))
    key = parts["cyl_key"].val()
    c_key = clash(holder, key) + clash(key, lens)
    print(f"  lens seated on the axis: {seated:.2e} mm^3", ok(seated < 1e-6))
    print(f"  lens moved 0.5 mm along the axis is stopped: {axial:.2f} mm^3", ok(axial > 1.0))
    print(f"  key fills the slot clear of holder and lens: {c_key:.2e} mm^3", ok(c_key < 1e-6))
    # the lens centre sits on the axis: the slot bottom is at -cyl_h/2 - fit
    good &= seated < 1e-6 and axial > 1.0 and c_key < 1e-6
    results.append(good)

    print("=== clamp screws")
    good = True
    hw = p.width / 2
    for x, z in p.screws:
        c = clash(holder, cq.Solid.makeCylinder(1.5, p.width + 2, cq.Vector(x, -hw - 1, z), cq.Vector(0, 1, 0)))
        print(f"  M3 at x={x:.0f}, z={z:.0f} passes: {c:.2e} mm^3", ok(c < 1e-6))
        good &= c < 1e-6
    results.append(good)

    print("=== bracket slots vs the kinematics of every medium")
    good = True
    bracket = parts["rail_bracket"].val()
    fb = p.frame_bracket["origin"]
    pl = p.rail["plate"]
    # rebuild the screw positions for each medium from the layout's kinematics
    for cand in (layout_path.parent, HERE.parent / "openuc2-opmsimulator"):
        if (cand / "opm_layout.py").exists() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
    import opm_layout as ol
    cfg = ol._cfg_from(layout["config"])
    L = ol.OpmLayout(cfg)
    for n in cfg.opts.media:
        tr = L.train(n)
        pose = tr["pose"]                      # the launch stage carries the bracket: take its move out
        for hole in tr["foot_holes"]:
            x, z = hole["xz"][0] - fb[0] - pose["x"], hole["xz"][1] - fb[2] - pose["z"]
            probe = cq.Solid.makeCylinder(1.5, p.bracket_thick + 4.0, cq.Vector(x, pl["y"][0] - fb[1] - 2.0, z), cq.Vector(0, 1, 0))
            c = clash(bracket, probe)
            print(f"  n {n:.3f} phi {tr['phi_deg']:.1f}: screw t={hole['t']:.0f} at ({x:+.1f}, {z:.1f}) in its slot: {c:.2e} mm^3", ok(c < 0.1))
            good &= c < 0.1
    results.append(good)

    print(f"{sum(results)}/{len(results)} checks passed")
    sys.stdout.flush()
    os._exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
