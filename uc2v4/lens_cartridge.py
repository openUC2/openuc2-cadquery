"""Automatic generation of the 3D-printable round insert pair that holds a
lens at an arbitrary pose inside an openUC2 V4 cube.

The manufacturing split this implements
---------------------------------------
Injection molded, never regenerated:

- the **cube**, whose inner tracks carry 7 notches at a 5.0 mm pitch,
  symmetric about the cube centre (-15, -10, -5, 0, +5, +10, +15 mm)
  — measured from ``PRT - 1003 - CUBHLF111 - V04``;
- two **master inserts** (PRT-2100 / PRT-2123), screwed face to face into a
  sandwich. Each is 4 mm thick with an 82 deg conic Ø40 opening; the notched
  variant snaps to the grid, the smooth variant slides freely.

3D printed, generated here:

- a **front** and a **back** round insert. Each seats in one master insert's
  cone via the base-holder profile from ``round_holder.py`` (so it carries
  the 8 noses and indexes every 45 deg), and together they wrap the lens.

So the cube gives a coarse, discrete axial position and the printed pair
absorbs everything left over: the residual axial offset plus the full
transverse offset and tilt. That is the whole trick — precision where it is
cheap (the mold), freedom where it is cheap (the printer).

Coordinates
-----------
Cube frame: origin at the **cube centre**, optical axis = Z. A pose is the
lens position (x, y, z) and tilt (rx, ry, rz) in that frame; ``Lens.reference``
picks which point of the lens (x, y, z) refers to.

Cartridge frame: origin on the sandwich **joint plane** (where the two master
inserts meet), so ``z_cartridge = z_cube - notch_z``.

Typical use
-----------
    lens = Lens(diameter_mm=25.4, center_thickness_mm=3.5, r1_mm=51.5, r2_mm=-51.5)
    plan = plan_cartridge(lens, Pose(x_mm=2.0, y_mm=-1.0, z_mm=7.3))
    front, back = build_cartridge(plan)

or from the command line, see ``--help``.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .round_holder import BaseHolderInterface, build_base_holder
except ImportError:                     # pragma: no cover
    from round_holder import BaseHolderInterface, build_base_holder


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lens:
    """A spherical singlet.

    Sign convention is the optical one: a surface radius is positive when its
    centre of curvature lies on the +Z side of the vertex, so a biconvex lens
    has ``r1_mm > 0`` and ``r2_mm < 0``. Use ``math.inf`` for a flat surface.
    """

    diameter_mm: float
    center_thickness_mm: float
    r1_mm: float = math.inf
    r2_mm: float = math.inf
    reference: str = "center"   # "center" | "front_vertex" | "back_vertex"

    @property
    def semi_diameter(self) -> float:
        return self.diameter_mm / 2.0

    def sag(self, radius: float, semi_diameter: float | None = None) -> float:
        """Axial rise of a surface from its vertex to *semi_diameter*."""
        h = self.semi_diameter if semi_diameter is None else semi_diameter
        if not math.isfinite(radius):
            return 0.0
        if abs(radius) < h:
            raise ValueError(
                f"surface radius {radius} mm is smaller than the semi-diameter "
                f"{h} mm — that surface cannot span the lens")
        return radius - math.copysign(math.sqrt(radius * radius - h * h), radius)

    @property
    def edge_thickness_mm(self) -> float:
        et = self.center_thickness_mm + self.sag(self.r2_mm) - self.sag(self.r1_mm)
        return et

    def vertices(self) -> tuple[float, float]:
        """(z of surface-1 vertex, z of surface-2 vertex) about the reference."""
        ct = self.center_thickness_mm
        if self.reference == "center":
            return -ct / 2.0, ct / 2.0
        if self.reference == "front_vertex":
            return 0.0, ct
        if self.reference == "back_vertex":
            return -ct, 0.0
        raise ValueError(f"unknown Lens.reference {self.reference!r}")

    def validate(self) -> None:
        if self.diameter_mm <= 0 or self.center_thickness_mm <= 0:
            raise ValueError("lens diameter and centre thickness must be positive")
        if self.edge_thickness_mm <= 0:
            raise ValueError(
                f"edge thickness is {self.edge_thickness_mm:.3f} mm — this lens "
                "closes up before its rim; check r1/r2 against the diameter")


@dataclass(frozen=True)
class Pose:
    """Target lens pose in the cube frame (origin = cube centre, mm / deg)."""

    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0
    rx_deg: float = 0.0
    ry_deg: float = 0.0
    rz_deg: float = 0.0


@dataclass(frozen=True)
class CubeInterface:
    """The molded cube's discrete grid, measured from PRT - 1003 - CUBHLF111."""

    grid_mm: float = 50.0
    notch_pitch_mm: float = 5.0
    notch_count: int = 7          # -> notches at -15, -10, -5, 0, +5, +10, +15

    def notch_positions(self) -> list[float]:
        k = (self.notch_count - 1) / 2.0
        return [(i - k) * self.notch_pitch_mm for i in range(self.notch_count)]

    def snap(self, z: float) -> tuple[int, float]:
        """Nearest notch to *z*: returns (index, z of that notch)."""
        pos = self.notch_positions()
        idx = min(range(len(pos)), key=lambda i: abs(pos[i] - z))
        return idx, pos[idx]


