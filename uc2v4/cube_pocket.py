"""Cube pocket: a beamsplitter cube (12.7, 20 or 25.4 mm, or any edge up to 28 mm) held at the
centre of an openUC2 cell, with a bore through each of its four side faces.

The printed body is the beamsplitter clamshell's (``beamsplitter_insert``): one tall square
insert split at z = 0 into a lower and an upper half with alignment pins. The pocket straddles
the split, so the cube drops into the lower half and the upper one closes over it. Each bore
is ``lip_mm`` narrower than the face on every side: that frame of wall is the retaining lip
that keeps the cube from sliding out of a port.

Frame: the cube frame — x and y the beam axes, z the pin axis; the beamsplitter cube's faces
along ±x, ±y, ±z. Units mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

from .beamsplitter_insert import BeamsplitterParams, BeamsplitterPlan, _half_blanks, _pin

PORTS = {"+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0), "+y": (0.0, 1.0, 0.0),
         "-y": (0.0, -1.0, 0.0)}


@dataclass(frozen=True)
class CubePocketParams:
    cube_mm: float = 25.4
    lip_mm: float = 1.0               # the frame of wall around each bore
    fit_clearance_mm: float = 0.15
    thickness_mm: float = 34.0        # the clamshell: 34 fills the inner cube
    ports: tuple[str, ...] = ("+x", "-x", "+y", "-y")
    pin_style: str = "dowel"


@dataclass
class CubePocketPlan:
    params: CubePocketParams
    bore_r_mm: float = 0.0
    floor_mm: float = 0.0             # wall under and over the cube
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"cube_mm": self.params.cube_mm, "bore_d_mm": round(2 * self.bore_r_mm, 3),
                "floor_mm": round(self.floor_mm, 3), "ports": list(self.params.ports),
                "warnings": self.warnings}


def plan_cube_pocket(p: CubePocketParams) -> CubePocketPlan:
    """Check the cube against the clamshell; nothing is built."""
    if not 3.0 <= p.cube_mm <= 28.0:
        raise ValueError(f"a {p.cube_mm} mm cube: the pocket holds cubes from 3 to 28 mm "
                         "(the clamshell's walls and pins need the rest of the cell)")
    bad = [q for q in p.ports if q not in PORTS]
    if bad:
        raise ValueError(f"ports must be among {', '.join(PORTS)}, got {bad}")
    if not p.cube_mm + 2 * p.fit_clearance_mm + 2.0 <= p.thickness_mm <= 34.0:
        raise ValueError(f"thickness {p.thickness_mm} mm: it must hold the cube with 1 mm "
                         "of wall above and below, and stay within the 34 mm inner cube")
    plan = CubePocketPlan(params=p)
    plan.bore_r_mm = p.cube_mm / 2.0 - p.lip_mm
    if plan.bore_r_mm < 1.0:
        raise ValueError(f"a {p.lip_mm} mm lip leaves no bore on a {p.cube_mm} mm cube")
    plan.floor_mm = (p.thickness_mm - p.cube_mm) / 2.0 - p.fit_clearance_mm
    return plan


def build_cube_pocket(plan: CubePocketPlan) -> tuple[cq.Workplane, cq.Workplane]:
    """The (lower, upper) halves in the cube frame."""
    p = plan.params
    shell = BeamsplitterPlan(params=BeamsplitterParams(pin_style=p.pin_style),
                             thickness_mm=p.thickness_mm)
    lower, upper = _half_blanks(shell)
    s = p.cube_mm + 2 * p.fit_clearance_mm
    pocket = cq.Workplane("XY").box(s, s, s)
    cutters = [pocket]
    for q in p.ports:
        v = cq.Vector(*PORTS[q])
        cutters.append(cq.Workplane("XY").add(
            cq.Solid.makeCylinder(plan.bore_r_mm, 40.0, cq.Vector(0, 0, 0), v)))
    for c in cutters:
        lower, upper = lower.cut(c), upper.cut(c)
    return _pin(lower.clean(), upper.clean(), shell)
