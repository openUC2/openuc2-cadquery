"""Plate for parts off the grid: a printed plate in the puzzle layer over a list of cells, in
place of their puzzle pieces, carrying the parts whose beam leaves the grid directions.

The plate is screwed to the base plate through the puzzle pieces' M3 holes (countersunk; a hole
under a feature is left out), takes the tabs of the neighbouring puzzle pieces in pockets, and
carries features at any position and yaw, each with its optical axis at ``beam_height_mm``:

- ``kinematic`` — a pedestal for the ½-inch kinematic mount ZJB-0.5-3 standing on its -y face,
  with the M3 pilot for the screw that comes through the mount's base;
- ``saddle`` — a half-round seat for a cylinder (a lens tube, a camera lens);
- ``cradle`` — a ``bolt_cradle`` pedestal for a device with a bolt pattern in its base;
- ``lens`` — a wall with a seat for a round lens across the beam.

Each feature is also a docking pose (``mounts``): where the part that fills it sits, in the
plate frame. Frame: the base plate's top at z = 0 (the puzzle layer is z 0 … ``thickness``),
cell (0, 0) centred on the origin, x and y along the cells. Units mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

#: The base plates the puzzle layer sits on: the direction each puzzle piece's tab points and
#: the M3 holes per cell (measured on the CAD-new parts and assemblies ASS-1007 / ASS-1008).
BASES = {
    "5x4": {"tabs": ((1, 0), (0, -1)), "screws": ((22.0, 0.0), (0.0, -22.0))},   # PRT-1043
    "6x4": {"tabs": ((1, 0), (0, 1)), "screws": ((22.0, 0.0), (0.0, 22.0))},     # PRT-1050
}
#: The ZJB-0.5-3 as CAD-new models it: its axis 12.6 mm above the -y face it stands on, the
#: base plate x 0 … 10 along the axis, the M3 hole through that face at x = 5.
ZJB = {"axis_above_face": 12.6, "base_x": (0.0, 10.0), "half": 12.6, "screw_x": 5.0}
TAB_POCKET = (6.4, 18.0)          # depth into the cell, width along the edge
M3 = (3.4, 6.6, 2.5)              # clearance Ø, countersink Ø, thread-forming pilot Ø


@dataclass(frozen=True)
class Feature:
    kind: str                     # kinematic | saddle | cradle | lens
    name: str
    at_mm: tuple[float, float]    # where on the plate (the feature's origin)
    yaw_deg: float = 0.0          # the feature's +u (its beam direction) from the plate's +x
    beam_height_mm: float = 30.0  # optical axis above the base plate's top (cube centres: 30)
    d_mm: float = 25.0            # saddle / lens: the part's diameter
    length_mm: float = 20.0       # saddle: along the beam; lens: the lens thickness
    cradle: dict = field(default_factory=dict)   # cradle: bolt_cradle parameters


@dataclass(frozen=True)
class OffGridPlateParams:
    cells: tuple[tuple[int, int], ...]
    pitch_mm: float = 50.0
    base: str = "5x4"
    bounds: tuple[int, int, int, int] | None = None   # base plate cells (c0, r0, c1, r1)
    thickness_mm: float = 5.0
    features: tuple[Feature, ...] = ()
    clearance_mm: float = 0.15


@dataclass
class OffGridPlatePlan:
    params: OffGridPlateParams
    tab_pockets: list[dict] = field(default_factory=list)
    screws: list[tuple[float, float]] = field(default_factory=list)
    skipped_screws: list[tuple[float, float]] = field(default_factory=list)
    footprints: dict = field(default_factory=dict)   # feature name -> its corners on the plate
    mounts: dict = field(default_factory=dict)       # feature name -> docking pose (record spelling)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"cells": [list(c) for c in self.params.cells],
                "tab_pockets": self.tab_pockets,
                "screws": [[round(x, 3), round(y, 3)] for x, y in self.screws],
                "skipped_screws": [[round(x, 3), round(y, 3)] for x, y in self.skipped_screws],
                "mounts": self.mounts, "warnings": self.warnings}


def _uv(f: Feature, u: float, v: float) -> tuple[float, float]:
    a = math.radians(f.yaw_deg)
    return (f.at_mm[0] + u * math.cos(a) - v * math.sin(a),
            f.at_mm[1] + u * math.sin(a) + v * math.cos(a))


def _extent(f: Feature, p: OffGridPlateParams) -> tuple[float, float, float, float]:
    """(u0, u1, v0, v1) of a feature's base in its own frame."""
    if f.kind == "kinematic":
        return ZJB["base_x"][0] - 2.0, ZJB["base_x"][1] + 2.0, -ZJB["half"] - 2.0, ZJB["half"] + 2.0
    if f.kind == "saddle":
        w = f.d_mm / 2.0 + 3.0
        return -f.length_mm / 2.0, f.length_mm / 2.0, -w, w
    if f.kind == "lens":
        t = f.length_mm / 2.0 + 2.5
        w = f.d_mm / 2.0 + 3.0
        return -t, t, -w, w
    holes = f.cradle.get("holes_mm", [[0.0, 0.0]])
    m = float(f.cradle.get("margin_mm", 3.0)) + 3.0
    au, av = f.cradle.get("axis_uv_mm", (0.0, 0.0))
    us = [h[0] - au for h in holes]
    vs = [h[1] - av for h in holes]
    return min(us) - m, max(us) + m, min(vs) - m, max(vs) + m