@dataclass(frozen=True)
class CartridgeParams:
    """Everything about the printed pair that is not the lens or the pose."""

    master_thickness_mm: float = 4.0     # one master insert = one seat depth
    # Extra axial room. It is added at each half's *outward* (narrow) end —
    # the same side the nose caps sit on — because that is the only direction
    # a half can grow: inward is the other half, and the seating cone must
    # stay untouched. This is the "skirt / support" of the hand sketch.
    extension_front_mm: float = 0.0
    extension_back_mm: float = 0.0
    fit_clearance_mm: float = 0.15       # gap all around the lens (print fit)
    rim_mm: float = 1.5                  # radial overlap that actually holds it
    clear_aperture_mm: float | None = None   # default: diameter - 2*rim
    min_wall_mm: float = 0.8             # thinnest acceptable printed wall

    snap_to_notch: bool = True           # False = the smooth, freely sliding master
    noses: bool = True                   # index the printed part every 45 deg

    # Which master insert of the sandwich carries the locking tongue. The
    # tongue is centred on that insert's mid-plane (MAS-2003 "Skizze37 --- for
    # tongue": profile z = -2..+2, tip at z = 0), so the notch fixes that
    # mid-plane and the joint plane lands half an insert away from it.
    # "auto" picks whichever side gets the lens closer to its target.
    notched_half: str = "auto"           # "auto" | "back" | "front"

    alignment_pins: int = 2              # 0 disables
    pin_boss_on: str = "back"            # which half grows the bosses
    pin_diameter_mm: float = 2.0
    pin_length_mm: float = 2.0
    pin_clearance_mm: float = 0.15
    pin_circle_mm: float = 16.5

    # Engraved identification on each outward face.
    label: str | None = None             # None -> auto from the lens and pose
    label_size_mm: float = 2.6
    label_depth_mm: float = 0.4

    def seat(self) -> BaseHolderInterface:
        """The front half's seating profile: band [0, t] above the joint.

        The two master inserts mate flipped (their self-mating screw pattern
        forces a 180 deg flip), so **both cones are wide at the joint and
        narrow outward**. A printed half is therefore dropped in from the
        joint side and trapped by the narrowing cone once the sandwich is
        screwed shut — the wide Ø40 ring faces inward, not outward.
        """
        return BaseHolderInterface(
            thickness=self.master_thickness_mm,
            interface_mid_z=self.master_thickness_mm / 2.0,
            skirt=0.0,                   # flush butt face on the joint plane
            noses=self.noses,
        )


# ---------------------------------------------------------------------------
# planning: cube grid -> what the printed part has to absorb
# ---------------------------------------------------------------------------

