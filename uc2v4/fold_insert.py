"""openUC2 V4 fold-optic insert: a flat plate held at an angle in a 1x1 cube cell.

The holding problem this covers is "a thin flat plate on the beam": a 45 deg
fold mirror, a fluorescence dichroic, a plate beamsplitter, a pellicle, and —
at ``fold_deg = 0`` — a filter or a window standing square across the beam.

Why the SQUARE insert and not the round holder pair: a Ø25 plate turned 45 deg
is 18 mm deep along the beam, and the round master-insert sandwich offers ~8 mm
between its two cone faces. The square insert (MAS-2013 lineage, the same blank
``lens_insert.py`` uses) spans the whole cell, so the plate fits and both the
entry and the exit faces of the cell stay open.

Coordinates: the insert's axis (and the incoming beam) is +Z; ±Y are the spring
sides that ride the cube's plate tracks, so +Y is up once the insert is seated.
The plate's normal is tilted by ``fold_deg`` about +Y, which sends the reflected
beam to −X. The plate slides DOWN into its slot from the +Y face — the slot is
open at the top and closed at the bottom, and that closed end is the seat.

    plate = Plate(thickness_mm=1.05, outline_mm=(35.6, 25.2))   # DMLP505
    front = build_fold_insert(plate)                            # one printed body

The first outline number lies in the TILT plane (x), the second along the slot
(y): a 25.2x35.6 dichroic is ``(35.6, 25.2)``, because the long axis is the one
the 45 deg tilt foreshortens back to 25.2 mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .interface import SquareInsertInterface, base_plate
except ImportError:                     # pragma: no cover
    from interface import SquareInsertInterface, base_plate


@dataclass(frozen=True)
class Plate:
    """A flat optic: round ``diameter_mm``, or rectangular ``outline_mm`` (W, H)."""

    thickness_mm: float
    diameter_mm: float | None = None
    outline_mm: tuple[float, float] | None = None

    @property
    def extents(self) -> tuple[float, float]:
        """(width, height) of the blank in its own plane."""
        if self.outline_mm is not None:
            return float(self.outline_mm[0]), float(self.outline_mm[1])
        if self.diameter_mm is None:
            raise ValueError("a plate needs either diameter_mm or outline_mm")
        return float(self.diameter_mm), float(self.diameter_mm)

    def validate(self) -> None:
        if self.thickness_mm <= 0:
            raise ValueError("plate thickness must be positive")
        if (self.diameter_mm is None) == (self.outline_mm is None):
            raise ValueError("give exactly one of diameter_mm or outline_mm")
        if min(self.extents) <= 0:
            raise ValueError("plate extents must be positive")

    def solid(self, clearance: float = 0.0) -> cq.Solid:
        """The plate centred at the origin, its normal +Z, grown by *clearance*."""
        self.validate()
        t = self.thickness_mm + 2.0 * clearance
        if self.diameter_mm is not None:
            return cq.Solid.makeCylinder(
                self.diameter_mm / 2.0 + clearance, t,
                pnt=cq.Vector(0, 0, -t / 2.0), dir=cq.Vector(0, 0, 1))
        w, h = self.extents
        return cq.Solid.makeBox(
            w + 2.0 * clearance, h + 2.0 * clearance, t,
            pnt=cq.Vector(-(w / 2.0 + clearance), -(h / 2.0 + clearance), -t / 2.0))


@dataclass(frozen=True)
class FoldInsertParams:
    """Everything about the printed insert that is not the plate itself."""

    interface: SquareInsertInterface = field(default_factory=SquareInsertInterface)
    #: None = deep enough for the tilted plate plus a wall each side.
    thickness_mm: float | None = None
    #: Plate normal from the beam. 45 folds to −X; 0 stands the plate square.
    fold_deg: float = 45.0
    fit_clearance_mm: float = 0.2
    #: Clear bore for the beam legs.
    beam_diameter_mm: float = 12.0
    #: Bore the far side too — a dichroic, beamsplitter or filter passes light on.
    transmissive: bool = False
    min_wall_mm: float = 1.2
    #: Material kept around the slot mouth on the ±X sides.
    side_wall_mm: float = 1.5

    def seat(self) -> SquareInsertInterface:
        return self.interface


@dataclass
class FoldPlan:
    plate: Plate
    params: FoldInsertParams
    thickness_mm: float = 0.0
    axial_extent_mm: float = 0.0
    half_x_mm: float = 0.0
    half_y_mm: float = 0.0
    entry_dir: tuple[float, float, float] = (0.0, 0.0, 1.0)
    exit_dir: tuple[float, float, float] | None = None
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {
            "plate": {"thickness_mm": self.plate.thickness_mm,
                      "diameter_mm": self.plate.diameter_mm,
                      "outline_mm": list(self.plate.outline_mm or ())},
            "fold_deg": self.params.fold_deg,
            "insert_thickness_mm": round(self.thickness_mm, 3),
            "plate_axial_extent_mm": round(self.axial_extent_mm, 3),
            "half_extent_mm": [round(self.half_x_mm, 3), round(self.half_y_mm, 3)],
            "entry_dir": [round(v, 6) for v in self.entry_dir],
            "exit_dir": None if self.exit_dir is None else [round(v, 6) for v in self.exit_dir],
            "transmissive": self.params.transmissive,
            "warnings": self.warnings,
        }


def reflected_dir(fold_deg: float) -> tuple[float, float, float]:
    """Where a +Z beam goes off a plate whose normal is tilted *fold_deg* about +Y."""
    a = math.radians(2.0 * fold_deg)
    return (-math.sin(a), 0.0, -math.cos(a))


def _usable_half_x(iface: SquareInsertInterface, y: float) -> float:
    """Outline half-width at height *y* — the octagon's corner flat included."""
    return min(iface.edge_half, max(iface.diag_sum - abs(y), 0.0))


