"""dvOPM camera adapter: the printed carrier that holds the Alvium bare board at the sensor tilt
inside an openUC2 cube.

The carrier is captured like every printed round insert: a double base-holder disc
(``round_holder``, the master insert's 82 deg cone and 8 noses on both faces) trapped between a
MASLCK on the outer notch and a MASINS. From the disc a bracket runs below the board and a spine
along its -y side to a 4 mm plate parallel to the sensor; the board's front face lies on the
plate's back, the 12 x 12 sensor package looks through a window, four M2 hold it from behind.
The light comes from the opposite face of the cube, through the window, and never meets the
carrier.

Frame: the camera cube's (origin at its centre, world axes, pins up); every number comes from the
``detection_cubes.camera`` block of ``openuc2-opmsimulator/opm_layout.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cadquery as cq
import numpy as np

try:                                    # works as a package and as a loose script
    from .round_holder import BaseHolderInterface, build_base_holder
except ImportError:                     # pragma: no cover
    from round_holder import BaseHolderInterface, build_base_holder

V = cq.Vector


def _box(x0, x1, y0, y1, z0, z1) -> cq.Solid:
    x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _frame_box(origin, a1, a2, a3, r1, r2, r3) -> cq.Solid:
    """Box with edges along the orthonormal axes a1, a2, a3 (local ranges r1..r3)."""
    o, a1, a2, a3 = V(*origin), V(*a1), V(*a2), V(*a3)
    c = o + a1 * r1[0] + a2 * r2[0] + a3 * r3[0]
    pts = [c, c + a1 * (r1[1] - r1[0]), c + a1 * (r1[1] - r1[0]) + a2 * (r2[1] - r2[0]), c + a2 * (r2[1] - r2[0])]
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(cq.Wire.makePolygon(pts + [pts[0]])), a3 * (r3[1] - r3[0]))


def _prism_xz(pts: Sequence[Sequence[float]], y0: float, y1: float) -> cq.Solid:
    vs = [V(x, y0, z) for x, z in pts]
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(cq.Wire.makePolygon(vs + [vs[0]])), V(0, y1 - y0, 0))


def plan(cam: Dict) -> Dict:
    """The carrier's dimensions from the layout's camera block (camera cube frame)."""
    S, n, X, Y = (np.array(cam[k], float) for k in ("sensor", "normal", "x_axis", "y_axis"))
    side = float(np.sign(cam["sandwich"]["axis"][0]))        # the sandwich sits on this side of the cube
    joint = float(cam["sandwich"]["joint"])
    half = cam["board_half"] + cam["frame_margin"]
    so = cam.get("standoff", 0.0)                                # pads lift the plate off the board's front parts
    w0, w1 = cam["w_face"] + so, cam["w_face"] + so + cam["frame_t"]
    # the plate's edge towards the sandwich (lower, back face) and its far edge (upper, back face)
    ends = [S + v * Y + w0 * n for v in (-half, half)]
    near = min(ends, key=lambda p: side * -p[0])                 # nearest to the sandwich
    far = max(ends, key=lambda p: side * -p[0])
    low_front = S + (half if near is ends[1] else -half) * Y + w1 * n
    x_disc = joint - side * 3.5                                  # bracket and spine start inside the disc
    x_spine = joint - side * 4.45                                # spine clear of the MASINS (face at joint -+ 4.24)
    bz0, bz1 = cam["bracket_z"]
    return {"S": S, "n": n, "X": X, "Y": Y, "side": side, "joint": joint, "half": half, "w": (w0, w1), "w_face": cam["w_face"],
            "near": near, "far": far, "low_front": low_front, "x_disc": x_disc, "x_spine": x_spine,
            "bracket_z": (bz0, bz1), "bracket_r": 18.5, "spine_y": (-(half + 0.8), -(half - 1.2)),
            "window": cam["window"], "holes": cam["holes"], "hole_d": cam["hole_d"]}


def build_carrier(cam: Dict) -> cq.Workplane:
    p = plan(cam)
    S, n, X, Y, side = p["S"], p["n"], p["X"], p["Y"], p["side"]
    # 1. double base-holder disc in the sandwich, axis along x
    seat = BaseHolderInterface(thickness=4.0, interface_mid_z=2.0, skirt=0.0)
    front = build_base_holder(seat).val()
    disc = front.fuse(front.mirror("XY")).rotate(V(0, 0, 0), V(0, 1, 0), 90.0).translate(V(p["joint"], 0, 0))
    # 2. bracket below the board: a circular segment of the cone opening, out to the plate's lower edge
    bz0, bz1 = p["bracket_z"]
    x0, x1 = p["x_disc"], p["low_front"][0] + side * -1.0
    seg = (cq.Workplane("YZ", origin=(min(x0, x1), 0, 0)).circle(p["bracket_r"]).extrude(abs(x1 - x0)).val()
           .intersect(_box(min(x0, x1) - 1, max(x0, x1) + 1, -30, 30, bz0, bz1)))
    # 3. spine along the board's -y side, from beyond the MASINS up to the plate's back face
    xs, near, far = p["x_spine"], p["near"], p["far"]
    spine = _prism_xz([(xs, bz0), (p["low_front"][0], bz0), (near[0], near[2]), (far[0], far[2]),
                       (xs, far[2])], *p["spine_y"])
    # 4. the plate, standing off the board on four pads round the M2 holes; window for the package
    h, w0, w1 = p["half"], *p["w"]
    plate = _frame_box(S, Y, X, n, (-h, h), (-h, h), (w0, w1))
    pads = [cq.Solid.makeCylinder(2.4, w0 - p["w_face"] + 0.01, V(*(S + u * X + v * Y + p["w_face"] * n)), V(*n))
            for u in (-p["holes"], p["holes"]) for v in (-p["holes"], p["holes"])]
    body = disc.fuse(seg, spine, plate, *pads).clean()
    win = p["window"] / 2
    cuts = [_frame_box(S, Y, X, n, (-win, win), (-win, win), (w0 - 1.0, w1 + 1.0))]
    for u in (-p["holes"], p["holes"]):
        for v in (-p["holes"], p["holes"]):
            o = S + u * X + v * Y + (p["w_face"] - 0.5) * n
            cuts.append(cq.Solid.makeCylinder(p["hole_d"] / 2, w1 - p["w_face"] + 1.0, V(*o), V(*n)))
    # the spine must not reach in front of the plate (the light comes from there)
    cuts.append(_frame_box(S, Y, X, n, (-60, 60), (-60, 60), (w1, w1 + 80)))
    solid = body.cut(*cuts).clean()
    out = cq.Workplane("XY").add(solid)
    if len(out.solids().vals()) != 1:
        raise ValueError(f"camera adapter came out as {len(out.solids().vals())} solids")
    return out


def generate(layout_json: str | Path, out_dir: str | Path = "generated/opm_detection", stem: str = "opm_camera_adapter",
             stl: bool = True) -> Dict:
    layout = json.loads(Path(layout_json).read_text())
    cam = layout["detection_cubes"]["camera"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wp = build_carrier(cam)
    files = {"step": str(out / f"{stem}.step")}
    cq.exporters.export(wp, files["step"])
    if stl:
        files["stl"] = str(out / f"{stem}.stl")
        cq.exporters.export(wp, files["stl"], tolerance=0.02, angularTolerance=0.1)
    info = {"frame": cam["frame"], "files": files, "volume_mm3": round(wp.val().Volume(), 1),
            "board_pose_in_cube": layout["detection_cubes"]["poses"]["camera_board_in_cube"],
            "sandwich": cam["sandwich"]}
    (out / f"{stem}_plan.json").write_text(json.dumps(info, indent=2))
    return info


def _cli(argv: Optional[List[str]] = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="uc2cad opm-camera",
                                 description="dvOPM camera adapter: carrier for the Alvium bare board at the sensor tilt, "
                                             "held in a MASLCK/MASINS sandwich of the camera cube, from an opm_layout.json")
    ap.add_argument("layout", help="opm_layout.json written by openuc2-opmsimulator/opm_layout.py")
    ap.add_argument("--out", default="generated/opm_detection", help="output folder")
    ap.add_argument("--stem", default="opm_camera_adapter")
    ap.add_argument("--no-stl", action="store_true")
    a = ap.parse_args(argv)
    info = generate(a.layout, a.out, a.stem, stl=not a.no_stl)
    print(json.dumps({k: info[k] for k in ("files", "volume_mm3")}, indent=2))


if __name__ == "__main__":
    _cli()
