"""openUC2 V4 round holder — the "base holder" interface and parts built on it.

The base holder is the round carrier that clicks into the master insert
(uc2v4/master_insert.py): a conic disk whose wall matches the master
insert's 82 deg opening, carrying 8 noses that are the exact positives of
the master insert's grooves. Every round optic module (MASINS* / mirror
holders / laser holders) is this disk plus its own pocketing, so the disk
lives here as a reusable blank.

``build_mirror_holder()`` with default parameters reproduces
PRT - 2111 - MASINSMIRHOLUPP - C ("Insert for mirror holder"): the blank
plus an obround beam aperture and two counterbored sandwich screw holes.

Extraction sources (COM dumps in ../extracted/):
- ``MAS - 2003 - Master Insert - B.ipt`` body *Base holder* — the disk and
  nose recipe (Revolution11 + Fillet35/37 + Circular Pattern20, and
  ``OffsetDiameterBaseHolder``, which is a 0.05 mm *face* offset, hence
  0.050491 mm radially on the 82 deg wall);
- ``MAS - 2007 - Kinem + fixed mirror 45 + 90 - C.ipt`` — derives that base
  holder, adds the 0.4 mm skirt and the mirror features. Its fixed-mirror
  branch is rolled back in the master, so the released part's b-rep is the
  authority for the aperture and hole positions.

Coordinates: optical axis = Z through (0, 0); units mm. The interface band
(the 4 mm the master insert grips) is centered on ``interface_mid_z``, which
defaults to 15.0 so the output lands on the released part's own datum. Set
it to 0.0 for a part centered on the mid-plane like the other uc2v4 models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import cadquery as cq


# ---------------------------------------------------------------------------
# the base-holder interface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseHolderInterface:
    """The round disk that mates the master insert's conic opening.

    Defaults are the MAS-2003 base holder: Ø40 nominal cone at 82 deg to the
    face, 4 mm tall, 8 noses on 45 deg indexing.
    """

    insert_diam: float = 40.0        # InsertDiam — the master insert's cone
    wall_offset: float = 0.05        # OffsetDiameterBaseHolder (face offset)
    cone_angle_deg: float = 82.0     # wall-to-face angle, as in the master
    thickness: float = 4.0           # the band the master insert grips
    interface_mid_z: float = 15.0    # z of the band's mid-plane

    top_fillet: float = 0.35         # blend from the cone to the top face
    skirt: float = 0.4               # plate continuing below the band
    bottom_chamfer: float = 0.4      # OuterChamfer, eats the skirt's edge

    # noses (positives of the master insert's grooves — same axis line)
    nose_count: int = 8
    nose_phase_deg: float = 22.5
    nose_radius: float = 0.8         # the groove/nose cylinder
    nose_axis_offset: float = 0.3    # axis inset perpendicular to the wall
    nose_cap_radius: float = 1.0     # revolved cap circle at the nose tip
    nose_cap_eccentricity: float = 0.1   # its center's offset from the axis
    nose_cap_setback: float = 0.3    # cap center below the band's top plane
    nose_fillet: float = 0.2         # blend where the cap meets the cylinder
    noses: bool = True

    @property
    def half_angle_rad(self) -> float:
        """Cone half angle measured from the Z axis (8 deg for an 82 deg wall)."""
        return math.radians(90.0 - self.cone_angle_deg)

    @property
    def z_band_bottom(self) -> float:
        return self.interface_mid_z - self.thickness / 2.0

    @property
    def z_band_top(self) -> float:
        return self.interface_mid_z + self.thickness / 2.0

    @property
    def z_bottom(self) -> float:
        return self.z_band_bottom - self.skirt

    @property
    def max_radius(self) -> float:
        """Widest radius, at the band's bottom plane."""
        return self.insert_diam / 2.0 + self.wall_offset / math.cos(self.half_angle_rad)

    def cone_radius_at(self, z: float) -> float:
        return self.max_radius - (z - self.z_band_bottom) * math.tan(self.half_angle_rad)

    @property
    def top_face_radius(self) -> float:
        """Radius of the top face, i.e. the top fillet's center radius."""
        a, fr = self.half_angle_rad, self.top_fillet
        return self.cone_radius_at(self.z_band_top - fr) - fr / math.cos(a)


