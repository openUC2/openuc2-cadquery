# uc2_masterinsert.py
# CadQuery generator for the UC2 master insert – a conic disk with 6 "nose"
# features around the circumference.
#
# Each nose is created by **revolving a 2-D cross-section profile** around the
# disk's symmetry axis (Z) over an arc of NOSE_SWEEP_DEG (98°).  Six such
# noses are spaced evenly at 360°/6 = 60° centre-to-centre, leaving small
# gaps between them.
#
# The nose cross-section is derived from the technical drawing:
#   – Runs along the conic edge in the R-Z half-plane
#   – Total axial span ≈ THICKNESS (4 mm)
#   – Radial bump ≈ R_NOSE_MAX_MID − R_BASE_EDGE_MID
#   – Rounded corners (R 0.25, R 1.3) as annotated
#
# Optical axis = Z through (0,0).  Units = mm.

from __future__ import annotations
import math
import cadquery as cq


# ============================================================
# Explicit parameters
# ============================================================

# Output files
OUT_STEP = "uc2_nose_conic_insert.step"
OUT_STL  = "uc2_nose_conic_insert.stl"

# Main conic disk
THICKNESS = 4.0                     # mm  total disk thickness
SIDE_ANGLE_TO_FACE_DEG = 82.0      # angle between top face and conic sidewall

# Radii (from drawing)
R_BASE_EDGE_MID = 19.18            # mm  cone edge radius at z = 0 (no nose)
R_NOSE_MAX_MID  = 20.05            # mm  max radius with nose bump

# Number of noses and sweep angle per nose
NOSE_COUNT     = 6
NOSE_SWEEP_DEG = 98.0              # each nose is a 98° revolution arc

# Nose profile dimensions (from detailed cross-section sketch)
NOSE_BUMP_HEIGHT  = R_NOSE_MAX_MID - R_BASE_EDGE_MID  # radial protrusion ≈ 0.87 mm
NOSE_FILLET_SMALL = 0.25           # mm  fillet at profile corners (top/bottom)
NOSE_FILLET_LARGE = 1.3            # mm  fillet at the bump crest

# Axial segment lengths of the nose cross-section (from drawing annotations)
NOSE_SEG_BOT  = 0.57              # mm  bottom flat segment (cone-following)
NOSE_SEG_MID  = 2.537             # mm  middle bump segment
NOSE_SEG_TOP  = 0.893             # mm  top flat segment (cone-following)

# How far the nose profile overlaps into the frustum for a robust boolean
NOSE_BOOL_OVERLAP = 0.15           # mm

# Fillets on base frustum
FILLET_BASE_VERTICAL_EDGES = 0.12  # small fillet on any |Z edges of frustum

# Final optional operations
ENABLE_FINAL_FILLET = False
FILLET_FINAL        = 0.08
DO_FINAL_CLEAN      = False

# STL tessellation quality
STL_LINEAR_TOL      = 0.03
STL_ANGULAR_TOL_DEG = 3.0


# ============================================================
# Derived geometry
# ============================================================

NOSE_SPACING_DEG = 360.0 / NOSE_COUNT   # 60° centre-to-centre

# Frustum top and bottom radii from angle + thickness
DR_HALF = (THICKNESS / 2.0) / math.tan(math.radians(SIDE_ANGLE_TO_FACE_DEG))
R_TOP   = R_BASE_EDGE_MID - DR_HALF     # radius at z = +THICKNESS/2
R_BOT   = R_BASE_EDGE_MID + DR_HALF     # radius at z = -THICKNESS/2


# ============================================================
# Robust helpers
# ============================================================

def safe_fillet(wp: cq.Workplane, radius: float,
               selector: str = "", attempts: int = 8) -> cq.Workplane:
    """Try to fillet edges; shrink radius on failure."""
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
    """Write STEP and STL output files."""
    cq.exporters.export(part, OUT_STEP)
    cq.exporters.export(
        part,
        OUT_STL,
        tolerance=STL_LINEAR_TOL,
        angularTolerance=math.radians(max(0.1, STL_ANGULAR_TOL_DEG)),
    )


# ============================================================
# Base conic disk (frustum)
# ============================================================

def build_conic_disk() -> cq.Workplane:
    """Build a truncated cone (frustum) centred on Z = 0."""
    disk = (
        cq.Workplane("XY")
        .workplane(offset=-THICKNESS / 2.0)
        .circle(R_BOT)
        .workplane(offset=THICKNESS)
        .circle(R_TOP)
        .loft(combine=True)
    )
    if FILLET_BASE_VERTICAL_EDGES > 0:
        disk = safe_fillet(disk, FILLET_BASE_VERTICAL_EDGES,
                           selector="|Z", attempts=8)
    return disk


# ============================================================
# Nose profile & revolution
# ============================================================

def _cone_radius_at_z(z: float) -> float:
    """Cone edge radius (without nose) at height z.  z = 0 → R_BASE_EDGE_MID."""
    return R_BASE_EDGE_MID - z / math.tan(math.radians(SIDE_ANGLE_TO_FACE_DEG))


