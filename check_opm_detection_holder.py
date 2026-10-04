"""Verification harness for the dvOPM detection holder (uc2v4/opm_detection_holder.py).

Builds the holder and its mirror carrier from an opm_layout.json and asserts, in the BREP
domain, what would bite on the bench:

1. both parts are one valid solid each;
2. the lens barrel stands free in its sleeve, the seat stops it, the clamp screws pass;
3. the image bundle (telecentric cones of NA/M from nine points of the tilted sensor, traced
   back over the mirror to the lens) touches neither part and lands on the mirror;
4. mirror and pad sit in the pocket on the carrier face; the carrier slides out along -y;
5. the board sits on the camera face, the sensor package is free in the window, the four M2
   pilots are there;
6. the base screws, their heads and the hex-key channels are clear; the neighbouring puzzle
   tab has its pocket.

Usage:
    uv run --with cadquery python check_opm_detection_holder.py [opm_layout.json]
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
V = cq.Vector


def load(name: str):
    pkg = HERE / "uc2v4"
    spec = importlib.util.spec_from_file_location(name, pkg / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


dh_mod = load("opm_detection_holder")


def ok(flag: bool) -> str:
    return "OK" if flag else "FAIL"


def clash(a: cq.Shape, b: cq.Shape) -> float:
    try:
        return a.intersect(b).Volume()
    except Exception:                      # disjoint solids: "Null TopoDS_Shape" in cq 2.8
        return 0.0


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def main() -> None:
    lay_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "openuc2-opmsimulator" / "opm_layout.json"
    layout = json.loads(lay_path.read_text())
    dh, det, cfg = layout["detection_holder"], layout["detection"], layout["config"]
    holder = dh_mod.build_holder(dh, layout).val()
    carrier = dh_mod.build_carrier(dh).val()
    results = []

    def rep(text: str, flag: bool) -> None:
        results.append(flag)
        print(f"  {text}", ok(flag))

    print("=== solids")
    for name, s in (("holder", holder), ("mirror carrier", carrier)):
        rep(f"{name:15s} valid={s.isValid()}, volume {s.Volume():.0f} mm^3", s.isValid())

    print("=== lens")
    lens = cfg["lens"]
    zb, zt = det["lens_bottom_z"], det["barrel_top_z"]
    r = lens["barrel_d_mm"] / 2
    barrel = cq.Solid.makeCylinder(r, zt - zb, V(0, 0, zb), V(0, 0, 1))
    c0 = clash(barrel, holder)
    rep(f"Ø{2 * r:.0f} barrel standing on the seat at z {zb:.2f}: {c0:.2e} mm^3", c0 < 1e-3)
    c1 = clash(barrel.translate(V(0, 0, -0.5)), holder)
    rep(f"pushed 0.5 mm down, the seat stops it: {c1:.1f} mm^3", c1 > 10.0)
    cl = dh["clamp"]
    for z in cl["screw_z"]:
        rod = cq.Solid.makeCylinder(1.5, 2 * cl["ear_half_y"] + 4, V(cl["screw_x"], -cl["ear_half_y"] - 2, z), V(0, 1, 0))
        c = clash(rod, holder)
        rep(f"clamp screw M3 at z {z:.1f} passes the ears: {c:.2e} mm^3", c < 1e-3)

    print("=== image bundle")
    cam, mr = cfg["camera"], cfg["mirror"]
    S, Xb, Yb = dh["camera"]["sensor"], dh["camera"]["x_axis"], dh["camera"]["y_axis"]
    M, nm = dh["mirror_centre"], dh["mirror_normal"]
    em = dh["mirror_long_axis"]
    s = dh["side"]
    tan_t = math.tan(math.asin(lens["na"] / lens["magnification"]))
    hits_h, hits_c, off_mirror, n_pts = 0, 0, 0, 0
    worst_edge = 1e9
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            Q = [S[k] + i * cam["sensor_flat_mm"] / 2 * Xb[k] + j * cam["sensor_tilted_mm"] / 2 * Yb[k] for k in range(3)]
            dirs = [[-s, 0.0, 0.0]] + [unit([-s, tan_t * math.cos(a), tan_t * math.sin(a)])
                                       for a in [k * math.pi / 4 for k in range(8)]]
            for d in dirs:
                t = sum((M[k] - Q[k]) * nm[k] for k in range(3)) / sum(d[k] * nm[k] for k in range(3))
                R = [Q[k] + t * d[k] for k in range(3)]
                dn = sum(d[k] * nm[k] for k in range(3))
                d2 = [d[k] - 2 * dn * nm[k] for k in range(3)]
                along = sum((R[k] - M[k]) * em[k] for k in range(3))
                across = R[1] - M[1]
                edge = min(mr["long_mm"] / 2 - abs(along), mr["short_mm"] / 2 - abs(across))
                worst_edge = min(worst_edge, edge)
                off_mirror += edge < 0
                t2 = (zb - 0.3 - R[2]) / d2[2]
                near = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]          # mm in front of the sensor: window and tunnel end
                pts = [[Q[k] + tt * d[k] for k in range(3)] for tt in near + [t * f for f in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 0.97)]]
                pts += [[R[k] + tt * d2[k] for k in range(3)] for tt in [t2 * f for f in (0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0)]]
                for p in pts:
                    n_pts += 1
                    hits_h += holder.isInside(V(*p), 1e-4)
                    hits_c += carrier.isInside(V(*p), 1e-4)
    rep(f"{n_pts} points on 81 rays (9 field points x chief + 8 rim): inside the holder {hits_h}, inside the carrier {hits_c}",
        hits_h == 0 and hits_c == 0)
    rep(f"every ray lands on the mirror, worst margin to its edge {worst_edge:.2f} mm", off_mirror == 0 and worst_edge > 0.5)

    print("=== mirror, pad and carrier")
    # BUY - Mirror - 40x30x2 in its placed frame: 40 along (x+y)/sqrt2, 30 along z, the reflective
    # normal (x-y)/sqrt2, glass and then the 41x29x1 pad behind the face
    pm = dh["poses"]["mirror"]
    a_long = [(pm["x_axis"][k] + pm["y_axis"][k]) / math.sqrt(2) for k in range(3)]
    a_back = [-(pm["x_axis"][k] - pm["y_axis"][k]) / math.sqrt(2) for k in range(3)]
    mirror = dh_mod._frame_box(pm["origin"], a_long, pm["z_axis"], a_back, (-mr["long_mm"] / 2, mr["long_mm"] / 2),
                               (-mr["short_mm"] / 2, mr["short_mm"] / 2), (0.0, mr["t_mm"]))
    pad = dh_mod._frame_box(pm["origin"], a_long, pm["z_axis"], a_back, (-20.5, 20.5), (-14.5, 14.5),
                            (mr["t_mm"], mr["t_mm"] + mr["pad_mm"]))
    cm, cp = clash(mirror, holder), clash(pad, holder)
    rep(f"mirror and pad free in the pocket: {cm:.2e} / {cp:.2e} mm^3", cm < 1e-3 and cp < 1e-3)
    cc = clash(mirror, carrier) + clash(pad, carrier)
    rep(f"mirror + pad vs carrier (pad on the carrier face): {cc:.2e} mm^3", cc < 1e-3)
    nm_ = dh["mirror_normal"]
    pad_in = pad.translate(V(*[-0.2 * c for c in nm_]))
    c_in = clash(pad_in, carrier)
    rep(f"pad pressed 0.2 mm further back meets the carrier face: {c_in:.1f} mm^3", c_in > 1.0)
    worst = 0.0
    for dy in (0, 2, 5, 10, 20, 30, 35):
        worst = max(worst, clash(carrier.translate(V(0, -dy, 0)), holder))
    rep(f"carrier slides out along -y (0..35 mm) without touching the holder: {worst:.2e} mm^3", worst < 1e-3)
    pil = 0.0
    bite = 0.0
    y0 = dh["chamber"]["y"][0]
    for x, z in dh["carrier"]["screws_xz"]:
        pil += clash(cq.Solid.makeCylinder(1.2, 6.5, V(x, y0, z), V(0, 1, 0)), holder)
        bite += clash(cq.Solid.makeCylinder(1.5, 6.5, V(x, y0, z), V(0, 1, 0)), holder)
    rep(f"four M3 pilots for the cover: Ø2.4 pin free {pil:.2e}, Ø3 screw bites {bite:.1f} mm^3", pil < 1e-3 and bite > 1.0)

    print("=== camera board")
    camp = dh["camera"]
    nrm = camp["normal"]
    wf = camp["w_face"]

    def board_box(dw, u0, u1, v0, v1, w0, w1):
        o = [S[k] + dw * nrm[k] for k in range(3)]
        return dh_mod._frame_box(o, Yb, Xb, nrm, (v0, v1), (u0, u1), (w0, w1))

    bh = cam["board_half_mm"]
    board = board_box(0.0, -bh, bh, -bh, bh, -4.75, wf)          # PCB stack behind its front face
    pkg = board_box(0.0, -6.0, 6.0, -6.0, 6.0, wf, 0.9)            # package + glass in front of it
    cb, cpk = clash(board, holder), clash(pkg, holder)
    rep(f"board on the face {cb:.2e} mm^3, sensor package free in the window {cpk:.2e} mm^3", cb < 1e-3 and cpk < 1e-3)
    cpush = clash(board.translate(V(*[0.2 * c for c in nrm])), holder)
    rep(f"board pushed 0.2 mm towards the light meets the face: {cpush:.1f} mm^3", cpush > 5.0)
    h = camp["holes"]
    free = bite = 0.0
    for u in (-h, h):
        for v in (-h, h):
            o = [S[k] + u * Xb[k] + v * Yb[k] + wf * nrm[k] for k in range(3)]
            free += clash(cq.Solid.makeCylinder(0.7, 5.5, V(*o), V(*nrm)), holder)
            bite += clash(cq.Solid.makeCylinder(1.0, 5.5, V(*o), V(*nrm)), holder)
    rep(f"four M2 pilots: Ø1.4 pin free {free:.2e}, Ø2 screw bites {bite:.1f} mm^3", free < 1e-3 and bite > 1.0)

    print("=== base")
    used = [sc for sc in dh["screws"] if sc["use"]]
    worst = 0.0
    for sc in used:
        x, y = sc["xy"]
        shank = cq.Solid.makeCylinder(1.5, 8.0, V(x, y, -3.3), V(0, 0, 1))
        head = cq.Solid.makeCone(1.5, 3.0, 1.5, V(x, y, 3.2), V(0, 0, 1))
        key = cq.Solid.makeCylinder(1.3, 250.0, V(x, y, 6.0), V(0, 0, 1))
        worst = max(worst, clash(shank, holder), clash(head, holder), clash(key, holder))
    rep(f"{len(used)} countersunk M3 (shank, head, hex-key channel) clear: {worst:.2e} mm^3", worst < 1e-3 and len(used) >= 4)
    for tb in dh["tabs"]:
        cx, cy = tb["centre"]
        dx, dy = tb["dir"]
        tab = (cq.Solid.makeBox(5.6, 16.0, 5.0, V(cx, cy - 8, 0)) if dx > 0 else
               cq.Solid.makeBox(16.0, 5.6, 5.0, V(cx - 8, cy - 5.6, 0)))
        c = clash(tab, holder)
        rep(f"puzzle tab from {('-x' if dx else '+y')} at ({cx:.1f}, {cy:.1f}) has its pocket: {c:.2e} mm^3", c < 1e-3)

    print(f"{sum(results)}/{len(results)} checks passed")
    sys.stdout.flush()
    os._exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