def _arc_mid(start, end, center, radius):
    """Midpoint of the minor arc start->end on the circle (center, radius)."""
    v1 = ((start[0] - center[0]) / radius, (start[1] - center[1]) / radius)
    v2 = ((end[0] - center[0]) / radius, (end[1] - center[1]) / radius)
    bx, by = v1[0] + v2[0], v1[1] + v2[1]
    n = math.hypot(bx, by)
    return (center[0] + radius * bx / n, center[1] + radius * by / n)


def disk_blank(iface: BaseHolderInterface) -> cq.Workplane:
    """The conic disk without noses, as a revolve of its exact (r, z) profile.

    When ``skirt`` exceeds ``bottom_chamfer`` the extra length becomes a
    straight cylindrical run at ``max_radius`` below the band — that is how a
    holder gains axial room without disturbing the mating cone.
    """
    a, fr = iface.half_angle_rad, iface.top_fillet
    cz = iface.z_band_top - fr
    cr = iface.top_face_radius
    tangent = (cr + fr * math.cos(a), cz + fr * math.sin(a))
    top = (cr, iface.z_band_top)
    ch = min(iface.bottom_chamfer, iface.skirt)

    wp = cq.Workplane("XZ").moveTo(0.0, iface.z_bottom)
    if ch > 1e-9:
        wp = (wp.lineTo(iface.max_radius - ch, iface.z_bottom)
                .lineTo(iface.max_radius, iface.z_bottom + ch))   # bottom chamfer
    else:                                                          # flush face
        wp = wp.lineTo(iface.max_radius, iface.z_bottom)
    if iface.z_band_bottom - (iface.z_bottom + ch) > 1e-9:   # straight extension
        wp = wp.lineTo(iface.max_radius, iface.z_band_bottom)
    wp = (
        wp.lineTo(*tangent)                                  # the 82 deg wall
        .threePointArc(_arc_mid(tangent, top, (cr, cz), fr), top)
        .lineTo(0.0, iface.z_band_top)
        .close()
    )
    return wp.revolve(360.0, (0, 0, 0), (0, 1, 0))


def nose_axis(iface: BaseHolderInterface):
    """The nose/groove axis in the (r, z) half plane: (A, B, unit, normal).

    Identical to the master insert's groove axis (master_insert._notch_tools):
    parallel to the wall, inset ``nose_axis_offset`` perpendicular to it. The
    bottom end A is placed so the nose's tilted flat end is tangent to the
    band's bottom plane, which is what makes the groove bottom out cleanly.
    """
    a = iface.half_angle_rad
    rad_shift = iface.nose_axis_offset / math.cos(a)
    over = iface.nose_radius * math.sin(a)

    z_a = iface.z_band_bottom - over
    z_b = iface.z_band_top
    r_a = iface.cone_radius_at(z_a) - rad_shift
    r_b = iface.cone_radius_at(z_b) - rad_shift

    length = math.hypot(r_b - r_a, z_b - z_a)
    unit = ((r_b - r_a) / length, (z_b - z_a) / length)
    normal = (unit[1], -unit[0])          # points to larger r
    return (r_a, z_a), (r_b, z_b), unit, normal, length