@dataclass
class CartridgePlan:
    lens: Lens
    pose: Pose
    cube: CubeInterface
    params: CartridgeParams

    notch_index: int = 0
    notch_z_mm: float = 0.0
    joint_z_mm: float = 0.0
    notched_half: str = "back"
    residual_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    clear_aperture_mm: float = 0.0
    usable_radius_mm: float = 0.0
    z_range_mm: tuple[float, float] = (0.0, 0.0)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        dx, dy, dz = self.residual_mm
        return {
            "lens": asdict(self.lens),
            "requested_pose": asdict(self.pose),
            "notch_index": self.notch_index,
            "notch_z_mm": round(self.notch_z_mm, 4),
            "notched_half": self.notched_half,
            "joint_z_mm": round(self.joint_z_mm, 4),
            "residual_offset_mm": {"dx": round(dx, 4), "dy": round(dy, 4),
                                   "dz": round(dz, 4)},
            "edge_thickness_mm": round(self.lens.edge_thickness_mm, 4),
            "clear_aperture_mm": round(self.clear_aperture_mm, 4),
            "cartridge_z_range_mm": [round(v, 4) for v in self.z_range_mm],
            "usable_radius_mm": round(self.usable_radius_mm, 4),
            "warnings": self.warnings,
        }


def plan_cartridge(lens: Lens, pose: Pose,
                   cube: CubeInterface | None = None,
                   params: CartridgeParams | None = None) -> CartridgePlan:
    """Snap to the cube grid and work out what the printed pair must absorb."""
    cube = cube or CubeInterface()
    params = params or CartridgeParams()
    lens.validate()

    t = params.master_thickness_mm
    if params.snap_to_notch:
        # The notch fixes the *notched insert's mid-plane*; the joint plane sits
        # half an insert to one side of it, on whichever side the second master
        # insert is stacked.
        sides = {"back": +1.0, "front": -1.0}
        if params.notched_half == "auto":
            candidates = list(sides.items())
        elif params.notched_half in sides:
            candidates = [(params.notched_half, sides[params.notched_half])]
        else:
            raise ValueError(f"notched_half must be auto/back/front, "
                             f"got {params.notched_half!r}")

        best = None
        for name, sign in candidates:
            idx, notch_z = cube.snap(pose.z_mm - sign * t / 2.0)
            joint_z = notch_z + sign * t / 2.0
            key = abs(pose.z_mm - joint_z)
            if best is None or key < best[0]:
                best = (key, name, idx, notch_z, joint_z)
        _, half_name, idx, notch_z, joint_z = best

        limit = max(cube.notch_positions())
        if abs(notch_z) > limit + 1e-9 or abs(pose.z_mm - joint_z) > t:
            raise ValueError(
                f"z = {pose.z_mm} mm cannot be reached on the notch grid "
                f"(notches at +-{limit} mm, pitch {cube.notch_pitch_mm} mm). "
                "Use snap_to_notch=False with the smooth master insert, or move "
                "the component to a neighbouring cube.")
    else:
        # Smooth master insert: it slides, so the joint can land exactly on z.
        half_name, idx, notch_z, joint_z = "none", -1, float("nan"), pose.z_mm

    dz = pose.z_mm - joint_z
    plan = CartridgePlan(lens=lens, pose=pose, cube=cube, params=params,
                         notch_index=idx, notch_z_mm=notch_z, joint_z_mm=joint_z,
                         notched_half=half_name,
                         residual_mm=(pose.x_mm, pose.y_mm, dz))

    aperture = params.clear_aperture_mm
    if aperture is None:
        aperture = lens.diameter_mm - 2.0 * params.rim_mm
    if aperture <= 0 or aperture >= lens.diameter_mm:
        raise ValueError(
            f"clear aperture {aperture} mm must be positive and smaller than the "
            f"lens diameter {lens.diameter_mm} mm")
    plan.clear_aperture_mm = aperture

    plan.z_range_mm = (-(t + params.extension_back_mm), t + params.extension_front_mm)
    _check_fit(plan)
    return plan


def available_radius(seat: BaseHolderInterface, z_from_joint: float) -> float:
    """Inner radius the printed half offers at *z_from_joint* (either side).

    The cone is widest on the joint plane and narrows outward, so — unlike the
    molded mirror holder — the tight spot is now at the *outward* faces.
    """
    z = abs(z_from_joint)
    if z >= seat.thickness - seat.top_fillet:
        return seat.top_face_radius            # past the blend, and the extension
    return seat.max_radius - z * math.tan(seat.half_angle_rad)


