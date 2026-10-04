"""dvOPM sample holder (dish ring on the sample stage) and a 35 mm dish, from opm_layout.json.

The sample XYZ stage stands on its cube tower beside the detection lens; this printed part
bolts to its slide (four holes, 25 mm pattern) and carries a C-shaped ring around the dish.
When the dish sits above the slide top (the low stack of opm_layout: dish bottom = slide
top + arm thickness) the part is one flat, short plate - mount, arm and ring in one slab,
the stiffest form; when the dish sits below the slide, a web drops beside the slide to the
arm. The dish rests on the ring's 2 mm ledge, located by a low rim; the ring is open towards
+x (the launch side) so the objective nose can come up under the dish.

Frame: origin at the sample stage's slide-top centre, world axes (see opm_layout).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import cadquery as cq


@dataclass
class SampleHolderPlan:
    dish_local: tuple                 # dish centre (x, y) and bottom z, in the holder frame
    dish_d: float
    dish_h: float
    ring_w: float
    ring_t: float
    ledge: float = 2.0
    rim_h: float = 2.0
    rim_t: float = 1.5
    opening_deg: float = 120.0        # towards +x
    mount: float = 40.0
    mount_t: float = 4.0
    hole_pitch: float = 25.0
    hole_d: float = 4.5
    arm_w: float = 20.0
    flat_arm_w: float = 32.0          # the slab between mount and ring when the dish is above the slide
    glass_t: float = 0.17
    frame: Optional[Dict] = None

    def report(self) -> Dict:
        return {"frame": "origin at the sample stage slide-top centre, world axes",
                "dish_centre_bottom_local": list(self.dish_local), "ring": {"outer_d": self.dish_d + 2 * self.ring_w,
                "inner_d": self.dish_d - 2 * self.ledge, "thickness": self.ring_t, "opening_deg_towards_+x": self.opening_deg},
                "mount": {"size": self.mount, "hole_pitch": self.hole_pitch, "hole_d": self.hole_d}, "frame_world": self.frame}


def plan_from_layout(layout: Dict) -> SampleHolderPlan:
    ss, dish, o = layout["sample_stage"], layout["dish"], layout["config"]["opts"]
    cx, cy = ss["centre_xy"]
    local = (dish["centre_xy"][0] - cx, dish["centre_xy"][1] - cy, dish["bottom_z"] - ss["slide_top_z"])
    return SampleHolderPlan(dish_local=local, dish_d=dish["d_mm"], dish_h=dish["h_mm"],
                            ring_w=o["dish_ring_w_mm"], ring_t=o["ring_thick_mm"], glass_t=dish["glass_mm"],
                            frame={"origin": [cx, cy, ss["slide_top_z"]], "x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "z_axis": [0, 0, 1]})


def _box(x0, x1, y0, y1, z0, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def build_sample_holder(p: SampleHolderPlan) -> cq.Workplane:
    dx, dy, dz = p.dish_local                  # dish centre and bottom face
    z_ring0, z_ring1 = dz - p.ring_t, dz
    ro, ri = p.dish_d / 2 + p.ring_w, p.dish_d / 2 - p.ledge
    m = p.mount / 2
    y_ring_edge = dy + ro                       # the ring's +y extreme (dish is at -y)
    ring = cq.Solid.makeCylinder(ro, p.ring_t, cq.Vector(dx, dy, z_ring0), cq.Vector(0, 0, 1))
    rim = cq.Solid.makeCylinder(p.dish_d / 2 + 0.25 + p.rim_t, p.rim_h, cq.Vector(dx, dy, z_ring1), cq.Vector(0, 0, 1))
    flat = dz >= p.mount_t - 1e-6
    if flat:
        # dish above the slide: mount and arm are one slab as thick as the dish height
        mount = _box(-m, m, -m, m, 0.0, dz)
        arm = _box(-p.flat_arm_w / 2, p.flat_arm_w / 2, y_ring_edge - 4.0, -m + 0.01, 0.0, dz)
        pieces = (mount, arm, ring, rim)
    else:
        # dish below the slide: mount plate on the slide, web down beside the slide, arm to the ring
        y_web0 = -m - 6.0
        mount = _box(-m, m, -m, m, 0.0, p.mount_t)
        web = _box(-p.arm_w / 2, p.arm_w / 2, y_web0, -m + 0.01, z_ring0, p.mount_t)
        arm = _box(-p.arm_w / 2, p.arm_w / 2, y_ring_edge - 2.0, y_web0 + 0.01, z_ring0, z_ring1)
        pieces = (mount, web, arm, ring, rim)
    part = cq.Workplane("XY").add(pieces[0])
    for pc in pieces[1:]:
        part = part.union(cq.Workplane("XY").add(pc))
    tools = [cq.Solid.makeCylinder(ri, p.ring_t + p.rim_h + 2, cq.Vector(dx, dy, z_ring0 - 1), cq.Vector(0, 0, 1)),
             cq.Solid.makeCylinder(p.dish_d / 2 + 0.25, p.rim_h + 1, cq.Vector(dx, dy, z_ring1), cq.Vector(0, 0, 1))]
    # opening towards +x: a wedge of `opening_deg` (through the whole slab when the arm is flat)
    a = math.radians(p.opening_deg / 2)
    L = ro + 5.0
    z_cut = -1.0 if flat else z_ring0 - 1
    wedge = (cq.Workplane("XY", origin=(0, 0, z_cut)).moveTo(dx, dy)
             .lineTo(dx + L * math.cos(a), dy - L * math.sin(a)).lineTo(dx + L, dy - L * math.sin(a))
             .lineTo(dx + L, dy + L * math.sin(a)).lineTo(dx + L * math.cos(a), dy + L * math.sin(a)).close()
             .extrude(z_ring1 + p.rim_h + 1 - z_cut))
    tools.append(wedge.val())
    ph = p.hole_pitch / 2
    for sx in (-ph, ph):
        for sy in (-ph, ph):
            tools.append(cq.Solid.makeCylinder(p.hole_d / 2, max(p.mount_t, dz) + 2, cq.Vector(sx, sy, -1), cq.Vector(0, 0, 1)))
    solid = part.val().cut(*tools).clean()
    out = cq.Workplane("XY").add(solid)
    if len(out.solids().vals()) != 1:
        raise ValueError(f"sample holder came out as {len(out.solids().vals())} solids")
    return out


def build_dish(p: SampleHolderPlan) -> cq.Workplane:
    """A 35 mm glass-bottom dish, simplified: 0.17 mm bottom, 1 mm wall. Frame: its own
    centre on the bottom face."""
    r = p.dish_d / 2
    bottom = cq.Solid.makeCylinder(r, p.glass_t, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))
    wall = cq.Solid.makeCylinder(r, p.dish_h, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1)).cut(
        cq.Solid.makeCylinder(r - 1.0, p.dish_h + 1, cq.Vector(0, 0, p.glass_t), cq.Vector(0, 0, 1)))
    return cq.Workplane("XY").add(bottom.fuse(wall).clean())


def generate(layout_json: str | Path, out_dir: str | Path = "generated/opm_launch", stem: str = "opm_launch",
             stl: bool = True) -> SampleHolderPlan:
    layout = json.loads(Path(layout_json).read_text())
    p = plan_from_layout(layout)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, wp in (("sample_holder", build_sample_holder(p)), ("dish", build_dish(p))):
        path = out / f"{stem}_{name}.step"
        cq.exporters.export(wp, str(path))
        files[name + "_step"] = str(path)
        if stl:
            path = out / f"{stem}_{name}.stl"
            cq.exporters.export(wp, str(path), tolerance=0.02, angularTolerance=0.1)
            files[name + "_stl"] = str(path)
    rep = p.report()
    rep["files"] = files
    (out / f"{stem}_sample_holder_plan.json").write_text(json.dumps(rep, indent=2))
    return p


def _cli(argv: Optional[list] = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="uc2cad opm-sample", description="dvOPM sample arm (dish ring on the sample "
                                 "stage's slide) and a 35 mm dish, from an opm_layout.json")
    ap.add_argument("layout", help="opm_layout.json written by openuc2-opmsimulator/opm_layout.py")
    ap.add_argument("--out", default="generated/opm_launch", help="output folder")
    ap.add_argument("--stem", default="opm_launch")
    a = ap.parse_args(argv)
    print(json.dumps(generate(a.layout, a.out, a.stem).report(), indent=2))


if __name__ == "__main__":
    import sys

    _cli(sys.argv[1:2] + (["--out", sys.argv[2]] if len(sys.argv) > 2 else []))