def _nose_solid(iface: BaseHolderInterface) -> cq.Solid:
    """One nose at azimuth 0, as a single revolve about its own axis.

    Building the cylinder, the cap and the blend between them as one profile
    revolved about the nose axis avoids a boolean + fillet on a tangent
    junction, which OCC handles poorly. The profile lives in (d, t): d =
    distance from the nose axis, t = distance along it from A.
    """
    A, _B, unit, normal, length = nose_axis(iface)
    rn = iface.nose_radius
    cap_r = iface.nose_cap_radius
    ecc = iface.nose_cap_eccentricity
    fr = iface.nose_fillet

    t_cap = length - iface.nose_cap_setback          # cap center along the axis
    # Concave blend of radius fr between the cylinder d = rn and the cap
    # circle: its center sits at d = rn + fr and at cap distance cap_r + fr.
    dd = (rn + fr) - ecc
    dt = math.sqrt(max((cap_r + fr) ** 2 - dd * dd, 0.0))
    f_center = (rn + fr, t_cap - dt)
    p_cyl = (rn, f_center[1])                        # tangency on the cylinder
    # tangency on the cap: along cap-center -> fillet-center, at cap_r
    ux, ut = (f_center[0] - ecc) / (cap_r + fr), (f_center[1] - t_cap) / (cap_r + fr)
    p_cap = (ecc + cap_r * ux, t_cap + cap_r * ut)
    t_axis = t_cap + math.sqrt(max(cap_r * cap_r - ecc * ecc, 0.0))   # cap meets axis

    def to_rz(d, t):
        return (A[0] + unit[0] * t + normal[0] * d,
                A[1] + unit[1] * t + normal[1] * d)

    # Both runs are minor arcs, so the plain midpoint is the right side: the
    # blend hugs the axis side of its circle, the cap bows over its widest
    # point (d = ecc + cap_r) on the way back to the axis.
    f_mid = _arc_mid(p_cyl, p_cap, f_center, fr)
    cap_mid = _arc_mid(p_cap, (0.0, t_axis), (ecc, t_cap), cap_r)

    wp = (
        cq.Workplane("XZ")
        .moveTo(*to_rz(0.0, 0.0))
        .lineTo(*to_rz(rn, 0.0))                     # flat end at A
        .lineTo(*to_rz(*p_cyl))                      # the Ø1.6 cylinder
        .threePointArc(to_rz(*f_mid), to_rz(*p_cap))  # blend
        .threePointArc(to_rz(*cap_mid), to_rz(0.0, t_axis))  # revolved cap
        .close()
    )
    axis_start = (A[0], A[1], 0.0)
    axis_end = (A[0] + unit[0] * length, A[1] + unit[1] * length, 0.0)
    return wp.revolve(360.0, axis_start, axis_end).val()


def nose_solids(iface: BaseHolderInterface) -> list[cq.Solid]:
    """All noses, trimmed to the interface band and placed at each azimuth."""
    one = _nose_solid(iface)
    box = cq.Solid.makeBox(
        80.0, 80.0, iface.thickness,
        pnt=cq.Vector(-40.0, -40.0, iface.z_band_bottom), dir=cq.Vector(0, 0, 1))
    one = one.intersect(box)
    out = []
    for k in range(iface.nose_count):
        az = iface.nose_phase_deg + k * 360.0 / iface.nose_count
        out.append(one.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), az))
    return out


def build_base_holder(iface: BaseHolderInterface | None = None) -> cq.Workplane:
    """The round holder blank: conic disk + noses, no pocketing."""
    iface = iface or BaseHolderInterface()
    part = disk_blank(iface)
    if iface.noses:
        for nose in nose_solids(iface):
            part = part.union(cq.Workplane("XY").add(nose))
    return part.clean()


# ---------------------------------------------------------------------------
# PRT - 2111 - MASINSMIRHOLUPP: base holder + beam aperture + sandwich screws
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MirrorHolderParams:
    interface: BaseHolderInterface = field(default_factory=BaseHolderInterface)

    # Obround beam aperture: two lobes of aperture_radius at
    # (center_x, +-lobe_offset), bridged by their common tangents. For a 45 deg
    # mirror the beam footprint is an ellipse, so the clear opening is
    # elongated and sits off-axis on the reflected side.
    aperture: bool = True
    aperture_center_x: float = 6.0
    aperture_radius: float = 5.0
    aperture_lobe_offset: float = 2.0
    aperture_chamfer: float = 0.4

    # Sandwich screws: the upper and lower holder halves clamp the mirror.
    holes: bool = True
    hole_positions: tuple = ((-7.2, 13.6), (-7.2, -13.6))
    clearance_diam: float = 2.9
    cbore_diam: float = 5.0
    cbore_depth: float = 2.0

    def with_mid_z(self, z: float) -> "MirrorHolderParams":
        return replace(self, interface=replace(self.interface, interface_mid_z=z))


