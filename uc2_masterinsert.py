# uc2_nose_conic_insert_rotated_noses.py
# CadQuery generator for a conic disk insert with patterned "noses" on the conic edge.
#
# This version keeps your original core idea (base frustum + repeated local revolved features),
# but changes the nose orientation:
# - the nose revolution axis is rotated by 90 degrees compared to the old torus version
# - axis is tangent to the disk circumference (local tangential direction)
# - nose is positioned relative to the conic edge (82 degree side)
#
# Important:
# - Use NOSE_COUNT = 6 or 8 depending on your insert variant.
# - Avoids .clean() during booleans because OCC can stall.
# - Uses incremental union with glue=True for better robustness.
#
# Optical axis = Z through (0,0)
# Units = mm

from __future__ import annotations
import math
import cadquery as cq


# ============================================================
# Explicit parameters
# ============================================================

# Output
OUT_STEP = "uc2_nose_conic_insert.step"
OUT_STL = "uc2_nose_conic_insert.stl"

# Main conic disk
THICKNESS = 4.0
SIDE_ANGLE_TO_FACE_DEG = 82.0  # angle between top face and conic side wall

# Base and nose radii (from your drawing)
R_BASE_EDGE_MID = 19.18   # minimum radius of cone edge (without nose), at z=0
R_NOSE_MAX_MID  = 20.05   # max radius with nose, roughly at z=0

# Pattern count (set to 6 or 8)
NOSE_COUNT = 6
# NOSE_COUNT = 8

# Nose geometry (from sketch, parametric)
NOSE_TUBE_DIAMETER = 1.60
NOSE_TUBE_R = NOSE_TUBE_DIAMETER / 2.0

# "Major radius" of the torus (distance from local torus axis to tube center)
# In your sketch this looks around 0.5 mm, keep explicit/tunable.
NOSE_MAJOR_R = 0.50

# Placement of nose center relative to conic edge point in the radial-z section
# local basis:
#   u_side   = along cone side (in radial-z plane)
#   u_normal = perpendicular to cone side (in radial-z plane, roughly outward)
#
# These are the key parameters to tune to match the sketch exactly.
NOSE_CENTER_OFFSET_ALONG_SIDE = 0.00   # mm
NOSE_CENTER_OFFSET_NORMAL     = 0.30   # mm (your sketch shows ~0.3)
NOSE_BOOL_OVERLAP             = 0.08   # mm inward overlap into cone for robust union

# Nose reference z position on the cone edge
NOSE_Z0 = 0.0  # mm (mid-plane of disk)

# Optional radial fine tuning (if you want to hit 20.05 exactly)
# Positive = shift nose outward radially, negative = inward
NOSE_RADIAL_FINE_SHIFT = 0.00

# Optional clipping around the rim (can be disabled while debugging)
ENABLE_RIM_TRIM = False
TRIM_RADIAL_INNER_MARGIN = 1.2
TRIM_RADIAL_OUTER_MARGIN = 1.0
TRIM_Z_EXTRA = 1.0

# Fillets
FILLET_BASE_VERTICAL_EDGES = 0.12   # small, robust
ENABLE_FINAL_FILLET = False         # set True later
FILLET_FINAL = 0.08                 # small global fillet after unions

# Final clean
DO_FINAL_CLEAN = False

# STL tessellation
STL_LINEAR_TOL = 0.03
STL_ANGULAR_TOL_DEG = 3.0


# ============================================================
# Derived geometry
# ============================================================

NOSE_STEP_DEG = 360.0 / NOSE_COUNT

# Frustum top and bottom radii from angle + thickness
DR_HALF = (THICKNESS / 2.0) / math.tan(math.radians(SIDE_ANGLE_TO_FACE_DEG))
R_TOP = R_BASE_EDGE_MID - DR_HALF
R_BOT = R_BASE_EDGE_MID + DR_HALF


# ============================================================
# Robust helpers
# ============================================================

def safe_fillet(wp: cq.Workplane, radius: float, selector: str = "", attempts: int = 8) -> cq.Workplane:
    if radius <= 0:
        return wp
    r = float(radius)
    for _ in range(attempts):
        try:
            sel = wp.edges(selector) if selector else wp.edges()
            if len(sel.vals()) == 0:
                return wp
            return sel.fillet(r)
        except Exception:
            r *= 0.65
    return wp


def export_part(part: cq.Workplane) -> None:
    cq.exporters.export(part, OUT_STEP)
    cq.exporters.export(
        part,
        OUT_STL,
        tolerance=STL_LINEAR_TOL,
        angularTolerance=math.radians(max(0.1, STL_ANGULAR_TOL_DEG)),
    )


# ============================================================
# Base conic disk
# ============================================================

def build_conic_disk() -> cq.Workplane:
    # Frustum centered around Z=0
    disk = (
        cq.Workplane("XY")
        .workplane(offset=-THICKNESS / 2.0)
        .circle(R_BOT)
        .workplane(offset=THICKNESS)
        .circle(R_TOP)
        .loft(combine=True)
    )

    # Small fillet on vertical-ish seam edges only (if any)
    if FILLET_BASE_VERTICAL_EDGES > 0:
        disk = safe_fillet(disk, FILLET_BASE_VERTICAL_EDGES, selector="|Z", attempts=8)

    return disk


# ============================================================
# Nose geometry (rotated torus)
# ============================================================