def _grid_rotation(yaw: float) -> dict:
    """The record's rotation for a part whose +x runs along the feature's beam, +y up.

    The grid takes the nearest quarter turn; the rest of the yaw is a turn about the
    part's own +y, which points up. ``offset-deg`` turns about the part's local axes,
    and its local z lies flat (x × up): a residual about z tilted the part out of the
    plate instead of turning it (0.7.0)."""
    q = round(yaw / 90.0) % 4
    x_axis = ("+x", "+y", "-x", "-y")[q]
    z_axis = ("-y", "+x", "+y", "-x")[q]          # x × up
    rot = {"kind": "grid", "grid": {"z": z_axis, "x": x_axis}}
    residual = yaw - 90.0 * round(yaw / 90.0)
    if abs(residual) > 1e-9:
        rot["offset-deg"] = {"y": round(residual, 6)}
    return rot


def plan_off_grid_plate(p: OffGridPlateParams) -> OffGridPlatePlan:
    """Check cells, features and screws; nothing is built."""
    if not p.cells:
        raise ValueError("no cells: give the cells the plate takes over")
    if p.base not in BASES:
        raise ValueError(f"base must be one of {', '.join(BASES)}, got {p.base!r}")
    cells = {tuple(c) for c in p.cells}
    if len(cells) != len(p.cells):
        raise ValueError("a cell is listed twice")
    plan = OffGridPlatePlan(params=p)
    pitch, base = p.pitch_mm, BASES[p.base]

    def on_base(c: tuple[int, int]) -> bool:
        if p.bounds is None:
            return True
        c0, r0, c1, r1 = p.bounds
        return c0 <= c[0] <= c1 and r0 <= c[1] <= r1

    for c, r in sorted(cells):
        if not on_base((c, r)):
            raise ValueError(f"cell ({c}, {r}) is off the base plate {p.bounds}")
        for d in base["tabs"]:
            nb = (c - d[0], r - d[1])
            if nb not in cells and on_base(nb):
                plan.tab_pockets.append({"cell": [c, r], "from": list(nb), "dir": list(d),
                                         "centre": [c * pitch - d[0] * pitch / 2,
                                                    r * pitch - d[1] * pitch / 2]})

    def in_cells(x: float, y: float) -> bool:
        return (round(x / pitch), round(y / pitch)) in cells and \
            abs(x - round(x / pitch) * pitch) <= pitch / 2 + 1e-6 and \
            abs(y - round(y / pitch) * pitch) <= pitch / 2 + 1e-6

    names = set()
    for f in p.features:
        if f.kind not in ("kinematic", "saddle", "cradle", "lens"):
            raise ValueError(f"feature {f.name!r}: kind must be kinematic, saddle, cradle or lens")
        if f.name in names:
            raise ValueError(f"two features are called {f.name!r}")
        names.add(f.name)
        u0, u1, v0, v1 = _extent(f, p)
        corners = [_uv(f, u, v) for u in (u0, u1) for v in (v0, v1)]
        outside = [c for c in corners if not in_cells(*c)]
        if outside:
            raise ValueError(f"feature {f.name!r} reaches ({outside[0][0]:.1f}, "
                             f"{outside[0][1]:.1f}) mm, off the plate's cells")
        plan.footprints[f.name] = corners
        low = {"kinematic": ZJB["axis_above_face"], "saddle": f.d_mm / 2.0 + 1.0,
               "lens": f.d_mm / 2.0 + 2.0, "cradle": 0.0}[f.kind]
        if f.beam_height_mm - p.thickness_mm < low:
            raise ValueError(f"feature {f.name!r}: a beam {f.beam_height_mm} mm above the base "
                             f"plate leaves {f.beam_height_mm - p.thickness_mm:.1f} mm over the "
                             f"plate; it needs {low:.1f}")
        x, y = f.at_mm
        plan.mounts[f.name] = {
            "pose": {"translation": {"offset-mm": {"x": round(x, 4), "y": round(y, 4),
                                                   "z": round(f.beam_height_mm, 4)}},
                     "rotation": _grid_rotation(f.yaw_deg)},
            "accepts": {"kinematic": "openuc2.mount.zjb-0.5-3",
                        "saddle": f"cylinder-d{f.d_mm:g}", "lens": f"lens-d{f.d_mm:g}",
                        "cradle": f"cradle-{f.name}"}[f.kind],
        }

    def under(x: float, y: float) -> bool:
        for f in p.features:
            u0, u1, v0, v1 = _extent(f, p)
            a = math.radians(f.yaw_deg)
            dx, dy = x - f.at_mm[0], y - f.at_mm[1]
            u = dx * math.cos(a) + dy * math.sin(a)
            v = -dx * math.sin(a) + dy * math.cos(a)
            if u0 - M3[1] / 2 <= u <= u1 + M3[1] / 2 and v0 - M3[1] / 2 <= v <= v1 + M3[1] / 2:
                return True
        return False

    for c, r in sorted(cells):
        for sx, sy in base["screws"]:
            pt = (c * pitch + sx, r * pitch + sy)
            (plan.skipped_screws if under(*pt) else plan.screws).append(pt)
    if not plan.screws:
        raise ValueError("every screw hole of the plate is under a feature: nothing holds it "
                         "to the base plate")
    if plan.skipped_screws:
        plan.warnings.append(f"{len(plan.skipped_screws)} screw holes are under features and "
                             "left out")
    return plan