def _check_fit(plan: CartridgePlan) -> None:
    lens, params = plan.lens, plan.params
    dx, dy, dz = plan.residual_mm
    seat = params.seat()

    # Axial: the lens' own extent, inflated by tilt, must sit inside the puck.
    zv1, zv2 = lens.vertices()
    half_extent = max(abs(zv1), abs(zv2), abs(zv1 + lens.sag(lens.r1_mm)),
                      abs(zv2 + lens.sag(lens.r2_mm)))
    tilt = max(abs(plan.pose.rx_deg), abs(plan.pose.ry_deg))
    half_extent += lens.semi_diameter * math.sin(math.radians(tilt))
    half_extent += params.fit_clearance_mm

    # Radial: check where the lens reaches furthest out along the axis, since
    # that is where the cone has closed in the most.
    lo, hi = plan.z_range_mm
    z_lo = max(dz - half_extent, lo)
    z_hi = min(dz + half_extent, hi)
    plan.usable_radius_mm = min(available_radius(seat, z_lo),
                                available_radius(seat, z_hi))

    offset = math.hypot(dx, dy)
    needed = offset + lens.semi_diameter + params.fit_clearance_mm + params.min_wall_mm
    if needed > plan.usable_radius_mm:
        raise ValueError(
            f"lens Ø{lens.diameter_mm} mm offset {offset:.2f} mm needs "
            f"{needed:.2f} mm of radius; the insert only offers "
            f"{plan.usable_radius_mm:.2f} mm over the z range it occupies. "
            "Reduce the transverse offset, the diameter, or min_wall_mm.")

    if dz - half_extent < lo + params.min_wall_mm:
        plan.warnings.append(
            f"lens reaches z={dz - half_extent:.2f} mm, within {params.min_wall_mm} mm "
            f"of the back face at {lo:.2f} mm — raise extension_back_mm")
    if dz + half_extent > hi - params.min_wall_mm:
        plan.warnings.append(
            f"lens reaches z={dz + half_extent:.2f} mm, within {params.min_wall_mm} mm "
            f"of the front face at {hi:.2f} mm — raise extension_front_mm")

    grip = min(dz + half_extent, hi) - max(dz - half_extent, lo)
    if dz - half_extent > 0 or dz + half_extent < 0:
        plan.warnings.append(
            "the lens lies entirely on one side of the joint plane; that half "
            "does all the holding and the other is only a spacer")
    elif grip <= 0:
        plan.warnings.append("lens does not intersect the cartridge volume")


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def _surface_arc(z_center: float, radius: float, h: float, z_vertex: float):
    """Three points (vertex, mid, edge) of a spherical surface in the (r, z) plane."""
    if not math.isfinite(radius):
        return (0.0, z_vertex), (h / 2.0, z_vertex), (h, z_vertex)
    phi_max = math.asin(min(h / abs(radius), 1.0))

    def at(phi):
        r = abs(radius) * math.sin(phi)
        z = z_center - math.copysign(abs(radius) * math.cos(phi), radius)
        return (r, z)

    return at(0.0), at(phi_max / 2.0), at(phi_max)


def lens_solid(lens: Lens, clearance: float = 0.0) -> cq.Workplane:
    """The lens as a revolved solid, uniformly grown by *clearance*.

    Growing a sphere outward is exact in the signed convention: the centre of
    curvature stays put, so r1 -> r1 + c and r2 -> r2 - c while the vertices
    move apart by c. The only approximation is the rim, where the offset is a
    sharp corner instead of a c-radius round — i.e. slightly more clearance.
    """
    c = clearance
    zv1, zv2 = lens.vertices()
    zv1, zv2 = zv1 - c, zv2 + c
    r1 = lens.r1_mm + c if math.isfinite(lens.r1_mm) else math.inf
    r2 = lens.r2_mm - c if math.isfinite(lens.r2_mm) else math.inf
    h = lens.semi_diameter + c

    for radius, name in ((r1, "r1"), (r2, "r2")):
        if math.isfinite(radius) and abs(radius) < h:
            raise ValueError(
                f"with {clearance} mm clearance the {name} surface (R={radius:.3f}) "
                f"can no longer span the Ø{2 * h:.3f} mm rim")

    v1, m1, e1 = _surface_arc(zv1 + r1 if math.isfinite(r1) else 0.0, r1, h, zv1)
    v2, m2, e2 = _surface_arc(zv2 + r2 if math.isfinite(r2) else 0.0, r2, h, zv2)

    wp = cq.Workplane("XZ").moveTo(*v1)
    wp = wp.lineTo(*e1) if not math.isfinite(r1) else wp.threePointArc(m1, e1)
    wp = wp.lineTo(*e2)
    wp = wp.lineTo(*v2) if not math.isfinite(r2) else wp.threePointArc(m2, v2)
    return wp.close().revolve(360.0, (0, 0, 0), (0, 1, 0))