def _obround_wire(p: MirrorHolderParams, grow: float = 0.0) -> cq.Wire:
    """Aperture outline, optionally grown by *grow* (for the chamfer loft)."""
    cx, r, dy = p.aperture_center_x, p.aperture_radius + grow, p.aperture_lobe_offset
    if dy <= 1e-9:   # degenerate obround = a plain circular bore
        return cq.Workplane("XY").center(cx, 0.0).circle(r).wires().val()
    return (
        cq.Workplane("XY")
        .moveTo(cx - r, -dy)
        .lineTo(cx - r, dy)
        .threePointArc((cx, dy + r), (cx + r, dy))
        .lineTo(cx + r, -dy)
        .threePointArc((cx, -dy - r), (cx - r, -dy))
        .close()
        .wires()
        .val()
    )


def _aperture_cutter(p: MirrorHolderParams) -> cq.Workplane:
    """Through obround with a 45 deg chamfer at each face.

    Built as core prism + two ruled lofts, for the same reason as the square
    inserts' outer chamfer: OCC will not chamfer a line/arc tangent chain.
    """
    iface = p.interface
    ch = p.aperture_chamfer
    z_lo, z_hi = iface.z_bottom, iface.z_band_top
    inner = _obround_wire(p)
    outer = _obround_wire(p, grow=ch)

    def at(w, z):
        return w.moved(cq.Location(cq.Vector(0, 0, z)))

    def prism(wire, z0, z1):
        wp = cq.Workplane("XY").add(wire).toPending().extrude(z1 - z0)
        return wp.translate((0, 0, z0))

    # The chamfer lofts must span exactly `ch` in z so their walls sit at
    # 45 deg; the straight overshoots beyond each face keep the cut clean.
    parts = [
        prism(inner, z_lo + ch, z_hi - ch),
        prism(outer, z_lo - 1.0, z_lo),
        prism(outer, z_hi, z_hi + 1.0),
    ]
    lofts = [
        cq.Solid.makeLoft([at(outer, z_lo), at(inner, z_lo + ch)], ruled=True),
        cq.Solid.makeLoft([at(inner, z_hi - ch), at(outer, z_hi)], ruled=True),
    ]
    cutter = parts[0]
    for extra in parts[1:]:
        cutter = cutter.union(extra)
    for loft in lofts:
        cutter = cutter.union(cq.Workplane("XY").add(loft))
    return cutter


def _hole_cutters(p: MirrorHolderParams) -> list[cq.Solid]:
    iface = p.interface
    z_lo, z_hi = iface.z_bottom, iface.z_band_top
    out = []
    for (x, y) in p.hole_positions:
        out.append(cq.Solid.makeCylinder(
            p.clearance_diam / 2.0, (z_hi - z_lo) + 2.0,
            pnt=cq.Vector(x, y, z_lo - 1.0), dir=cq.Vector(0, 0, 1)))
        out.append(cq.Solid.makeCylinder(
            p.cbore_diam / 2.0, p.cbore_depth + 1.0,
            pnt=cq.Vector(x, y, z_hi - p.cbore_depth), dir=cq.Vector(0, 0, 1)))
    return out


def build_mirror_holder(params: MirrorHolderParams | None = None) -> cq.Workplane:
    p = params or MirrorHolderParams()
    iface = p.interface

    lobe_span = p.aperture_center_x + p.aperture_radius
    if lobe_span > iface.top_face_radius:
        raise ValueError(
            f"aperture reaches r={lobe_span:.2f} mm, past the {iface.top_face_radius:.2f} mm "
            "top face of the holder")

    part = build_base_holder(iface)
    if p.aperture:
        part = part.cut(_aperture_cutter(p))
    if p.holes:
        for tool in _hole_cutters(p):
            part = part.cut(cq.Workplane("XY").add(tool))
    return part.clean()


if __name__ == "__main__":
    holder = build_mirror_holder()
    cq.exporters.export(holder, "uc2v4_mirror_holder.step")
    cq.exporters.export(holder, "uc2v4_mirror_holder.stl", tolerance=0.02)
    print("exported uc2v4_mirror_holder.step")
