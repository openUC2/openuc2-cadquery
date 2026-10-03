"""Adapter into the ½-inch kinematic mount ZJB-0.5-3 — the mount of the kinematic mirror
cube (ASS-2013) and the kinematic splitter (ASS-2077): any round or rectangular optic of any
thickness, at a tilt to the mount axis if needed (a 45° dichroic).

A stub fills the mount's Ø12.8 bore down to its lip, so the mount holds the adapter where it
held a ½-inch optic; on the mount's front a plate (a wedge for a tilted optic) carries the
optic in a pocket, glued or on an adhesive pad. An optic narrower than the bore sits in the
stub itself. ``transmissive`` bores the stub and the plate along the mount axis; ``bores``
adds openings for beams that cross the adapter at an angle.

Frame: the mount's, as the CAD-new part BUY - Kinematic mirror mount - ZJB-0.5-3 has it — the
mount axis is +x through (0, 0), the base plate's back at x = 0. Units mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq


@dataclass(frozen=True)
class KinematicMount:
    """The ZJB-0.5-3 as the CAD-new part models it (measured on the .ipt)."""

    bore_d_mm: float = 12.8       # the moving plate's bore
    lip_x_mm: float = 13.5        # where the bore steps down to the Ø12 opening
    front_x_mm: float = 20.6      # the face an adapter plate rests on
    half_mm: float = 12.0         # half the moving plate's side
    opening_d_mm: float = 12.0    # behind the lip: the light's way through the mount


@dataclass(frozen=True)
class KinematicAdapterParams:
    optic_d_mm: float | None = None               # round optic
    optic_wh_mm: tuple[float, float] | None = None   # rectangular: w along the mount y (tilts), h along z
    optic_t_mm: float = 3.0
    tilt_deg: float = 0.0          # the optic's normal from the mount axis, about the mount's z
    wall_mm: float = 2.0           # behind the optic, at its thinnest
    rim_mm: float = 1.5            # around the pocket
    proud_mm: float = 0.5          # how far the optic stands out of its pocket
    fit_clearance_mm: float = 0.15
    stub_clearance_mm: float = 0.05
    transmissive: bool = False
    bores: tuple = ()              # ({"axis": (x, y, z), "point_mm": (x, y, z), "diameter_mm": d}, ...)
    finger_notch: bool = True
    mount: KinematicMount = field(default_factory=KinematicMount)


@dataclass
class KinematicAdapterPlan:
    params: KinematicAdapterParams
    in_bore: bool = False          # the optic sits in the stub, no plate
    stub_r_mm: float = 0.0
    clear_r_mm: float = 0.0        # the transmissive opening (0 = none)
    optic_centre_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)   # back face centre
    optic_normal: tuple[float, float, float] = (1.0, 0.0, 0.0)
    x_range_mm: tuple[float, float] = (0.0, 0.0)
    radius_mm: float = 0.0         # how far the adapter reaches from the mount axis
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"in_bore": self.in_bore, "stub_d_mm": round(2 * self.stub_r_mm, 3),
                "clear_d_mm": round(2 * self.clear_r_mm, 3),
                "optic_centre_mm": [round(v, 3) for v in self.optic_centre_mm],
                "optic_normal": [round(v, 4) for v in self.optic_normal],
                "x_range_mm": [round(v, 3) for v in self.x_range_mm],
                "radius_mm": round(self.radius_mm, 3), "warnings": self.warnings}


def _outline_half(p: KinematicAdapterParams) -> tuple[float, float]:
    """Half width (y) and half height (z) of the optic."""
    if p.optic_wh_mm is not None:
        return p.optic_wh_mm[0] / 2.0, p.optic_wh_mm[1] / 2.0
    return p.optic_d_mm / 2.0, p.optic_d_mm / 2.0


def plan_kinematic_adapter(p: KinematicAdapterParams) -> KinematicAdapterPlan:
    """Check the optic against the mount; nothing is built."""
    if (p.optic_d_mm is None) == (p.optic_wh_mm is None):
        raise ValueError("give the optic as optic_d_mm (round) or optic_wh_mm (rectangular)")
    if p.optic_t_mm <= 0:
        raise ValueError("optic_t_mm must be > 0")
    if not 0.0 <= abs(p.tilt_deg) <= 60.0:
        raise ValueError(f"tilt {p.tilt_deg}° is past 60°: the wedge would stand out further "
                         "than the cube allows")
    m = p.mount
    plan = KinematicAdapterPlan(params=p)
    plan.stub_r_mm = m.bore_d_mm / 2.0 - p.stub_clearance_mm
    hw, hh = _outline_half(p)
    radius = math.hypot(hw, hh) if p.optic_wh_mm is not None else hw
    if p.optic_d_mm is not None and radius + p.fit_clearance_mm + 0.8 <= plan.stub_r_mm \
            and abs(p.tilt_deg) < 1e-9:
        plan.in_bore = True
        depth = p.optic_t_mm - p.proud_mm
        plan.optic_centre_mm = (m.front_x_mm - depth, 0.0, 0.0)
        if depth > m.front_x_mm - m.lip_x_mm - p.wall_mm:
            raise ValueError(
                f"a {p.optic_t_mm} mm thick optic in the bore leaves less than {p.wall_mm} mm "
                "of stub behind it; it needs a plate in front of the mount (raise proud_mm)")
        plan.x_range_mm = (m.lip_x_mm + 0.1, m.front_x_mm)
        plan.radius_mm = plan.stub_r_mm
    else:
        t = math.radians(p.tilt_deg)
        # The wedge is thinnest at the optic's edge nearest the mount face.
        x0 = m.front_x_mm + p.wall_mm + (hw + p.rim_mm) * abs(math.sin(t))
        plan.optic_centre_mm = (x0, 0.0, 0.0)
        plan.optic_normal = (math.cos(t), math.sin(t), 0.0)
        reach = (hw + p.rim_mm) * abs(math.sin(t)) + (p.optic_t_mm - p.proud_mm) * math.cos(t)
        plan.x_range_mm = (m.lip_x_mm + 0.1, x0 + reach)
        grow = p.rim_mm + p.fit_clearance_mm
        across = (hw + grow) * math.cos(t) + (p.optic_t_mm - p.proud_mm) * abs(math.sin(t))
        if p.optic_wh_mm is not None:
            plan.radius_mm = math.hypot(across, hh + grow)
        else:
            plan.radius_mm = max(across, hw + grow)
        if hw < m.half_mm - p.rim_mm and hh < m.half_mm - p.rim_mm and abs(p.tilt_deg) < 1e-9:
            plan.warnings.append("the optic is smaller than the mount's plate; the plate is cut "
                                 "to the optic's outline")
    if p.transmissive:
        limit = min(m.opening_d_mm / 2.0, plan.stub_r_mm - 0.8)
        aperture = min(hw, hh) - p.rim_mm if not plan.in_bore else radius - 0.5
        plan.clear_r_mm = max(min(limit, aperture), 0.0)
        if plan.clear_r_mm < 1.0:
            raise ValueError("no clear opening left through the stub for a transmissive optic")
    return plan


def _optic_solid(p: KinematicAdapterParams, grow: float, depth: float) -> cq.Solid:
    """The optic's outline grown by *grow*, from its back face (z = 0) to *depth*, local frame."""
    hw, hh = _outline_half(p)
    if p.optic_wh_mm is not None:
        return cq.Solid.makeBox(2 * (hw + grow), 2 * (hh + grow), depth,
                                cq.Vector(-(hw + grow), -(hh + grow), 0.0))
    return cq.Solid.makeCylinder(hw + grow, depth, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))