def _place(shape, plan: CartridgePlan):
    """Rotate a shape about the lens reference point, then move it into place."""
    dx, dy, dz = plan.residual_mm
    p = plan.pose
    s = shape
    for angle, axis in ((p.rx_deg, (1, 0, 0)), (p.ry_deg, (0, 1, 0)),
                        (p.rz_deg, (0, 0, 1))):
        if angle:
            s = s.rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), angle)
    return s.translate(cq.Vector(dx, dy, dz))


def _cavity(plan: CartridgePlan) -> cq.Workplane:
    """Lens pocket plus the clear-aperture bore, already posed."""
    pocket = lens_solid(plan.lens, plan.params.fit_clearance_mm).val()

    lo, hi = plan.z_range_mm
    length = (hi - lo) * 3.0 + plan.lens.diameter_mm
    bore = cq.Solid.makeCylinder(
        plan.clear_aperture_mm / 2.0, length,
        pnt=cq.Vector(0, 0, -length / 2.0), dir=cq.Vector(0, 0, 1))

    return (cq.Workplane("XY").add(_place(pocket, plan))
            .union(cq.Workplane("XY").add(_place(bore, plan))))


def _pin_angles(plan: CartridgePlan) -> list[float]:
    """Clock the alignment pins so they clear the lens pocket."""
    n = plan.params.alignment_pins
    if n <= 0:
        return []
    dx, dy, _ = plan.residual_mm
    keep_out = (plan.lens.semi_diameter + plan.params.fit_clearance_mm
                + plan.params.pin_diameter_mm / 2.0 + plan.params.min_wall_mm)
    best, best_margin = None, -1e9
    for start in range(0, 360, 5):
        margin = 1e9
        for i in range(n):
            a = math.radians(start + i * 360.0 / n)
            px = plan.params.pin_circle_mm * math.cos(a)
            py = plan.params.pin_circle_mm * math.sin(a)
            margin = min(margin, math.hypot(px - dx, py - dy) - keep_out)
        if margin > best_margin:
            best, best_margin = start, margin
    if best_margin < 0:
        plan.warnings.append(
            "no clocking leaves room for the alignment pins — they were dropped")
        return []
    return [best + i * 360.0 / n for i in range(n)]


def _pin_solids(plan: CartridgePlan, angles: list[float], socket: bool,
                sign: float = 1.0):
    """Pins straddling the joint. *sign* is +1 when the boss half is the back
    one (bosses grow into +Z), -1 when it is the front one."""
    p = plan.params
    r = p.pin_diameter_mm / 2.0 + (p.pin_clearance_mm if socket else 0.0)
    length = p.pin_length_mm + (p.pin_clearance_mm if socket else 0.0)
    out = []
    for a in angles:
        rad = math.radians(a)
        x, y = p.pin_circle_mm * math.cos(rad), p.pin_circle_mm * math.sin(rad)
        out.append(cq.Solid.makeCylinder(r, length, pnt=cq.Vector(x, y, 0.0),
                                         dir=cq.Vector(0, 0, sign)))
    return out


def _half_blank(plan: CartridgePlan, extension: float) -> cq.Workplane:
    """One printable half in front orientation: band [0, t], wide on the joint.

    The optional extension is a flush cylinder off the *narrow* end, which is
    the only direction a half may grow.
    """
    seat = plan.params.seat()
    blank = build_base_holder(seat)
    if extension > 1e-9:
        boss = cq.Solid.makeCylinder(
            seat.top_face_radius, extension,
            pnt=cq.Vector(0, 0, seat.z_band_top), dir=cq.Vector(0, 0, 1))
        blank = blank.union(cq.Workplane("XY").add(boss))
    return blank


