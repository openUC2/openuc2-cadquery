# uc2_insert_builder.py
# Update: remove the corner "ears"/flexures.
# Instead, optional side tabs are placed at the CENTER of each flat side (+X,-X,+Y,-Y),
# which matches the "no corner springs" look.
#
# Optical axis is Z through (0,0). Insert thickness is centered around Z=0.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

import cadquery as cq


# ----------------------------
# Explicit parameters
# ----------------------------

OUT_STEP_PATH = "uc2_insert.step"
OUT_STL_PATH  = "uc2_insert.stl"

# Outline from your drawing (interpreting as half-dimensions)
OUTER_HALF    = 24.70   # mm -> 49.40 overall
SHOULDER_HALF = 16.95   # mm -> 33.90 overall flat-to-flat on the inner square region

INSERT_THICKNESS = 6.0  # mm

# Robust edge rounding (applied only to base outline)
OUTER_EDGE_FILLET = 1  # set 0.0 to disable

# Central through hole (example, can also be done via external cutter STEP)
ADD_CENTER_BORE = True
CENTER_BORE_DIAMETER = 25.2  # mm

OPTICALAXIS_BORE_DIAMETER = 10.0  # mm

# Thread holes (red dots)
ADD_THREAD_HOLES = True
THREAD_TAP_DIAMETER = 2.8   # mm (tap drill for M2.5); change as needed
THREAD_HOLE_EDGE_INSET = 2.5 # mm inset from the shoulder corner
THREAD_HOLE_Z_EXTRA = 1.0    # mm

# Side tabs (replace your previous corner wings)
ADD_SIDE_TABS = True
TAB_OUTSET = 3.96             # mm protruding beyond outer flat
TAB_WIDTH  = 33.9             # mm along the side
TAB_FILLET = 0.4             # mm, optional

# External cutters (STEP solids) to subtract
# Each entry: (path, affine transform)
@dataclass
class Affine:
    tx: float = 0.0
    ty: float = 0.0
    tz: float = 0.0
    rx: float = 0.0  # deg about X
    ry: float = 0.0  # deg about Y
    rz: float = 0.0  # deg about Z

CUTTERS: List[Tuple[str, Optional[Affine]]] = [
    # ("component_cut.step", Affine(tx=0, ty=0, tz=0, rx=0, ry=0, rz=0)),
]

# STL quality
STL_LINEAR_TOL      = 0.05
STL_ANGULAR_TOL_DEG = 5.0


# ----------------------------
# Robust helpers
# ----------------------------



def safe_fillet(wp: cq.Workplane, radius: float, selector: str = "|Z", attempts: int = 8) -> cq.Workplane:
    if not radius or radius <= 0:
        return wp
    r = float(radius)
    for _ in range(attempts):
        try:
            sel = wp.edges(selector)
            if len(sel.vals()) == 0:
                return wp
            return sel.fillet(r)
        except Exception:
            r *= 0.65
    return wp

def safe_chamfer(wp: cq.Workplane, size: float, selector: str = "|Z") -> cq.Workplane:
    if not size or size <= 0:
        return wp
    try:
        sel = wp.edges(selector)
        if len(sel.vals()) == 0:
            return wp
        return sel.chamfer(float(size))
    except Exception:
        return wp


# ----------------------------
# Geometry
# ----------------------------

def octagon_points(outer_half: float, shoulder_half: float) -> List[Tuple[float, float]]:
    oh = float(outer_half)
    sh = float(shoulder_half)
    return [
        ( oh, -sh),
        ( oh,  sh),
        ( sh,  oh),
        (-sh,  oh),
        (-oh,  sh),
        (-oh, -sh),
        (-sh, -oh),
        ( sh, -oh),
    ]

def build_base_outline() -> cq.Workplane:
    pts = octagon_points(OUTER_HALF, SHOULDER_HALF)
    base = cq.Workplane("XY").polyline(pts).close().extrude(INSERT_THICKNESS, both=True).clean()
    # Fillet only the base, before unions/cuts
    if OUTER_EDGE_FILLET and OUTER_EDGE_FILLET > 0:
        # base = safe_fillet(base, OUTER_EDGE_FILLET, selector="|Z", attempts=8)
        base = safe_chamfer(base, OUTER_EDGE_FILLET, selector="|Z")
    return base

def cutout_optical_axis(model: cq.Workplane) -> cq.Workplane:
    r_bore = float(OPTICALAXIS_BORE_DIAMETER / 2.0)
    solid = cq.Workplane("XY").circle(r_bore).extrude(INSERT_THICKNESS+2, both=True)
    return model.cut(solid)