def make_torus_axis_z(major_r: float, tube_r: float) -> cq.Solid:
    """
    Build a torus around local Z axis at origin.
    """
    wp = (
        cq.Workplane("XZ")
        .center(major_r, 0.0)
        .circle(tube_r)
        .revolve(angleDegrees=360, axisStart=(0, 0, 0), axisEnd=(0, 0, 1))
    )
    return wp.val()


def cone_local_basis_at_plus_x() -> tuple[cq.Vector, cq.Vector]:
    """
    Local basis in XZ plane at azimuth 0 (+X side):
    - u_side: along conic edge line (upwards, slightly inward)
    - u_normal: perpendicular to cone side in XZ plane (roughly outward)
    """
    a = math.radians(SIDE_ANGLE_TO_FACE_DEG)
    # Cone side goes upward and inward on +X side
    u_side = cq.Vector(-math.cos(a), 0.0, math.sin(a)).normalized()
    # Perpendicular in XZ plane
    u_normal = cq.Vector(math.sin(a), 0.0, math.cos(a)).normalized()
    return u_side, u_normal


def cone_edge_radius_at_z(z: float) -> float:
    """
    Cone edge radius (without nose) at height z.
    z=0 -> R_BASE_EDGE_MID
    Positive z -> smaller radius (top)
    """
    return R_BASE_EDGE_MID - z / math.tan(math.radians(SIDE_ANGLE_TO_FACE_DEG))


def build_one_rotated_nose() -> cq.Solid:
    """
    One nose at azimuth 0 (+X side), with torus axis rotated 90 degrees
    so the torus axis is tangential to the disk (parallel to Y at azimuth 0).
    """
    # Start with torus axis = Z
    tor = make_torus_axis_z(NOSE_MAJOR_R, NOSE_TUBE_R)

    # Rotate torus axis Z -> Y (90 degree rotation about X)
    # This is the key change compared to your old code.
    tor = tor.rotate((0, 0, 0), (1, 0, 0), 90.0)

    # Reference point on conic edge at z = NOSE_Z0
    r_edge = cone_edge_radius_at_z(NOSE_Z0)
    p_edge = cq.Vector(r_edge, 0.0, NOSE_Z0)

    # Local placement basis in radial-z section
    u_side, u_normal = cone_local_basis_at_plus_x()

    # Place the torus axis center relative to cone edge
    # Move slightly inward for overlap (robust union)
    p_center = (
        p_edge
        + u_side * NOSE_CENTER_OFFSET_ALONG_SIDE
        + u_normal * (NOSE_CENTER_OFFSET_NORMAL - NOSE_BOOL_OVERLAP)
        + cq.Vector(NOSE_RADIAL_FINE_SHIFT, 0.0, 0.0)
    )

    tor = tor.translate((p_center.x, p_center.y, p_center.z))
    return tor


def build_rim_trim_body() -> cq.Workplane:
    """
    Optional annular trim body around the rim to clip oversized torus parts.
    Disable while debugging booleans.
    """
    r_inner = R_BASE_EDGE_MID - TRIM_RADIAL_INNER_MARGIN
    r_outer = R_NOSE_MAX_MID + TRIM_RADIAL_OUTER_MARGIN
    h = THICKNESS + 2.0 * TRIM_Z_EXTRA

    outer = cq.Workplane("XY").circle(r_outer).extrude(h, both=True)
    inner = cq.Workplane("XY").circle(r_inner).extrude(h, both=True)
    annulus = outer.cut(inner)
    return annulus


def build_nose_solids() -> list[cq.Solid]:
    """
    Pattern the rotated nose around Z.
    """
    one = build_one_rotated_nose()
    nose_solids: list[cq.Solid] = []

    trim = build_rim_trim_body() if ENABLE_RIM_TRIM else None

    for k in range(NOSE_COUNT):
        ang = k * NOSE_STEP_DEG
        nk = one.rotate((0, 0, 0), (0, 0, 1), ang)

        if trim is not None:
            try:
                nk_wp = cq.Workplane("XY").add(nk).intersect(trim)
                vals = nk_wp.solids().vals()
                nk = vals[0] if vals else nk_wp.val()
            except Exception:
                pass

        nose_solids.append(nk)

    return nose_solids


# ============================================================
# Robust incremental union (instead of base_solid.fuse(s))
# ============================================================

def union_incremental(base: cq.Workplane, solids: list[cq.Solid]) -> cq.Workplane:
    """
    Workplane.union(..., glue=True, clean=False) is often more stable than direct Solid.fuse.
    """
    part = base

    for i, s in enumerate(solids):
        print(f"Union nose {i+1}/{len(solids)}")
        nose_wp = cq.Workplane("XY").add(s)
        # glue=True helps when solids overlap/touch slightly
        part = part.union(nose_wp, clean=False, glue=True)

    return part


# ============================================================
# Build final part
# ============================================================

def build_part() -> cq.Workplane:
    base = build_conic_disk()

    noses = build_nose_solids()
    part = union_incremental(base, noses)

    # Optional small final fillet
    if ENABLE_FINAL_FILLET and FILLET_FINAL > 0:
        part = safe_fillet(part, FILLET_FINAL, selector="", attempts=6)

    if DO_FINAL_CLEAN:
        try:
            part = part.clean()
        except Exception:
            pass

    return part


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("Building conic insert with rotated noses")
    print(f"NOSE_COUNT = {NOSE_COUNT}")
    print(f"R_TOP = {R_TOP:.3f} mm")
    print(f"R_BOT = {R_BOT:.3f} mm")

    p = build_part()
    export_part(p)

    print(f"Exported: {OUT_STEP}")
    print(f"Exported: {OUT_STL}")