def _auto_label(plan: CartridgePlan, side: str) -> str:
    n = "" if plan.notch_index < 0 else f"N{plan.notch_index}"
    return f"D{plan.lens.diameter_mm:g} {n} {side[0].upper()}".replace("  ", " ").strip()


def _engrave(half: cq.Workplane, plan: CartridgePlan, text: str,
             z_face: float, outward: int) -> cq.Workplane:
    """Sink *text* into the outward face; failures are cosmetic, never fatal."""
    p = plan.params
    if not text or p.label_depth_mm <= 0:
        return half
    dx, dy, _ = plan.residual_mm
    seat = p.seat()
    r_out = seat.top_face_radius

    # Put the label on the widest part of the annulus, i.e. away from the bore,
    # and run it *tangentially* — a radial string of any length walks off the
    # rim, a tangential one only ever spans `size` in the radial direction.
    norm = math.hypot(dx, dy)
    ux, uy = (-dx / norm, -dy / norm) if norm > 1e-6 else (0.0, -1.0)
    r_in = max(plan.clear_aperture_mm / 2.0 - norm, 0.0)
    r_place = (r_out + r_in) / 2.0

    size = min(p.label_size_mm, (r_out - r_in) * 0.5)
    for _ in range(6):                        # shrink until the ends fit inside
        half_len = 0.32 * size * max(len(text), 1)
        if math.hypot(r_place, half_len) <= r_out - 0.4 or size <= 1.2:
            break
        size *= 0.8
    if size < 1.0:
        plan.warnings.append("no room for a legible label on the outward face")
        return half

    z0 = z_face - (p.label_depth_mm if outward > 0 else 1.0)
    try:
        solid = (cq.Workplane("XY").workplane(offset=z0)
                 .text(text, size, p.label_depth_mm + 1.0).val())
        if outward < 0:                       # so it reads right from outside
            solid = solid.mirror("YZ")
        angle = math.degrees(math.atan2(uy, ux)) - 90.0
        solid = solid.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), angle)
        solid = solid.translate(cq.Vector(ux * r_place, uy * r_place, 0.0))
        return half.cut(cq.Workplane("XY").add(solid))
    except Exception as exc:                  # missing font, degenerate glyphs
        plan.warnings.append(f"could not engrave the label ({exc.__class__.__name__})")
        return half


def build_cartridge(plan: CartridgePlan) -> tuple[cq.Workplane, cq.Workplane]:
    """Return (front, back) — the two printable halves, in the cartridge frame.

    Front occupies z >= 0, back occupies z <= 0; the joint plane is z = 0 and
    corresponds to ``plan.joint_z_mm`` in the cube frame. Both halves present
    their wide Ø40 cone ring to the joint, so each drops into its master
    insert from the inside and is trapped when the sandwich is screwed shut.
    """
    p = plan.params
    t = p.master_thickness_mm

    front = _half_blank(plan, p.extension_front_mm)          # spans [0, t+ext]
    back = cq.Workplane("XY").add(
        _half_blank(plan, p.extension_back_mm).val().mirror("XY"))   # [-t-ext, 0]

    cavity = _cavity(plan)
    front = front.cut(cavity)
    back = back.cut(cavity)

    angles = _pin_angles(plan)
    if angles:
        boss_on_back = p.pin_boss_on == "back"
        bosses, sockets = (back, front) if boss_on_back else (front, back)
        sign = 1.0 if boss_on_back else -1.0
        for boss in _pin_solids(plan, angles, socket=False, sign=sign):
            bosses = bosses.union(cq.Workplane("XY").add(boss))
        for socket in _pin_solids(plan, angles, socket=True, sign=sign):
            sockets = sockets.cut(cq.Workplane("XY").add(socket))
        front, back = (sockets, bosses) if boss_on_back else (bosses, sockets)

    front = _engrave(front, plan, p.label or _auto_label(plan, "front"),
                     t + p.extension_front_mm, outward=+1)
    back = _engrave(back, plan, p.label or _auto_label(plan, "back"),
                    -(t + p.extension_back_mm), outward=-1)

    front, back = front.clean(), back.clean()
    for name, half in (("front", front), ("back", back)):
        solids = half.solids().vals()
        if not solids:
            raise ValueError(f"the {name} half came out empty — the lens swallows it")
        if len(solids) > 1:
            plan.warnings.append(
                f"the {name} half is {len(solids)} disconnected pieces; it will not "
                "print as one part. Reduce the offset or the aperture.")
    return front, back