def add_center_bore(model: cq.Workplane) -> cq.Workplane:
    if not ADD_CENTER_BORE:
        return model
    d = float(CENTER_BORE_DIAMETER)
    h = INSERT_THICKNESS + 2.0
    bore = cq.Workplane("XY").circle(d / 2.0).extrude(h, both=True)
    return model.cut(bore)

def subtract_external_cutters(model: cq.Workplane) -> cq.Workplane:
    if not CUTTERS:
        return model
    cutters_wp = cq.Workplane("XY")
    for (path, aff) in CUTTERS:
        solid = load_step_as_solid(path)
        solid = apply_affine(solid, aff)
        cutters_wp = cutters_wp.add(solid)
    return model.cut(cutters_wp)

def build_side_tabs() -> cq.Workplane:
    # Tabs centered on each side (+X, -X, +Y, -Y). No corner tabs.
    tabs = cq.Workplane("XY")
    t = INSERT_THICKNESS
    o = float(TAB_OUTSET)
    w = float(TAB_WIDTH)

    # +Y
    tabs = tabs.union(
        cq.Workplane("XY")
        .center(0, OUTER_HALF + o / 2.0)
        .rect(w, o)
        .extrude(t, both=True)
    )
    # -Y
    tabs = tabs.union(
        cq.Workplane("XY")
        .center(0, -OUTER_HALF - o / 2.0)
        .rect(w, o)
        .extrude(t, both=True)
    )
    # +X
    tabs = tabs.union(
        cq.Workplane("XY")
        .center(OUTER_HALF + o / 2.0, 0)
        .rect(o, w)
        .extrude(t, both=True)
    )
    # -X
    tabs = tabs.union(
        cq.Workplane("XY")
        .center(-OUTER_HALF - o / 2.0, 0)
        .rect(o, w)
        .extrude(t, both=True)
    )

    tabs = tabs.clean()

    if TAB_FILLET and TAB_FILLET > 0:
        tabs = safe_fillet(tabs, TAB_FILLET, selector="|Z", attempts=6)

    return tabs



def add_thread_holes(model: cq.Workplane) -> cq.Workplane:
    if not ADD_THREAD_HOLES:
        return model

    d = float(THREAD_TAP_DIAMETER)
    h = INSERT_THICKNESS + float(THREAD_HOLE_Z_EXTRA)

    # Place at corners of the inner square region with inset
    p = float(SHOULDER_HALF) - float(THREAD_HOLE_EDGE_INSET)
    pts = [(+p, +p), (-p, +p), (-p, -p), (+p, -p)]

    cutters = cq.Workplane("XY")
    for (x, y) in pts:
        cutters = cutters.union(
            cq.Workplane("XY").center(x, y).circle(d / 2.0).extrude(h, both=True)
        )

    return model.cut(cutters)

def load_step_as_solid(path: str) -> cq.Solid:
    wp = cq.importers.importStep(path)
    solids = wp.solids().vals()
    if solids:
        fused = solids[0]
        for s in solids[1:]:
            fused = fused.fuse(s)
        return fused
    v = wp.val()
    if hasattr(v, "Solids") and len(v.Solids()) > 0:
        ss = v.Solids()
        fused = ss[0]
        for s in ss[1:]:
            fused = fused.fuse(s)
        return fused
    return v

def apply_affine(s: cq.Solid, a: Optional[Affine]) -> cq.Solid:
    if a is None:
        return s
    s2 = s.rotate((0, 0, 0), (1, 0, 0), float(a.rx))
    s2 = s2.rotate((0, 0, 0), (0, 1, 0), float(a.ry))
    s2 = s2.rotate((0, 0, 0), (0, 0, 1), float(a.rz))
    s2 = s2.translate((float(a.tx), float(a.ty), float(a.tz)))
    return s2


def export(model: cq.Workplane) -> None:
    cq.exporters.export(model, OUT_STEP_PATH)
    cq.exporters.export(
        model,
        OUT_STL_PATH,
        tolerance=STL_LINEAR_TOL,
        angularTolerance=math.radians(max(0.1, STL_ANGULAR_TOL_DEG)),
    )

def build_insert() -> cq.Workplane:
    m = build_base_outline()

    if ADD_SIDE_TABS:
        m = m.union(build_side_tabs())

    m = add_thread_holes(m)
    #m = add_center_bore(m)
    m = cutout_optical_axis(m)
    #m = subtract_external_cutters(m)

    return m.clean()


if __name__ == "__main__":
    insert = build_insert()
    export(insert)
