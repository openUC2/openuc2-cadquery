"""A single-piece filter cube on the fold insert: dichroic slot + two filter pockets.

The clamshell (``beamsplitter_insert``) is the validated design; this is the
one-piece alternative — the fold insert holding the dichroic at ``fold_deg``,
an excitation pocket square across the entry leg (the −Z face) and an
emission pocket square across the reflected leg (the −X face), the insert
deepened to hold them. Kept for a print without pins; not measured against
a reference part.

Insert frame: the beam arrives along +Z, the plate at the origin is tilted
about +Y, the fold leaves along −X at 45°, the far bore continues +Z.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

from .fold_insert import FoldInsertParams, FoldPlan, Plate, build_fold_insert, plan_fold_insert


@dataclass(frozen=True)
class RoundFilter:
    diameter_mm: float
    thickness_mm: float


@dataclass(frozen=True)
class FilterCubeParams:
    dichroic: Plate
    excitation: RoundFilter | None = None
    emission: RoundFilter | None = None
    fold_deg: float = 45.0
    beam_diameter_mm: float = 12.0
    fit_clearance_mm: float = 0.2
    #: Material kept between a pocket and the slot / the outside.
    pocket_wall_mm: float = 1.2
    #: Minimum insert depth along the beam; the pockets and the plate may need more.
    thickness_mm: float | None = None


def plan_filter_cube(params: FilterCubeParams) -> FoldPlan:
    """Size the fold insert so the plate AND the pockets fit."""
    if params.emission and abs(params.fold_deg - 45.0) > 1e-6:
        raise ValueError("an emission pocket sits on the fold face, which needs fold_deg 45")
    base = FoldInsertParams(fold_deg=params.fold_deg, fit_clearance_mm=params.fit_clearance_mm,
                            beam_diameter_mm=params.beam_diameter_mm, transmissive=True)
    plan = plan_fold_insert(params.dichroic, base)
    c, wall = params.fit_clearance_mm, params.pocket_wall_mm
    thickness = plan.thickness_mm
    if params.excitation:
        thickness = max(thickness, plan.axial_extent_mm + 2 * wall + params.excitation.thickness_mm)
    if params.emission:
        thickness = max(thickness, params.emission.diameter_mm + 2 * c + 2 * wall)
    if params.thickness_mm is not None:
        thickness = max(thickness, params.thickness_mm)
    thickness = math.ceil(thickness * 2.0) / 2.0
    return plan_fold_insert(params.dichroic, FoldInsertParams(
        thickness_mm=thickness, fold_deg=params.fold_deg, fit_clearance_mm=c,
        beam_diameter_mm=params.beam_diameter_mm, transmissive=True))


def build_filter_cube(params: FilterCubeParams, plan: FoldPlan | None = None) -> cq.Workplane:
    """The one-piece insert, in the fold insert's own frame."""
    plan = plan or plan_filter_cube(params)
    c = params.fit_clearance_mm
    body = build_fold_insert(params.dichroic, plan=plan)
    if params.excitation:
        f = params.excitation
        body = body.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
            f.diameter_mm / 2.0 + c, f.thickness_mm + c + 1.0,
            pnt=cq.Vector(0, 0, -plan.thickness_mm / 2.0 - 1.0), dir=cq.Vector(0, 0, 1))))
    if params.emission:
        f = params.emission
        ex = cq.Vector(*plan.exit_dir).normalized()
        face = plan.params.interface.edge_half
        body = body.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
            f.diameter_mm / 2.0 + c, f.thickness_mm + c + 1.0,
            pnt=ex.multiply(face + 1.0), dir=ex.multiply(-1.0))))
    solids = body.solids().vals()
    if len(solids) != 1:
        raise ValueError(
            f"the insert is {len(solids)} piece(s) — a pocket broke through; a smaller "
            "filter or a thicker wall")
    return body