def _box(u0: float, u1: float, v0: float, v1: float, z0: float, z1: float) -> cq.Solid:
    return cq.Solid.makeBox(u1 - u0, v1 - v0, z1 - z0, cq.Vector(u0, v0, z0))


def _place(shape: cq.Solid | cq.Workplane, f: Feature) -> cq.Workplane:
    w = shape if isinstance(shape, cq.Workplane) else cq.Workplane("XY").add(shape)
    if abs(f.yaw_deg) > 1e-9:
        w = w.rotate((0, 0, 0), (0, 0, 1), f.yaw_deg)
    return w.translate((f.at_mm[0], f.at_mm[1], 0.0))


def _feature(f: Feature, p: OffGridPlateParams) -> cq.Workplane:
    """One feature in the plate frame, standing on the plate's top."""
    top, c = p.thickness_mm, p.clearance_mm
    u0, u1, v0, v1 = _extent(f, p)
    h = f.beam_height_mm
    if f.kind == "kinematic":
        face = h - ZJB["axis_above_face"]
        body = cq.Workplane("XY").add(_box(u0, u1, v0, v1, top - 0.01, face))
        pilot = cq.Solid.makeCylinder(M3[2] / 2.0, 9.0, cq.Vector(ZJB["screw_x"], 0.0, face - 8.9))
        return _place(body.cut(cq.Workplane("XY").add(pilot)), f)
    if f.kind == "saddle":
        r = f.d_mm / 2.0
        body = cq.Workplane("XY").add(_box(u0, u1, v0, v1, top - 0.01, h))
        seat = cq.Solid.makeCylinder(r + c, u1 - u0 + 2.0, cq.Vector(u0 - 1.0, 0.0, h),
                                     cq.Vector(1, 0, 0))
        return _place(body.cut(cq.Workplane("XY").add(seat)), f)
    if f.kind == "lens":
        r = f.d_mm / 2.0
        t = f.length_mm
        wall = cq.Workplane("XY").add(_box(u0, u1, v0, v1, top - 0.01, h + r + 3.0))
        seat = cq.Solid.makeCylinder(r + c, t / 2.0 + c + 10.0, cq.Vector(-t / 2.0 - c, 0.0, h),
                                     cq.Vector(1, 0, 0))
        clear = cq.Solid.makeCylinder(r - 1.2, u1 - u0 + 2.0, cq.Vector(u0 - 1.0, 0.0, h),
                                      cq.Vector(1, 0, 0))
        wall = wall.cut(cq.Workplane("XY").add(seat)).cut(cq.Workplane("XY").add(clear))
        return _place(wall, f)
    from .bolt_cradle import BoltCradleParams, build_bolt_cradle, plan_bolt_cradle

    spec = dict(f.cradle)
    spec["holes_mm"] = tuple(tuple(hh) for hh in spec["holes_mm"])
    spec["axis_uv_mm"] = tuple(spec.get("axis_uv_mm", (0.0, 0.0)))
    cradle = BoltCradleParams(form="pedestal", beam_height_mm=h - top + 0.01, **spec)
    body = build_bolt_cradle(plan_bolt_cradle(cradle)).translate((0, 0, top - 0.01))
    return _place(body, f)