# ---------------------------------------------------------------------------
# convenience
# ---------------------------------------------------------------------------

def generate(lens: Lens, pose: Pose, out_dir: str | Path = "generated",
             cube: CubeInterface | None = None,
             params: CartridgeParams | None = None,
             stem: str = "lens_cartridge",
             stl: bool = True, diagram: bool = True) -> CartridgePlan:
    """Plan, build and write front/back STEP (+STL), the plan JSON and a
    schematic layout diagram."""
    plan = plan_cartridge(lens, pose, cube, params)
    front, back = build_cartridge(plan)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, half in (("front", front), ("back", back)):
        cq.exporters.export(half, str(out / f"{stem}_{name}.step"))
        if stl:
            cq.exporters.export(half, str(out / f"{stem}_{name}.stl"), tolerance=0.01)
    (out / f"{stem}_plan.json").write_text(
        json.dumps(plan.report(), indent=2), encoding="utf-8")

    if diagram:
        try:
            try:
                from .cartridge_plot import plot_plan
            except ImportError:
                from cartridge_plot import plot_plan
            plot_plan(plan, out / f"{stem}_layout.png")
        except Exception as exc:            # matplotlib is optional
            plan.warnings.append(f"layout diagram skipped ({exc.__class__.__name__})")
    return plan


def _cli() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the printable round insert pair that holds a lens "
                    "at a given pose inside an openUC2 V4 cube.")
    ap.add_argument("--diameter", type=float, required=True, help="lens Ø in mm")
    ap.add_argument("--thickness", type=float, required=True,
                    help="lens centre thickness in mm")
    ap.add_argument("--r1", type=float, default=float("inf"),
                    help="front surface radius (mm, +ve = centre toward +Z)")
    ap.add_argument("--r2", type=float, default=float("inf"),
                    help="back surface radius (mm, -ve for the 2nd biconvex face)")
    ap.add_argument("--reference", default="center",
                    choices=["center", "front_vertex", "back_vertex"])
    ap.add_argument("-x", type=float, default=0.0, help="target x from cube centre")
    ap.add_argument("-y", type=float, default=0.0, help="target y from cube centre")
    ap.add_argument("-z", type=float, default=0.0, help="target z from cube centre")
    ap.add_argument("--rx", type=float, default=0.0)
    ap.add_argument("--ry", type=float, default=0.0)
    ap.add_argument("--rz", type=float, default=0.0)
    ap.add_argument("--aperture", type=float, default=None, help="clear aperture Ø")
    ap.add_argument("--clearance", type=float, default=0.15)
    ap.add_argument("--extension-front", type=float, default=0.0)
    ap.add_argument("--extension-back", type=float, default=0.0)
    ap.add_argument("--no-snap", action="store_true",
                    help="smooth master insert: place the joint exactly on z")
    ap.add_argument("--no-pins", action="store_true")
    ap.add_argument("--label", default=None,
                    help="text engraved on both outward faces (default: auto)")
    ap.add_argument("--no-diagram", action="store_true")
    ap.add_argument("--out-dir", default="generated")
    ap.add_argument("--stem", default="lens_cartridge")
    args = ap.parse_args()

    lens = Lens(diameter_mm=args.diameter, center_thickness_mm=args.thickness,
                r1_mm=args.r1, r2_mm=args.r2, reference=args.reference)
    pose = Pose(x_mm=args.x, y_mm=args.y, z_mm=args.z,
                rx_deg=args.rx, ry_deg=args.ry, rz_deg=args.rz)
    params = CartridgeParams(
        clear_aperture_mm=args.aperture,
        fit_clearance_mm=args.clearance,
        extension_front_mm=args.extension_front,
        extension_back_mm=args.extension_back,
        snap_to_notch=not args.no_snap,
        alignment_pins=0 if args.no_pins else 2,
        label=args.label,
    )
    plan = generate(lens, pose, args.out_dir, params=params, stem=args.stem,
                    diagram=not args.no_diagram)
    print(json.dumps(plan.report(), indent=2))


if __name__ == "__main__":
    _cli()
