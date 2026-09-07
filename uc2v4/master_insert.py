"""openUC2 V4 master insert (MAS - 2003 lineage).

``build_master_insert()`` reproduces both released parts, verified against
their STEPs by ``tools/validate_master_inserts.py``:

- the default (``corner_rib=False``) is PRT - 2100 - MASINS - V04, the
  *sliding* insert: smooth ledges, held by friction;
- ``corner_rib=True`` is PRT - 2123 - MASLCK - V04 ("Master lock"): the raised
  rib on the ±X ledges drops into one of the cube's notches, so the insert
  sits at a repeatable 5 mm position.

Either is a 4 mm plate on the square-insert interface with

- a conic center opening, wall angle 82 deg to the plate face
  (Ø40.0 at the bottom face, Ø38.876 at the top face, InsertDiam = 40),
  chamfered 0.2 mm on both circular edges;
- 8 nose grooves ("notches") around the cone wall every 45 deg
  (offset 22.5 deg): each is the full revolution of the tooth quad around
  its own cone-parallel edge -> a Ø1.6 groove with an R1.3 spherical end
  at the top. The matching base holder (the round insert that carries the
  optics) has the complementary noses, +0.05 mm offset, so it clicks into
  45-deg orientations;
- 2x Ø1.9 thread-forming pilot holes and 2x Ø2.8 clearance holes with
  Ø5.0 x 2.0 head counterbores at (+-21.4, +-13.6): two identical halves
  screwed face-to-face clamp the optic - each screw passes one half's
  clearance hole and bites the other half's pilot.

Everything is exact per the COM extraction of the Inventor master; the only
simplifications are the omitted R0.5 rim fillet around each notch groove and
the corner blend approximation (see interface.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .interface import MasterInsertInterface, base_plate
except ImportError:                     # pragma: no cover
    from interface import MasterInsertInterface, base_plate


@dataclass(frozen=True)
class MasterInsertParams:
    interface: MasterInsertInterface = MasterInsertInterface()
    thickness: float = 4.0                 # HightMasterInsert

    # conic center opening
    insert_diam: float = 40.0              # InsertDiam, at the bottom face
    cone_angle_deg: float = 82.0           # wall-to-face angle
    cone_edge_chamfer: float = 0.2

    # notch grooves (the 45-deg indexing)
    notch_count: int = 8
    notch_phase_deg: float = 22.5
    notch_radius: float = 0.8              # groove cylinder radius
    notch_sphere_radius: float = 1.3       # spherical groove end (top)
    notch_axis_offset: float = 0.3         # groove axis inset, perp. to wall
    notches: bool = True

    # sandwich screw holes
    hole_positions: tuple = ((21.4, 13.6), (-21.4, -13.6))   # clearance pair
    pilot_positions: tuple = ((-21.4, 13.6), (21.4, -13.6))  # pilot pair
    clearance_diam: float = 2.8
    cbore_diam: float = 5.0
    cbore_depth: float = 2.0
    pilot_diam: float = 1.9
    pilot_depth_from_top: float = 3.5      # then a 45 deg relief cone breaks
    holes: bool = True                     # through the bottom face

    # corner-ledge rib: the LOCKING feature (PRT-2123 MASLCK) — a raised
    # tongue at mid-height on the four +-X-side corner ledges that drops into
    # the cube track's notches (measured: crest at shoulder+0.8586, flat over
    # z +-0.1414, 45 deg flanks down to the ledge at z +-1.0, plan end rounded
    # r0.5 just before the side face). Off = the sliding PRT-2100 MASINS.
    corner_rib: bool = False
    rib_height: float = 0.8586
    rib_flat_half_z: float = 0.1414
    rib_flank_end_z: float = 1.0

    def with_grid(self, grid: float) -> "MasterInsertParams":
        return replace(self, interface=replace(self.interface, grid=grid))


def _cone_cut(params: MasterInsertParams) -> cq.Workplane:
    """Revolved cut of the conic opening incl. its 0.2 rim chamfers.

    The chamfers are equal-leg (0.2 mm along the face and 0.2 mm along the
    82 deg wall), matching the measured section: wall point
    (19.9722, -1.8019) / face point (20.2, -2.0) for InsertDiam 40, t=4.
    """
    t2 = params.thickness / 2.0
    r_bot = params.insert_diam / 2.0
    slope = 1.0 / math.tan(math.radians(params.cone_angle_deg))  # dr per dz
    r_top = r_bot - params.thickness * slope
    ch = params.cone_edge_chamfer
    # unit vector along the wall, pointing down (+r, -z as z decreases)
    norm = math.hypot(slope, 1.0)
    wall_dr, wall_dz = slope / norm, -1.0 / norm
    profile = [
        (0.0, t2),
        (r_top + ch, t2),
        (r_top + wall_dr * ch, t2 + wall_dz * ch),
        (r_bot - wall_dr * ch, -t2 - wall_dz * ch),
        (r_bot + ch, -t2),
        (0.0, -t2),
    ]
    wp = cq.Workplane("XZ").moveTo(*profile[0])
    for p in profile[1:]:
        wp = wp.lineTo(*p)
    wp = wp.close()
    return wp.revolve(360.0, (0, 0, 0), (0, 1, 0))


def _notch_tools(params: MasterInsertParams):
    """One groove = tilted cylinder + sphere, instanced at each azimuth.

    In the (r, z) half plane the groove axis runs from
    A = (19.7127, -2.1113) to B = (19.1349, 2.0) - parallel to the 82 deg
    cone wall, inset 0.3 mm perpendicular to it (MAS-2003 'Sketch Side
    view', dims d689/d694/d695). B sits at the top face; A continues
    0.1113 mm below the bottom face.
    """
    t2 = params.thickness / 2.0
    r_bot = params.insert_diam / 2.0
    slope = 1.0 / math.tan(math.radians(params.cone_angle_deg))  # dr per dz
    # radial shift equivalent of the perpendicular axis inset
    rad_shift = params.notch_axis_offset * math.hypot(1.0, slope)

    over = 0.1113  # measured overshoot of the quad beyond the faces
    z_a, z_b = -t2 - over, t2
    r_a = r_bot - (z_a + t2) * slope - rad_shift
    r_b = r_bot - (z_b + t2) * slope - rad_shift

    tools = []
    for k in range(params.notch_count):
        az = math.radians(params.notch_phase_deg + k * 360.0 / params.notch_count)
        u = (math.cos(az), math.sin(az))
        a3 = cq.Vector(r_a * u[0], r_a * u[1], z_a)
        b3 = cq.Vector(r_b * u[0], r_b * u[1], z_b)
        axis = (b3 - a3)
        length = axis.Length
        dirv = axis.multiply(1.0 / length)
        # extend below A a little for a clean boolean
        base = a3 - dirv.multiply(0.5)
        cyl = cq.Solid.makeCylinder(params.notch_radius, length + 0.5,
                                    pnt=base, dir=dirv)
        sph = cq.Solid.makeSphere(params.notch_sphere_radius, pnt=b3,
                                  angleDegrees1=-90, angleDegrees2=90)
        tools.append(cyl)
        tools.append(sph)
    return tools


def _hole_tools(params: MasterInsertParams):
    t2 = params.thickness / 2.0
    tools = []
    for (x, y) in params.hole_positions:
        tools.append(cq.Solid.makeCylinder(
            params.clearance_diam / 2.0, params.thickness + 0.2,
            pnt=cq.Vector(x, y, -t2 - 0.1), dir=cq.Vector(0, 0, 1)))
        tools.append(cq.Solid.makeCylinder(
            params.cbore_diam / 2.0, params.cbore_depth + 0.1,
            pnt=cq.Vector(x, y, t2 - params.cbore_depth),
            dir=cq.Vector(0, 0, 1)))
    for (x, y) in params.pilot_positions:
        r = params.pilot_diam / 2.0
        z_end = t2 - params.pilot_depth_from_top   # cylinder ends here
        tools.append(cq.Solid.makeCylinder(
            r, params.pilot_depth_from_top + 0.1,
            pnt=cq.Vector(x, y, z_end), dir=cq.Vector(0, 0, 1)))
        # 45 deg drill relief widening to the bottom face and through it
        depth = (z_end + t2) + 0.1
        tools.append(cq.Solid.makeCone(
            r + depth, r, depth,
            pnt=cq.Vector(x, y, z_end - depth), dir=cq.Vector(0, 0, 1)))
    return tools


def _corner_rib_tools(params: MasterInsertParams):
    """Raised rib on each +-X corner ledge (union tools).

    The rib = (flank prism along X) intersect (plan prism along Z). Both
    prisms extend a margin into existing material, so the union needs no
    clipping: where the plate is already solid nothing changes, and the
    45 deg corner flat bounds the rib's inner end automatically.
    """
    iface = params.interface
    e = iface.edge_half
    w = iface.shoulder_half
    crest = w + params.rib_height
    fh = params.rib_flat_half_z
    fe = params.rib_flank_end_z
    m = 0.4  # margin into the material

    # (y, z) cross-section: 45 deg flanks from the ledge to the flat crest
    prof = [
        (w - m, fe + m),
        (crest, fh),
        (crest, -fh),
        (w - m, -fe - m),
    ]
    x0, x1 = w + 1.0, e + 0.5
    wp = cq.Workplane("YZ").workplane(offset=x0).moveTo(*prof[0])
    for pt in prof[1:]:
        wp = wp.lineTo(*pt)
    flank = wp.close().extrude(x1 - x0).val()

    # plan shape (x, y): rib band ending in the measured r0.5 round + blend
    plan = (
        cq.Workplane("XY")
        .moveTo(x0 - 0.5, w - m)
        .lineTo(x0 - 0.5, crest)
        .lineTo(e - 0.5, crest)
        .threePointArc((e - 0.5 + 0.5 * math.cos(math.radians(45)),
                        crest - 0.5 + 0.5 * math.sin(math.radians(45))),
                       (e - 0.0258, w + 0.5172))
        .lineTo(e, w + 0.2929)
        .lineTo(e, w - m)
        .close()
        .extrude(params.thickness / 2.0 + 0.5, both=True)
        .val()
    )
    tool = flank.intersect(plan)

    tools = [tool]
    tools.append(tool.mirror("XZ"))                      # +X / -Y corner
    tools += [t.mirror("YZ") for t in tools]             # -X side
    return tools


def build_master_insert(params: MasterInsertParams | None = None) -> cq.Workplane:
    p = params or MasterInsertParams()
    part = base_plate(p.interface, p.thickness)
    if p.corner_rib:
        for tool in _corner_rib_tools(p):
            part = part.union(cq.Workplane("XY").add(tool))
    part = part.cut(_cone_cut(p))
    if p.notches:
        for tool in _notch_tools(p):
            part = part.cut(cq.Workplane("XY").add(tool))
    if p.holes:
        for tool in _hole_tools(p):
            part = part.cut(cq.Workplane("XY").add(tool))
    return part.clean()


if __name__ == "__main__":
    part = build_master_insert()
    cq.exporters.export(part, "uc2v4_master_insert.stl")
    print("exported uc2v4_master_insert.step")