def build_off_grid_plate(plan: OffGridPlatePlan) -> cq.Workplane:
    """The printed plate with its features, in the plate frame."""
    p = plan.params
    pitch, t = p.pitch_mm, p.thickness_mm
    plate = None
    for c, r in p.cells:
        cell = cq.Workplane("XY").add(_box(c * pitch - pitch / 2, c * pitch + pitch / 2,
                                           r * pitch - pitch / 2, r * pitch + pitch / 2, 0.0, t))
        plate = cell if plate is None else plate.union(cell)
    for f in p.features:
        plate = plate.union(_feature(f, p))
    depth, width = TAB_POCKET
    for tab in plan.tab_pockets:
        cx, cy = tab["centre"]
        dx, dy = tab["dir"]
        if dx:
            u0, u1 = (cx - 0.1, cx + depth) if dx > 0 else (cx - depth, cx + 0.1)
            pocket = _box(u0, u1, cy - width / 2, cy + width / 2, -0.1, t + 0.1)
        else:
            v0, v1 = (cy - 0.1, cy + depth) if dy > 0 else (cy - depth, cy + 0.1)
            pocket = _box(cx - width / 2, cx + width / 2, v0, v1, -0.1, t + 0.1)
        plate = plate.cut(cq.Workplane("XY").add(pocket))
    for sx, sy in plan.screws:
        hole = cq.Solid.makeCylinder(M3[0] / 2, t + 0.2, cq.Vector(sx, sy, -0.1))
        cone = cq.Solid.makeCone(M3[0] / 2, M3[1] / 2, (M3[1] - M3[0]) / 2,
                                 cq.Vector(sx, sy, t - (M3[1] - M3[0]) / 2))
        head = cq.Solid.makeCylinder(M3[1] / 2, 60.0, cq.Vector(sx, sy, t))
        plate = plate.cut(cq.Workplane("XY").add(hole)).cut(cq.Workplane("XY").add(cone)) \
            .cut(cq.Workplane("XY").add(head))
    return plate.clean()
