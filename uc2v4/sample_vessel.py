"""Vial and cuvette inserts with a light-tight cap.

A thick square insert across the beam with a well for the vessel — round for a vial, square
for a cuvette (12.5 mm outside is the standard) — standing upright, open to the top. The floor
sets where the beam crosses the vessel (``beam_height_mm`` above its bottom); windows open the
walls on the beam axis (``-z``, ``+z``) and, for 90° collection, across it (``-x``, ``+x``). The
cap is a cup over the vessel's top, outside the cube, whose skirt plugs into a groove around the
well so no light gets in along the vessel.

Frame: the insert frame of the V4 inserts (beam = z, the mid-plane at z = 0 before the notch
shift; +y becomes the cube's up when seated). Units mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

from .interface import SquareInsertInterface, base_plate

NOTCHES = (-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0)
WINDOWS = {"-z": (0, 0, -1), "+z": (0, 0, 1), "-x": (-1, 0, 0), "+x": (1, 0, 0)}


@dataclass(frozen=True)
class SampleVesselParams:
    vessel: str = "cuvette"          # cuvette | vial
    size_mm: float = 12.5            # cuvette: outside side; vial: outside Ø
    length_mm: float = 45.0
    beam_height_mm: float = 15.0     # the beam above the vessel's bottom
    windows: tuple[str, ...] = ("-z", "+z")
    window_mm: float = 8.0
    wall_mm: float = 2.0
    clearance_mm: float = 0.2
    cap: bool = True
    cap_wall_mm: float = 1.6
    groove_mm: float = 3.0           # depth of the cap's skirt in the insert's top
    z_mm: float = 0.0                # along the beam (nearest notch)


@dataclass
class SampleVesselPlan:
    params: SampleVesselParams
    thickness_mm: float = 0.0        # along the beam
    floor_y_mm: float = 0.0          # the vessel's bottom (insert frame y; the beam is at 0)
    top_y_mm: float = 0.0            # the vessel's top
    notch_mm: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"vessel": self.params.vessel, "thickness_mm": round(self.thickness_mm, 3),
                "floor_y_mm": round(self.floor_y_mm, 3), "top_y_mm": round(self.top_y_mm, 3),
                "notch_mm": self.notch_mm, "warnings": self.warnings}


def plan_sample_vessel(p: SampleVesselParams,
                       iface: SquareInsertInterface | None = None) -> SampleVesselPlan:
    """Check the vessel against the insert and the cube's ports; nothing is built."""
    iface = iface or SquareInsertInterface()
    if p.vessel not in ("cuvette", "vial"):
        raise ValueError(f"vessel must be cuvette or vial, got {p.vessel!r}")
    bad = [w for w in p.windows if w not in WINDOWS]
    if bad:
        raise ValueError(f"windows must be among {', '.join(WINDOWS)}, got {bad}")
    outer = p.size_mm + 2 * p.clearance_mm
    if p.cap and outer + 2 * p.cap_wall_mm > 33.0:
        raise ValueError(f"a {p.size_mm} mm {p.vessel} with its cap does not pass the cube's "
                         "34 mm top port")
    plan = SampleVesselPlan(params=p)
    plan.thickness_mm = outer + 2 * p.wall_mm
    if plan.thickness_mm > 34.0:
        raise ValueError(f"the insert would be {plan.thickness_mm:.1f} mm thick along the beam; "
                         "it has to stay within the 34 mm inner cube")
    plan.floor_y_mm = -p.beam_height_mm
    plan.top_y_mm = plan.floor_y_mm + p.length_mm
    if plan.floor_y_mm - 2.0 < -iface.edge_half:
        raise ValueError(f"a beam {p.beam_height_mm} mm above the vessel's bottom puts the floor "
                         "under the insert: lower beam_height_mm")
    if p.window_mm / 2 > min(p.beam_height_mm, p.size_mm / 2):
        raise ValueError(f"a Ø{p.window_mm} mm window does not fit the vessel's wall at the beam")
    if plan.top_y_mm < iface.edge_half and p.cap:
        plan.warnings.append("the vessel ends inside the insert; the cap sits on the top")
    notch = min(NOTCHES, key=lambda n: abs(n - p.z_mm))
    if abs(notch - p.z_mm) > 2.5 + 1e-9:
        raise ValueError(f"z = {p.z_mm} mm is past the outer notch (±15 mm)")
    if notch - plan.thickness_mm / 2 < -17.0 or notch + plan.thickness_mm / 2 > 17.0:
        raise ValueError(f"on the notch at {notch:g} mm the {plan.thickness_mm:.1f} mm insert "
                         "reaches past ±17 mm: move it towards the centre")
    plan.notch_mm = notch
    return plan


def _well(p: SampleVesselParams, grow: float, y0: float, y1: float) -> cq.Solid:
    s = p.size_mm / 2 + grow
    if p.vessel == "vial":
        return cq.Solid.makeCylinder(s, y1 - y0, cq.Vector(0, y0, 0), cq.Vector(0, 1, 0))
    return cq.Solid.makeBox(2 * s, y1 - y0, 2 * s, cq.Vector(-s, y0, -s))


def build_sample_vessel(plan: SampleVesselPlan) -> tuple[cq.Workplane, cq.Workplane | None]:
    """(insert, cap) in the insert frame; the cap is None when not asked for."""
    p = plan.params
    iface = SquareInsertInterface()
    top = iface.edge_half
    c = p.clearance_mm
    body = base_plate(iface, plan.thickness_mm)
    body = body.cut(cq.Workplane("XY").add(_well(p, c, plan.floor_y_mm, top + 1.0)))
    for w in p.windows:
        d = cq.Vector(*WINDOWS[w])
        body = body.cut(cq.Workplane("XY").add(
            cq.Solid.makeCylinder(p.window_mm / 2, 30.0, cq.Vector(0, 0, 0), d)))
    cap = None
    if p.cap:
        skirt_in = c + 0.1
        skirt_out = skirt_in + p.cap_wall_mm
        groove = _well(p, skirt_out + 0.2, top - p.groove_mm, top + 1.0)
        body = body.cut(cq.Workplane("XY").add(groove))
        y0 = top - p.groove_mm + 0.2
        y1 = max(plan.top_y_mm, top) + 1.0 + p.cap_wall_mm
        cup = cq.Workplane("XY").add(_well(p, skirt_out, y0, y1))
        cap = cup.cut(cq.Workplane("XY").add(_well(p, skirt_in, y0 - 1.0, y1 - p.cap_wall_mm)))
        cap = cap.clean()
    return body.clean(), cap
