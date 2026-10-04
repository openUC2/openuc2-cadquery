"""dvOPM detection holder: one printed body for the reversed telecentric lens, the 45 deg fold
mirror and the Alvium board at the sensor tilt, plus the slide-in mirror carrier.

SUPERSEDED (2026-10-03): the dvOPM now keeps its detection in cubes (turned CAD-new modules and
``opm_camera_adapter``); this monolithic version needs a layout with a ``detection_holder``
block, which ``opm_layout.py`` no longer writes. Kept for comparison only, not in the CLI.

The body stands on the 5x4 plate in the puzzle layer of three cells (pockets for the
neighbouring puzzle tabs, countersunk M3 on the PRT-1043 holes a hex key can reach). The lens
stands on a seat and is pinched by a split sleeve; below it a pocket takes the carrier with
the BUY 40x30x2 mirror on its 41x29x1 adhesive pad (inserted from -y, its cover closes the
pocket); a lofted tunnel, sized to the image bundle, leads to a face at the sensor tilt on
which the bare board is screwed (four M2, sensor package through a window).

Frame: the world of ``openuc2-opmsimulator/opm_layout.py`` (z = 0 on the plate's top face,
detection axis = z axis); every number comes from its ``detection_holder`` block.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cadquery as cq

V = cq.Vector


def _box(x0, x1, y0, y1, z0, z1) -> cq.Solid:
    x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _cyl(r: float, base, direction, length: float) -> cq.Solid:
    return cq.Solid.makeCylinder(r, length, V(*base), V(*direction))


def _poly(pts: Sequence[Sequence[float]]) -> cq.Wire:
    vs = [V(*p) for p in pts]
    return cq.Wire.makePolygon(vs + [vs[0]])


def _prism(pts: Sequence[Sequence[float]], vec) -> cq.Solid:
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(_poly(pts)), V(*vec))


def _frame_box(origin, a1, a2, a3, r1, r2, r3) -> cq.Solid:
    """Box with its edges along the orthonormal right-handed axes a1, a2, a3 (local ranges r1..r3)."""
    o, a1, a2, a3 = V(*origin), V(*a1), V(*a2), V(*a3)
    corner = o + a1 * r1[0] + a2 * r2[0] + a3 * r3[0]
    pts = [corner, corner + a1 * (r1[1] - r1[0]), corner + a1 * (r1[1] - r1[0]) + a2 * (r2[1] - r2[0]),
           corner + a2 * (r2[1] - r2[0])]
    face = cq.Face.makeFromWires(cq.Wire.makePolygon(pts + [pts[0]]))
    return cq.Solid.extrudeLinear(face, a3 * (r3[1] - r3[0]))


def _rect(x: float, mz: float, hy: float, hz: float) -> cq.Wire:
    return _poly([(x, -hy, mz - hz), (x, hy, mz - hz), (x, hy, mz + hz), (x, -hy, mz + hz)])


def _fuse(solids: List[cq.Solid]) -> cq.Shape:
    out = solids[0]
    if len(solids) > 1:
        out = out.fuse(*solids[1:], glue=False)
    return out.clean()


def build_holder(dh: Dict, layout: Dict) -> cq.Workplane:
    det = layout["detection"]
    s, mz = dh["side"], det["mirror_centre"][2]
    base, pocket, ch, sl, cl = dh["base"], dh["pocket"], dh["chamber"], dh["sleeve"], dh["clamp"]
    cam, tun = dh["camera"], dh["tunnel"]
    P, bt = base["pitch"], base["z"][1]
    lens_bottom = det["lens_bottom_z"]
    # ---- material
    parts = [_box(P * c - P / 2, P * c + P / 2, P * r - P / 2, P * r + P / 2, 0.0, bt) for c, r in base["cells"]]
    parts += [_box(*st["x"], *st["y"], 0.0, bt) for st in base["strips"]]
    parts.append(_box(*ch["x"], *ch["y"], 0.0, lens_bottom))
    parts.append(_cyl(sl["r_out"], (0, 0, sl["z"][0]), (0, 0, 1), sl["z"][1] - sl["z"][0]))
    parts.append(_box(*cl["ear_x"], -cl["ear_half_y"], cl["ear_half_y"], *cl["z"]))
    S = cam["sensor"]
    nrm, Xb, Yb = cam["normal"], cam["x_axis"], cam["y_axis"]
    behind = _frame_box(S, Yb, Xb, nrm, (-300, 300), (-300, 300), (-400, cam["w_face"]))
    tb, cb = tun["box"], cam["block"]
    blocks = _box(*tb["x"], *tb["y"], *tb["z"]).fuse(_box(*cb["x"], *cb["y"], *cb["z"])).cut(behind)
    parts.append(blocks)
    body = _fuse(parts)
    # ---- light path, lens and mirror
    cuts = [_box(pocket["x"][0], pocket["x"][1], ch["y"][0] - 1.0, pocket["y"][1], *pocket["z"]),
            _cyl(sl["seat_r"], (0, 0, pocket["z"][1] - 0.5), (0, 0, 1), lens_bottom - pocket["z"][1] + 0.51),
            _cyl(sl["r_bore"], (0, 0, lens_bottom), (0, 0, 1), sl["z"][1] - lens_bottom + 1.0)]
    A, B = tun["sections"]
    loft = cq.Solid.makeLoft([_rect(A["x"], mz, A["hy"], A["hz"]), _rect(B["x"], mz, B["hy"], B["hz"])], True)
    end = _box(B["x"], S[0] + s * 4.0, -B["hy"], B["hy"], mz - B["hz"], mz + B["hz"])     # on past the sensor
    inner = _frame_box(S, Yb, Xb, nrm, (-300, 300), (-300, 300), (-400, cam["w_inner"]))
    cuts.append(loft.fuse(end).cut(inner))
    h = cam["window"] / 2
    cuts.append(_frame_box(S, Yb, Xb, nrm, (-h, h), (-h, h), (cam["w_face"] - 0.5, cam["w_inner"] + 0.5)))
    for u in (-cam["holes"], cam["holes"]):
        for v in (-cam["holes"], cam["holes"]):
            p0 = [S[i] + u * Xb[i] + v * Yb[i] + (cam["w_face"] - 0.3) * nrm[i] for i in range(3)]
            cuts.append(_cyl(cam["hole_d"] / 2, p0, nrm, cam["hole_depth"] + 0.3))
    # ---- clamp: slit, two M3 screws across it, nut traps on +y
    x_in, x_out = s * (sl["r_bore"] - 1.0), s * (sl["r_out"] + 10.0)
    cuts.append(_box(x_in, x_out, -cl["slit"] / 2, cl["slit"] / 2, cl["slit_z0"], sl["z"][1] + 1.0))
    hy = cl["ear_half_y"]
    for z in cl["screw_z"]:
        cuts.append(_cyl(cl["screw_d"] / 2, (cl["screw_x"], -hy - 1.0, z), (0, 1, 0), 2 * hy + 2.0))
        rr = cl["nut_af"] / 2 / math.cos(math.radians(30))
        hexa = [(cl["screw_x"] + rr * math.cos(math.radians(60 * k)), hy - cl["nut_depth"], z + rr * math.sin(math.radians(60 * k)))
                for k in range(6)]
        cuts.append(_prism(hexa, (0, cl["nut_depth"] + 0.5, 0)))
    # ---- base: tab pockets, countersunk M3 where a key reaches the head
    for tb_ in dh["tabs"]:
        cx, cy = tb_["centre"]
        dx, dy = tb_["dir"]
        if dx:
            cuts.append(_box(cx - 0.1 if dx > 0 else cx - 6.4, cx + 6.4 if dx > 0 else cx + 0.1, cy - 9.0, cy + 9.0, -0.1, bt + 0.1))
        else:
            cuts.append(_box(cx - 9.0, cx + 9.0, cy - 0.1 if dy > 0 else cy - 6.4, cy + 6.4 if dy > 0 else cy + 0.1, -0.1, bt + 0.1))
    z_head = bt - 0.3
    for sc in dh["screws"]:
        if not sc["use"]:
            continue
        x, y = sc["xy"]
        cuts.append(_cyl(1.7, (x, y, -0.1), (0, 0, 1), bt + 0.2))
        cuts.append(cq.Solid.makeCone(1.7, 3.35, 1.65, V(x, y, z_head - 1.65), V(0, 0, 1)))
        cuts.append(_cyl(3.4, (x, y, z_head), (0, 0, 1), 4.3))                   # head pocket
        cuts.append(_cyl(1.6, (x, y, z_head + 4.0), (0, 0, 1), 400.0))         # hex key channel
    # ---- M3 pilots for the carrier's cover
    for x, z in dh["carrier"]["screws_xz"]:
        cuts.append(_cyl(1.25, (x, ch["y"][0] - 0.1, z), (0, 1, 0), 7.1))
    solid = body.cut(*cuts).clean()
    out = cq.Workplane("XY").add(solid)
    n = len(out.solids().vals())
    if n != 1:
        raise ValueError(f"detection holder came out as {n} solids")
    return out


def build_carrier(dh: Dict) -> cq.Workplane:
    """The wedge that carries the mirror (pad face at the pocket's 45 deg diagonal) and the
    cover that closes the pocket on -y; four M3 through the cover."""
    c = dh["carrier"]
    y0, y1 = c["y"]
    wedge = _prism([(x, y0, z) for x, z in c["section_xz"]], (0, y1 - y0, 0))
    cover = _box(*c["cover_x"], *c["cover_y"], *c["cover_z"])
    holes = [_cyl(1.7, (x, c["cover_y"][0] - 0.1, z), (0, 1, 0), c["cover_y"][1] - c["cover_y"][0] + 0.2) for x, z in c["screws_xz"]]
    solid = wedge.fuse(cover).cut(*holes).clean()
    out = cq.Workplane("XY").add(solid)
    if len(out.solids().vals()) != 1:
        raise ValueError("mirror carrier came out as more than one solid")
    return out


def generate(layout_json: str | Path, out_dir: str | Path = "generated/opm_detection", stem: str = "opm_detection",
             stl: bool = True) -> Dict:
    layout = json.loads(Path(layout_json).read_text())
    dh = layout["detection_holder"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files, volumes = {}, {}
    for name, wp in (("holder", build_holder(dh, layout)), ("mirror_carrier", build_carrier(dh))):
        path = out / f"{stem}_{name}.step"
        cq.exporters.export(wp, str(path))
        files[name + "_step"] = str(path)
        volumes[name] = round(wp.val().Volume(), 1)
        if stl:
            path = out / f"{stem}_{name}.stl"
            cq.exporters.export(wp, str(path), tolerance=0.02, angularTolerance=0.1)
            files[name + "_stl"] = str(path)
    plan = {"frame": "world (opm_layout): both parts are placed with the identity at the world origin",
            "files": files, "volumes_mm3": volumes, "poses": dh["poses"],
            "screws_used": [sc["xy"] for sc in dh["screws"] if sc["use"]],
            "lens_seat_z": layout["detection"]["lens_bottom_z"], "mirror_centre": dh["mirror_centre"],
            "sensor_centre": dh["camera"]["sensor"], "sleeve_top_z": dh["sleeve"]["z"][1]}
    (out / f"{stem}_plan.json").write_text(json.dumps(plan, indent=2))
    return plan


def _cli(argv: Optional[List[str]] = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="uc2cad opm-detection",
                                 description="dvOPM detection holder (lens seat + clamp, 45 deg mirror pocket, image "
                                             "tunnel, 50 deg camera face) and its mirror carrier, from an opm_layout.json")
    ap.add_argument("layout", help="opm_layout.json written by openuc2-opmsimulator/opm_layout.py")
    ap.add_argument("--out", default="generated/opm_detection", help="output folder")
    ap.add_argument("--stem", default="opm_detection")
    ap.add_argument("--no-stl", action="store_true")
    a = ap.parse_args(argv)
    plan = generate(a.layout, a.out, a.stem, stl=not a.no_stl)
    print(json.dumps({k: plan[k] for k in ("files", "volumes_mm3", "screws_used", "lens_seat_z", "sensor_centre")}, indent=2))


if __name__ == "__main__":
    _cli()