def _to_mount(shape: cq.Solid, plan: KinematicAdapterPlan) -> cq.Solid:
    """Local optic frame → mount frame: local x (width) → y, y (height) → z, z (normal) → x,
    then the tilt about the mount's z; the back face centre lands on ``optic_centre_mm``."""
    t = math.degrees(math.atan2(plan.optic_normal[1], plan.optic_normal[0]))
    shape = shape.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 1, 1), 120.0)
    if abs(t) > 1e-9:
        shape = shape.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), t)
    return shape.translate(cq.Vector(*plan.optic_centre_mm))


def build_kinematic_adapter(plan: KinematicAdapterPlan) -> cq.Workplane:
    """The printed adapter in the mount frame."""
    p, m = plan.params, plan.params.mount
    stub = cq.Solid.makeCylinder(plan.stub_r_mm, m.front_x_mm - plan.x_range_mm[0],
                                 cq.Vector(plan.x_range_mm[0], 0, 0), cq.Vector(1, 0, 0))
    body = cq.Workplane("XY").add(stub)
    depth = p.optic_t_mm - p.proud_mm
    if not plan.in_bore:
        grow = p.rim_mm + p.fit_clearance_mm
        slab = _to_mount(_optic_solid(p, grow, depth), plan)
        # The rim outline in the optic's back plane, pushed straight back along the mount
        # axis past the mount face: the wedge between face and optic.
        face = _to_mount(_optic_solid(p, grow, 1.0), plan).Faces()
        back_face = min(face, key=lambda f: f.Center().dot(cq.Vector(*plan.optic_normal)))
        reach = plan.optic_centre_mm[0] - m.front_x_mm + 2.0 * (plan.radius_mm + 1.0)
        prism = cq.Solid.extrudeLinear(back_face, cq.Vector(-reach, 0.0, 0.0))
        body = body.union(cq.Workplane("XY").add(slab)).union(cq.Workplane("XY").add(prism))
        behind = cq.Solid.makeBox(80.0, 120.0, 120.0, cq.Vector(m.front_x_mm - 80.0, -60.0, -60.0))
        body = body.cut(cq.Workplane("XY").add(behind)).union(cq.Workplane("XY").add(stub))
    pocket = _optic_solid(p, p.fit_clearance_mm, depth + 5.0)
    body = body.cut(cq.Workplane("XY").add(_to_mount(pocket, plan)))
    if p.optic_wh_mm is not None and not plan.in_bore:
        hw, hh = _outline_half(p)
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                relief = cq.Solid.makeCylinder(0.8, depth + 5.0, cq.Vector(
                    sy * (hw + p.fit_clearance_mm), sz * (hh + p.fit_clearance_mm), 0.0))
                body = body.cut(cq.Workplane("XY").add(_to_mount(relief, plan)))
    if p.finger_notch and not plan.in_bore:
        hw, hh = _outline_half(p)
        notch = cq.Solid.makeBox(8.0, p.rim_mm + p.fit_clearance_mm + 1.0, depth + 5.0,
                                 cq.Vector(-4.0, hh - 0.5, 0.0))
        body = body.cut(cq.Workplane("XY").add(_to_mount(notch, plan)))
    if plan.clear_r_mm:
        hole = cq.Solid.makeCylinder(plan.clear_r_mm, 200.0, cq.Vector(-100.0, 0, 0),
                                     cq.Vector(1, 0, 0))
        body = body.cut(cq.Workplane("XY").add(hole))
    for b in p.bores:
        ax = cq.Vector(*b["axis"]).normalized()
        pt = cq.Vector(*b.get("point_mm", (0.0, 0.0, 0.0)))
        hole = cq.Solid.makeCylinder(b["diameter_mm"] / 2.0, 200.0, pt - ax * 100.0, ax)
        body = body.cut(cq.Workplane("XY").add(hole))
    return body.clean()