def _build_nose_profile_wire() -> cq.Wire:
    """
    Build the 2-D closed profile of one nose in the R-Z half-plane.

    The profile sits radially outside the cone surface and will be revolved
    around the Z axis.  It is drawn on the CadQuery "XZ" workplane where
    X = radial distance from Z-axis, Z = axial height.

    From the technical drawing the cross-section has three axial segments:
      1) NOSE_SEG_BOT  (0.57 mm) – follows the cone surface at the bottom
      2) NOSE_SEG_MID  (2.537 mm) – bump region protruding outward
      3) NOSE_SEG_TOP  (0.893 mm) – follows the cone surface at the top

    The bump rises NOSE_BUMP_HEIGHT above the cone surface.
    Transitions are filleted with NOSE_FILLET_SMALL (0.25 mm) and
    NOSE_FILLET_LARGE (1.3 mm).
    """
    half_t  = THICKNESS / 2.0
    overlap = NOSE_BOOL_OVERLAP
    bump_h  = NOSE_BUMP_HEIGHT  # radial protrusion (exact, no overlap added)

    # Cone slope: dR/dZ  (positive Z → smaller R)
    tan_a = math.tan(math.radians(SIDE_ANGLE_TO_FACE_DEG))

    # Key Z positions along the profile (bottom = -half_t, top = +half_t)
    z_bot       = -half_t                             # -2.0
    z_bump_bot  = z_bot + NOSE_SEG_BOT                # -1.43
    z_bump_top  = z_bump_bot + NOSE_SEG_MID           # +1.107
    z_top       = +half_t                             # +2.0

    # Corresponding cone-surface radii at those Z positions
    r_bot      = _cone_radius_at_z(z_bot)
    r_bump_bot = _cone_radius_at_z(z_bump_bot)
    r_bump_top = _cone_radius_at_z(z_bump_top)
    r_top      = _cone_radius_at_z(z_top)

    # Inner edge (overlap into cone body for robust boolean)
    r_bot_inner = r_bot - overlap
    r_top_inner = r_top - overlap

    # Outer (bump) radii – constant at R_NOSE_MAX_MID (cylindrical outer surface)
    r_bump_bot_outer = R_NOSE_MAX_MID
    r_bump_top_outer = R_NOSE_MAX_MID

    # Build closed profile clockwise in (R, Z):
    #   inner-bottom → inner-top → outer-top-cone → outer-bump-top →
    #   outer-bump-bottom → outer-bottom-cone → close
    profile = (
        cq.Workplane("XZ")
        .moveTo(r_bot_inner, z_bot)
        # Inner edge (follows cone line, shifted inward by overlap)
        .lineTo(r_top_inner, z_top)
        # Across top face to cone outer surface
        .lineTo(r_top, z_top)
        # Down along cone surface to bump-top transition
        .lineTo(r_bump_top, z_bump_top)
        # Transition outward to bump (upper shoulder)
        .lineTo(r_bump_top_outer, z_bump_top)
        # Along the bump crest (at peak radius)
        .lineTo(r_bump_bot_outer, z_bump_bot)
        # Transition inward from bump (lower shoulder)
        .lineTo(r_bump_bot, z_bump_bot)
        # Down along cone surface to bottom
        .lineTo(r_bot, z_bot)
        # Close back to start
        .close()
    )

    return profile


def build_one_nose_solid() -> cq.Solid:
    """
    Revolve the nose profile around the global Z axis by NOSE_SWEEP_DEG.

    The profile is drawn on the CadQuery "XZ" workplane where:
      local X = global X (radial direction)
      local Y = global Z (axial direction)

    To revolve around global Z we use axisEnd=(0, 1, 0) in local coords.
    The revolution sweeps symmetrically about azimuth 0.
    """
    profile = _build_nose_profile_wire()

    # Revolve around global Z axis = local Y axis on XZ workplane
    revolved = profile.revolve(
        angleDegrees=NOSE_SWEEP_DEG,
        axisStart=(0, 0, 0),
        axisEnd=(0, 1, 0),   # local Y = global Z
    )

    # The revolve starts at azimuth 0 and sweeps CCW by NOSE_SWEEP_DEG.
    # Rotate back by half the sweep so the nose is centred on azimuth 0.
    solid = revolved.val()
    solid = solid.rotate((0, 0, 0), (0, 0, 1), -NOSE_SWEEP_DEG / 2.0)

    return solid


def build_nose_solids() -> list[cq.Solid]:
    """Create all nose solids, evenly spaced around Z."""
    one = build_one_nose_solid()
    solids: list[cq.Solid] = []

    for k in range(NOSE_COUNT):
        angle = k * NOSE_SPACING_DEG
        rotated = one.rotate((0, 0, 0), (0, 0, 1), angle)
        solids.append(rotated)

    return solids


# ============================================================
# Robust incremental union
# ============================================================

def union_incremental(base: cq.Workplane,
                      solids: list[cq.Solid]) -> cq.Workplane:
    """Union a list of Solids into a Workplane one-by-one (more stable)."""
    part = base
    for i, s in enumerate(solids):
        print(f"  Union nose {i + 1}/{len(solids)}")
        nose_wp = cq.Workplane("XY").add(s)
        try:
            part = part.union(nose_wp, clean=False, glue=False)
        except Exception:
            # Fallback: try without glue flag
            try:
                part = part.union(nose_wp, clean=False)
            except Exception as e:
                print(f"    WARNING: union failed for nose {i+1}: {e}")
    return part


# ============================================================
# Build final part
# ============================================================

def build_part() -> cq.Workplane:
    """Assemble base frustum + nose features."""
    base  = build_conic_disk()
    noses = build_nose_solids()
    part  = union_incremental(base, noses)

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
    print("Building UC2 master insert (conic disk + 6 revolved noses)")
    print(f"  NOSE_COUNT     = {NOSE_COUNT}")
    print(f"  NOSE_SWEEP_DEG = {NOSE_SWEEP_DEG}°")
    print(f"  NOSE_SPACING   = {NOSE_SPACING_DEG}°")
    print(f"  R_TOP = {R_TOP:.3f} mm,  R_BOT = {R_BOT:.3f} mm")

    p = build_part()
    export_part(p)

    print(f"Exported: {OUT_STEP}")
    print(f"Exported: {OUT_STL}")