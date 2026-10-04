"""Cartridge with focus adjustment: a lens in a printed barrel that slides ±``travel_mm``
along the beam in a round clamp (``round_clamp``) and is locked by the clamp's set screw.

For a locked distance tighter than a printed cartridge holds (its play is about 0.15 mm): set
the lens while watching the image, then tighten. The lens rests on a lip in the barrel, cut to
its own surface, and is held by a ring pressed (or glued) in from the other end. The barrel is
as long as the clamp plus the travel at both ends, so the clamp grips it over its full length
anywhere in the range.

Frame: the clamp frame (body axis = z, the sandwich's joint plane at z = 0); the lens centre
at ``lens_z_mm`` from the joint at the middle of the travel. Units mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

from .lens_cartridge import Lens, lens_solid
from .round_clamp import RoundClampParams, RoundClampPlan, plan_round_clamp


@dataclass(frozen=True)
class FocusCartridgeParams:
    lens: Lens
    z_mm: float = 0.0               # lens centre along the beam, from the cube centre
    travel_mm: float = 1.0          # ± along the beam
    wall_mm: float = 1.2            # barrel wall around the lens
    lip_mm: float = 1.5             # lip under the lens rim: clear aperture = Ø - 2 lip
    lip_length_mm: float = 1.2
    ring_mm: float = 2.5            # the retaining ring's length
    fit_clearance_mm: float = 0.15  # lens in the barrel
    slide_clearance_mm: float = 0.15   # barrel in the clamp
    screw: str = "M3"
    grip_front_mm: float = 10.0
    grip_back_mm: float = 10.0


@dataclass
class FocusCartridgePlan:
    params: FocusCartridgeParams
    clamp: RoundClampPlan
    lens_z_mm: float = 0.0          # clamp frame
    barrel_r_mm: float = 0.0
    bore_r_mm: float = 0.0
    clear_r_mm: float = 0.0
    barrel_z_mm: tuple[float, float] = (0.0, 0.0)   # clamp frame, at the middle of the travel
    lens_z_range_mm: tuple[float, float] = (0.0, 0.0)
    ring_z_mm: tuple[float, float] = (0.0, 0.0)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"joint_z_mm": round(self.clamp.joint_z_mm, 3),
                "lens_z_from_joint_mm": round(self.lens_z_mm, 3),
                "travel_mm": self.params.travel_mm,
                "barrel_d_mm": round(2 * self.barrel_r_mm, 3),
                "clear_aperture_mm": round(2 * self.clear_r_mm, 3),
                "barrel_z_mm": [round(v, 3) for v in self.barrel_z_mm],
                "clamp": self.clamp.report(), "warnings": self.warnings}


def plan_focus_cartridge(p: FocusCartridgeParams) -> FocusCartridgePlan:
    """Check the lens, the barrel and the clamp; nothing is built."""
    lens = p.lens
    lens.validate()
    if lens.outline_mm is not None:
        raise ValueError("a rectangular lens cannot turn in a round barrel — the focus "
                         "cartridge takes round optics")
    if not 0.1 <= p.travel_mm <= 5.0:
        raise ValueError(f"travel ±{p.travel_mm} mm: give 0.1 to 5 mm")
    bore = lens.semi_diameter + p.fit_clearance_mm
    barrel_r = bore + p.wall_mm
    clear = lens.semi_diameter - p.lip_mm
    if clear <= 0.5:
        raise ValueError(f"a {p.lip_mm} mm lip leaves no clear aperture on a "
                         f"Ø{lens.diameter_mm} mm lens")
    clamp = plan_round_clamp(RoundClampParams(
        body_d_mm=2.0 * barrel_r, z_mm=p.z_mm, fit_clearance_mm=p.slide_clearance_mm,
        screw=p.screw, grip_front_mm=p.grip_front_mm, grip_back_mm=p.grip_back_mm))
    plan = FocusCartridgePlan(params=p, clamp=clamp, barrel_r_mm=barrel_r, bore_r_mm=bore,
                              clear_r_mm=clear, warnings=list(clamp.warnings))
    plan.lens_z_mm = p.z_mm - clamp.joint_z_mm
    zv1, zv2 = lens.vertices()
    s1, s2 = lens.sags()
    lo = plan.lens_z_mm + min(zv1, zv1 + s1)
    hi = plan.lens_z_mm + max(zv2, zv2 + s2)
    plan.lens_z_range_mm = (lo, hi)
    # The ring meets the second face at its rim; its inner edge is cut to the face.
    rim2 = plan.lens_z_mm + zv2 + s2 + p.fit_clearance_mm
    plan.ring_z_mm = (rim2, max(rim2, hi) + p.ring_mm)
    c_lo, c_hi = clamp.z_range_mm
    z_lo = min(lo - p.lip_length_mm, c_lo - p.travel_mm)
    z_hi = max(plan.ring_z_mm[1], c_hi + p.travel_mm)
    plan.barrel_z_mm = (z_lo, z_hi)
    return plan


def _tube(r_out: float, r_in: float, z0: float, z1: float) -> cq.Workplane:
    tube = cq.Solid.makeCylinder(r_out, z1 - z0, cq.Vector(0, 0, z0), cq.Vector(0, 0, 1))
    if r_in > 0:
        tube = tube.cut(cq.Solid.makeCylinder(r_in, z1 - z0 + 2.0, cq.Vector(0, 0, z0 - 1.0),
                                              cq.Vector(0, 0, 1)))
    return cq.Workplane("XY").add(tube)


def build_focus_barrel(plan: FocusCartridgePlan) -> tuple[cq.Workplane, cq.Workplane]:
    """(barrel, ring) in the clamp frame at the middle of the travel."""
    p = plan.params
    z_lo, z_hi = plan.barrel_z_mm
    lo, hi = plan.lens_z_range_mm
    barrel = _tube(plan.barrel_r_mm, plan.clear_r_mm, z_lo, z_hi)
    # The lens goes in from +z: full bore down to the rim of its first face; the lip inside
    # that rim is cut to the face itself, so the lens rests on it.
    zv1, _ = p.lens.vertices()
    s1, _ = p.lens.sags()
    rim = plan.lens_z_mm + zv1 + s1 - p.fit_clearance_mm
    barrel = barrel.cut(_tube(plan.bore_r_mm, 0.0, rim, z_hi + 1.0))
    cavity = lens_solid(p.lens, p.fit_clearance_mm).translate((0, 0, plan.lens_z_mm))
    barrel = barrel.cut(cavity).clean()
    r0, r1 = plan.ring_z_mm
    ring = _tube(plan.bore_r_mm - 0.05, plan.clear_r_mm, r0, r1)
    ring = ring.cut(lens_solid(p.lens, p.fit_clearance_mm).translate((0, 0, plan.lens_z_mm)))
    return barrel, ring.clean()
