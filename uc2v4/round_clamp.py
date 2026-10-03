"""Round clamp: a cylinder body (laser module, fibre collimator, LED or lens tube, up to
Ø34 mm) held in an openUC2 cube between two master inserts, with a radial set screw.

The printed clamp is a double base-holder disc (the master insert's 82 deg cone and 8 noses
on both faces) trapped between a MASLCK on a notch and a MASINS, the same capture as the lens
cartridge, plus a sleeve along the body and a bore. One set screw, thread-formed into the
printed wall (a boss where the sleeve is too thin), presses the body against the bore. The
body slides through before the screw is tightened, and may pass a cube face (Ø ≤ 34 mm).

Frame (the clamp frame): body axis = z, the joint plane of the sandwich at z = 0; units mm.
``RoundClampPlan.joint_z_mm`` places it in the cube.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from .lens_cartridge import CubeInterface, snap_joint
from .round_holder import BaseHolderInterface, build_base_holder

#: Thread-forming pilot, boss radius and socket-head radius per screw size.
SCREWS = {"M3": (2.5, 3.5, 2.75), "M4": (3.3, 4.5, 3.5)}
#: Thread a printed wall needs to hold a set screw.
MIN_THREAD_MM = 4.0
#: Half the face port: a screw head outside it cannot be reached with a hex key.
PORT_HALF_MM = 17.0


@dataclass(frozen=True)
class RoundClampParams:
    body_d_mm: float
    z_mm: float = 0.0                     # where the joint should go (nearest legal joint)
    offset_mm: tuple[float, float] = (0.0, 0.0)   # body axis from the cube axis
    fit_clearance_mm: float = 0.15        # radial gap around the body
    min_wall_mm: float = 1.6
    grip_front_mm: float = 10.0           # sleeve beyond the disc, +z side
    grip_back_mm: float = 10.0            # sleeve beyond the disc, -z side
    screw: str = "M3"
    screw_side: str = "auto"              # front, back, or the side facing the cube centre
    screw_angle_deg: float = 90.0         # about the axis, from +x (90 = +y)
    snap_to_notch: bool = True
    master_thickness_mm: float = 4.0


@dataclass
class RoundClampPlan:
    params: RoundClampParams
    joint_z_mm: float = 0.0
    notched_half: str = "auto"
    bore_r_mm: float = 0.0
    sleeve_r_mm: float = 0.0
    boss_r_mm: float = 0.0                # 0 = no boss
    boss_top_mm: float = 0.0              # how far out from the body axis the boss reaches
    screw_z_mm: float = 0.0               # clamp frame
    z_range_mm: tuple[float, float] = (0.0, 0.0)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {
            "joint_z_mm": round(self.joint_z_mm, 3),
            "notched_half": self.notched_half,
            "bore_d_mm": round(2 * self.bore_r_mm, 3),
            "sleeve_d_mm": round(2 * self.sleeve_r_mm, 3),
            "boss_r_mm": round(self.boss_r_mm, 3),
            "screw": self.params.screw,
            "screw_z_mm": round(self.screw_z_mm, 3),
            "z_range_mm": [round(v, 3) for v in self.z_range_mm],
            "warnings": self.warnings,
        }


def seat() -> BaseHolderInterface:
    return BaseHolderInterface(thickness=4.0, interface_mid_z=2.0, skirt=0.0)


def plan_round_clamp(p: RoundClampParams, cube: CubeInterface | None = None) -> RoundClampPlan:
    """Check the body against the cube and the sandwich; nothing is built."""
    cube = cube or CubeInterface()
    if p.screw not in SCREWS:
        raise ValueError(f"screw must be one of {sorted(SCREWS)}, got {p.screw!r}")
    if p.screw_side not in ("auto", "front", "back"):
        raise ValueError(f"screw_side must be auto, front or back, got {p.screw_side!r}")
    if not 2.0 < p.body_d_mm <= 34.0:
        raise ValueError(
            f"a Ø{p.body_d_mm} mm body: the clamp holds bodies up to Ø34 mm, the opening "
            "of a cube face")
    t = p.master_thickness_mm
    half, _, _, joint = snap_joint(p.z_mm, cube, t, "auto" if p.snap_to_notch else None)
    plan = RoundClampPlan(params=p, joint_z_mm=joint, notched_half=half)

    pilot, boss_r, head_r = SCREWS[p.screw]
    s = seat()
    offset = math.hypot(*p.offset_mm)
    plan.bore_r_mm = p.body_d_mm / 2.0 + p.fit_clearance_mm
    if offset + plan.bore_r_mm + p.min_wall_mm > s.top_face_radius + 1e-9:
        raise ValueError(
            f"a Ø{p.body_d_mm} mm body {offset:.2f} mm off the axis needs "
            f"{offset + plan.bore_r_mm + p.min_wall_mm:.2f} mm of radius; the disc between "
            f"the master inserts offers {s.top_face_radius:.2f} mm")
    plan.sleeve_r_mm = min(plan.bore_r_mm + MIN_THREAD_MM, s.top_face_radius - offset)

    # The sleeve stays in the cube: past the end frames only the body goes on.
    room_front = cube.round_limit_mm - joint - t
    room_back = cube.round_limit_mm + joint - t
    grip_front, grip_back = min(p.grip_front_mm, room_front), min(p.grip_back_mm, room_back)
    for name, asked, got in (("front", p.grip_front_mm, grip_front),
                             ("back", p.grip_back_mm, grip_back)):
        if got < asked - 1e-9:
            plan.warnings.append(f"the {name} sleeve is cut to {got:.2f} mm to stay inside "
                                 f"the cube (±{cube.round_limit_mm:g} mm)")
    side = p.screw_side
    if side == "auto":
        side = "back" if joint > 0 else "front"
        if (grip_back if side == "back" else grip_front) < 2.0 * boss_r + 1.0:
            side = "front" if side == "back" else "back"
    grip = grip_front if side == "front" else grip_back
    if grip < 2.0 * boss_r + 1.0:
        raise ValueError(
            f"the {side} sleeve is {grip:g} mm long; an {p.screw} set screw needs "
            f"{2.0 * boss_r + 1.0:g} mm of sleeve beyond the master insert")
    # Right beside the master insert, so a boss never meets its square outline.
    plan.screw_z_mm = (1.0 if side == "front" else -1.0) * (t + boss_r + 0.5)
    wall = plan.sleeve_r_mm - plan.bore_r_mm
    if wall < MIN_THREAD_MM - 1e-9:
        plan.boss_r_mm = boss_r
        plan.boss_top_mm = plan.bore_r_mm + MIN_THREAD_MM
        plan.warnings.append(
            f"the sleeve wall is {wall:.2f} mm; the {p.screw} screw gets a boss reaching "
            f"{plan.boss_top_mm:.2f} mm from the axis")
    reach = abs(joint + plan.screw_z_mm) + head_r
    if reach > PORT_HALF_MM:
        raise ValueError(
            f"the set screw sits {abs(joint + plan.screw_z_mm):.2f} mm from the cube centre; "
            f"its head has to stay within the {2 * PORT_HALF_MM:g} mm port of the face to be "
            "reached with a hex key. Shorten the sleeve or move the clamp inward")
    plan.z_range_mm = (-(t + max(grip_back, 0.0)), t + max(grip_front, 0.0))
    return plan


def _cylinder(r: float, z0: float, z1: float, at=(0.0, 0.0)) -> cq.Solid:  # noqa: ANN001
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(at[0], at[1], z0), cq.Vector(0, 0, 1))


def build_round_clamp(plan: RoundClampPlan) -> cq.Workplane:
    """The printed clamp in the clamp frame (joint plane at z = 0, body axis = z)."""
    p, t = plan.params, plan.params.master_thickness_mm
    front = build_base_holder(seat())
    disc = front.union(cq.Workplane("XY").add(front.val().mirror("XY")))
    lo, hi = plan.z_range_mm
    body = disc.union(cq.Workplane("XY").add(_cylinder(plan.sleeve_r_mm, lo, hi, p.offset_mm)))
    a = math.radians(p.screw_angle_deg)
    direction = cq.Vector(math.cos(a), math.sin(a), 0.0)
    origin = cq.Vector(p.offset_mm[0], p.offset_mm[1], plan.screw_z_mm)
    if plan.boss_r_mm:
        boss = cq.Solid.makeCylinder(plan.boss_r_mm, plan.boss_top_mm, origin, direction)
        body = body.union(cq.Workplane("XY").add(boss))
    body = body.cut(cq.Workplane("XY").add(_cylinder(plan.bore_r_mm, lo - 1.0, hi + 1.0,
                                                     p.offset_mm)))
    pilot = SCREWS[p.screw][0] / 2.0
    reach = max(plan.boss_top_mm, plan.sleeve_r_mm) + 1.0
    body = body.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(pilot, reach, origin, direction)))
    return body.clean()
