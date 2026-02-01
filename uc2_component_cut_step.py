# uc2_component_cut_step.py
# Creates a STEP file that represents the negative volume (cutter) of a component,
# for example a lens pocket. Optical axis is Z, centered at (0,0).

import cadquery as cq
import math

# ----------------------------
# Explicit parameters
# ----------------------------
OUT_STEP_PATH = "component_cut.step"
OUT_STL_PATH  = "component_cut.stl"

# Lens style cutter (example)
LENS_DIAMETER_NOMINAL = 25.0      # mm
RADIAL_CLEARANCE      = 0.20      # mm
THROUGH_BORE_DIAMETER = LENS_DIAMETER_NOMINAL + RADIAL_CLEARANCE

SEAT_DIAMETER         = LENS_DIAMETER_NOMINAL + 0.60   # slightly larger top pocket
SEAT_DEPTH            = 2.0                            # mm pocket depth

CUTTER_TOTAL_HEIGHT   = 30.0       # mm, keep taller than insert thickness for robust boolean

# Optional set screw holes (radial)
ADD_SET_SCREWS        = True
SET_SCREW_COUNT       = 3
SET_SCREW_DIAMETER    = 2.6        # drill for M3 clearance; for tapping use smaller
SET_SCREW_RADIUS      = (THROUGH_BORE_DIAMETER / 2.0) + 2.0
SET_SCREW_Z           = 0.0        # mm
SET_SCREW_LENGTH      = 40.0       # mm, long cylinder to guarantee cut

# STL quality
STL_LINEAR_TOL        = 0.05
STL_ANGULAR_TOL_DEG   = 5.0


def build_lens_cutter() -> cq.Workplane:
    r_bore = THROUGH_BORE_DIAMETER / 2.0
    r_seat = SEAT_DIAMETER / 2.0

    # Through bore (centered on origin, along Z)
    bore = cq.Workplane("XY").circle(r_bore).extrude(CUTTER_TOTAL_HEIGHT, both=True)

    # Seat pocket at +Z side
    seat_center_z = (CUTTER_TOTAL_HEIGHT / 2.0) - (SEAT_DEPTH / 2.0)
    seat = (
        cq.Workplane("XY")
        .workplane(offset=seat_center_z)
        .circle(r_seat)
        .extrude(SEAT_DEPTH, both=True)
    )

    cutter = bore.union(seat)

    if ADD_SET_SCREWS and SET_SCREW_COUNT > 0:
        screw = cq.Workplane("YZ").circle(SET_SCREW_DIAMETER / 2.0).extrude(SET_SCREW_LENGTH, both=True)
        # Move the screw axis to the desired radius in +Y, then rotate copies around Z
        screw = screw.translate((0, SET_SCREW_RADIUS, SET_SCREW_Z))

        screws = cq.Workplane("XY")
        for k in range(SET_SCREW_COUNT):
            ang = 360.0 * k / float(SET_SCREW_COUNT)
            screws = screws.add(screw.rotate((0, 0, 0), (0, 0, 1), ang))

        cutter = cutter.union(screws)

    return cutter


def export(step_path: str, stl_path: str, model: cq.Workplane) -> None:
    cq.exporters.export(model, step_path)
    cq.exporters.export(
        model,
        stl_path,
        tolerance=STL_LINEAR_TOL,
        angularTolerance=math.radians(max(0.1, STL_ANGULAR_TOL_DEG)),
    )


if __name__ == "__main__":
    m = build_lens_cutter()
    export(OUT_STEP_PATH, OUT_STL_PATH, m)
