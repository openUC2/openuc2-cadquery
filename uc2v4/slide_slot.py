"""Slide-slot insert: a square insert across the beam with a slot for a microscope slide
(76 x 26 x 1.0 mm by default), a stop at one end, a thumb cut-out at the other, a clear aperture
on the beam axis and, if asked, a pocket for a coverslip (22 x 22 x 0.17).

The slide lies in the insert's mid-plane, so the sample plane is the insert's notch position.
It goes in through the top face (``slide_axis: vertical``, resting on the stop below) or a side
face (``horizontal``) — the cube's 34 mm ports pass its 26 mm width — and runs on through the
opposite face unless the stop holds it: ``stop_mm`` is how far the stop's face is from the cube
centre, on the side opposite the entry. A slide is longer than a cube, so its middle is not on
the axis when it rests on a stop inside the cell.

Frame: the insert frame of the V4 inserts (beam = z, the mid-plane at z = 0 before the notch
shift; +y becomes the cube's up when seated); the slide runs along y (vertical) or x. Units mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

from .interface import SquareInsertInterface, base_plate

NOTCHES = (-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0)


@dataclass(frozen=True)
class SlideSlotParams:
    slide_mm: tuple[float, float, float] = (76.0, 26.0, 1.0)   # length, width, thickness
    slide_axis: str = "vertical"     # in through the top face, or "horizontal" (a side face)
    clearance_mm: float = 0.15
    wall_mm: float = 2.0             # in front of and behind the slide
    stop_mm: float | None = 23.0     # the stop's face from the centre (None: no stop)
    clear_aperture_mm: float = 20.0
    coverslip_mm: float | None = None   # a square coverslip pocket on the +z face
    coverslip_t_mm: float = 0.17
    z_mm: float = 0.0                # along the beam (nearest notch)


@dataclass
class SlideSlotPlan:
    params: SlideSlotParams
    thickness_mm: float = 0.0
    notch_mm: float = 0.0
    slide_centre_mm: float = 0.0     # along the slide axis, where the slide's middle ends up
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"thickness_mm": round(self.thickness_mm, 3), "notch_mm": self.notch_mm,
                "slide_centre_mm": round(self.slide_centre_mm, 3),
                "slide_axis": self.params.slide_axis, "warnings": self.warnings}


def plan_slide_slot(p: SlideSlotParams, iface: SquareInsertInterface | None = None) -> SlideSlotPlan:
    """Check the slide against the insert and the cube's ports; nothing is built."""
    iface = iface or SquareInsertInterface()
    length, width, thick = p.slide_mm
    if p.slide_axis not in ("vertical", "horizontal"):
        raise ValueError(f"slide_axis must be vertical or horizontal, got {p.slide_axis!r}")
    if width + 2 * p.clearance_mm > 33.0:
        raise ValueError(f"a {width} mm wide slide does not pass the cube's 34 mm port")
    if width / 2 + p.clearance_mm + 2.0 > iface.edge_half:
        raise ValueError("the slot would cut the insert in two: the slide is too wide")
    plan = SlideSlotPlan(params=p)
    plan.thickness_mm = thick + 2 * p.clearance_mm + 2 * p.wall_mm
    notch = min(NOTCHES, key=lambda n: abs(n - p.z_mm))
    if abs(notch - p.z_mm) > 2.5 + 1e-9:
        raise ValueError(f"z = {p.z_mm} mm is past the outer notch (±15 mm): move the slide to "
                         "a neighbouring cube")
    plan.notch_mm = notch
    if abs(notch - p.z_mm) > 1e-9:
        plan.warnings.append(f"the insert sits on the notch at {notch:g} mm")
    if p.stop_mm is not None:
        if not p.clear_aperture_mm / 2 + 2.0 < p.stop_mm <= iface.edge_half - 1.0:
            raise ValueError(f"the stop at {p.stop_mm} mm must lie past the clear aperture and "
                             f"inside the insert (≤ {iface.edge_half - 1.0:.1f} mm)")
        plan.slide_centre_mm = length / 2.0 - p.stop_mm      # the slide rests on the stop
    if p.coverslip_mm is not None and p.coverslip_mm / 2 + 0.3 > iface.shoulder_half:
        raise ValueError(f"a {p.coverslip_mm} mm coverslip does not fit the insert's face")
    if p.clear_aperture_mm >= width:
        raise ValueError(f"a {p.clear_aperture_mm} mm aperture is wider than the slide")
    return plan


def build_slide_slot(plan: SlideSlotPlan) -> cq.Workplane:
    """The printed insert in the insert frame (mid-plane at z = 0)."""
    p = plan.params
    length, width, thick = p.slide_mm
    c = p.clearance_mm
    body = base_plate(SquareInsertInterface(), plan.thickness_mm)
    w, t = width + 2 * c, thick + 2 * c
    near = -(p.stop_mm if p.stop_mm is not None else 60.0)   # the stop, opposite the entry
    if p.slide_axis == "vertical":
        slot = cq.Workplane("XY").add(cq.Solid.makeBox(w, 60.0 - near, t,
                                                       cq.Vector(-w / 2, near, -t / 2)))
        thumb = cq.Solid.makeCylinder(8.0, 40.0, cq.Vector(0.0, 24.7, -20.0))
    else:
        slot = cq.Workplane("XY").add(cq.Solid.makeBox(60.0 - near, w, t,
                                                       cq.Vector(near, -w / 2, -t / 2)))
        thumb = cq.Solid.makeCylinder(8.0, 40.0, cq.Vector(24.7, 0.0, -20.0))
    body = body.cut(slot).cut(cq.Workplane("XY").add(thumb))
    body = body.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
        p.clear_aperture_mm / 2, 40.0, cq.Vector(0, 0, -20.0))))
    if p.coverslip_mm is not None:
        s = p.coverslip_mm + 0.3
        depth = p.coverslip_t_mm + 0.05
        body = body.cut(cq.Workplane("XY").add(cq.Solid.makeBox(
            s, s, depth + 1.0, cq.Vector(-s / 2, -s / 2, plan.thickness_mm / 2 - depth))))
    return body.clean()