def plan_fold_insert(plate: Plate, params: FoldInsertParams | None = None) -> FoldPlan:
    """Size the insert around the tilted plate, and refuse what will not fit."""
    params = params or FoldInsertParams()
    plate.validate()
    if not 0.0 <= params.fold_deg < 90.0:
        raise ValueError(f"fold_deg {params.fold_deg} must be in [0, 90)")

    iface = params.interface
    c = params.fit_clearance_mm
    w, h = plate.extents
    t = plate.thickness_mm
    theta = math.radians(params.fold_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    # The tilted plate's bounding box: the width foreshortens into x, the
    # thickness stands up into it, and the whole of it has to lie inside the
    # insert with a wall left over.
    half_x = ((w + 2 * c) * cos_t + (t + 2 * c) * sin_t) / 2.0
    half_y = (h + 2 * c) / 2.0
    axial = (w + 2 * c) * sin_t + (t + 2 * c) * cos_t

    plan = FoldPlan(plate=plate, params=params, axial_extent_mm=axial,
                    half_x_mm=half_x, half_y_mm=half_y,
                    exit_dir=None if params.fold_deg == 0.0
                    else reflected_dir(params.fold_deg))

    thickness = params.thickness_mm
    if thickness is None:
        thickness = math.ceil((axial + 2.0 * params.min_wall_mm) * 2.0) / 2.0
    plan.thickness_mm = float(thickness)
    if axial + 2.0 * params.min_wall_mm > thickness + 1e-9:
        raise ValueError(
            f"the plate needs {axial:.2f} mm along the beam (plus {params.min_wall_mm} mm "
            f"of wall each side); the insert is only {thickness:.2f} mm thick — raise "
            "thickness_mm, reduce fold_deg, or take a smaller plate")

    if half_y + params.min_wall_mm > iface.edge_half:
        raise ValueError(
            f"the plate is {2 * half_y:.2f} mm along the slot; the insert outline only "
            f"reaches {2 * iface.edge_half:.2f} mm — the plate does not fit the cell")
    limit = _usable_half_x(iface, half_y) - params.side_wall_mm
    if half_x > limit:
        raise ValueError(
            f"the tilted plate reaches x = ±{half_x:.2f} mm; the outline leaves "
            f"±{limit:.2f} mm at y = ±{half_y:.2f} mm — reduce the plate or the fold")

    beam_r = params.beam_diameter_mm / 2.0
    clear = min(w, h) / 2.0 * (1.0 if params.fold_deg == 0.0 else cos_t)
    if beam_r > clear:
        plan.warnings.append(
            f"the Ø{params.beam_diameter_mm} mm bore is wider than the plate's own "
            f"Ø{2 * clear:.1f} mm projected clear area — the beam will clip the mount")
    return plan


def _slot_cutter(plan: FoldPlan) -> cq.Workplane:
    """The plate cavity, swept up to the +Y face so the plate can be dropped in."""
    p = plan.params
    body = plan.plate.solid(p.fit_clearance_mm)
    if p.fold_deg:
        body = body.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), p.fold_deg)
    travel = p.interface.edge_half + 5.0
    swept = body
    steps = 24
    for i in range(1, steps + 1):
        swept = swept.fuse(body.translate(cq.Vector(0.0, travel * i / steps, 0.0)))
    return cq.Workplane("XY").add(swept.clean())


def _bore(direction: tuple[float, float, float], radius: float, length: float,
          start: float = 0.0) -> cq.Solid:
    """A cylinder from *start* along *direction*, running *length*."""
    v = cq.Vector(*direction).normalized()
    return cq.Solid.makeCylinder(radius, length, pnt=v.multiply(start), dir=v)


def _beam_cutters(plan: FoldPlan) -> list[cq.Solid]:
    """Entry leg, reflected leg, and (transmissive) the far leg."""
    p = plan.params
    r = p.beam_diameter_mm / 2.0
    reach = plan.thickness_mm + p.interface.edge_half + 5.0
    out = [_bore((0, 0, -1), r, reach)]                       # entry, from the plate back
    if plan.exit_dir is not None:
        out.append(_bore(plan.exit_dir, r, reach))            # the fold
    if p.transmissive or plan.exit_dir is None:
        out.append(_bore((0, 0, 1), r, reach))                # straight on through
    return out


def build_fold_insert(plate: Plate, params: FoldInsertParams | None = None,
                      plan: FoldPlan | None = None) -> cq.Workplane:
    """The printed 1x1 insert holding *plate* at ``fold_deg``, in the cube frame."""
    plan = plan or plan_fold_insert(plate, params)
    p = plan.params
    body = base_plate(p.interface, plan.thickness_mm)
    body = body.cut(_slot_cutter(plan))
    for cutter in _beam_cutters(plan):
        body = body.cut(cq.Workplane("XY").add(cutter))
    body = body.clean()
    solids = body.solids().vals()
    if not solids:
        raise ValueError("the insert came out empty — the plate swallows it")
    if len(solids) > 1:
        plan.warnings.append(
            f"the insert is {len(solids)} disconnected pieces; it will not print as one "
            "part. Reduce the beam bore or the plate")
    return body


if __name__ == "__main__":
    import json

    dichroic = Plate(thickness_mm=1.05, outline_mm=(35.6, 25.2))
    plan = plan_fold_insert(dichroic, FoldInsertParams(transmissive=True))
    part = build_fold_insert(dichroic, plan=plan)
    cq.exporters.export(part, "uc2v4_fold_insert.step")
    cq.exporters.export(part, "uc2v4_fold_insert.stl", tolerance=0.02)
    print(json.dumps(plan.report(), indent=2))
