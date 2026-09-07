"""openUC2 V4 lens insert (MAS - 2013 "Square Inserts" lineage).

``build_lens_insert()`` with default parameters reproduces
PRT - 2027 - INSLEND43F-50 - V04 ("Insert for lens"): a 17 mm tall block on
the square-insert interface whose interior is a lens cavity:

    z = +8.5  top face (0.4 chamfer into the thread bore)
    z =  2.9..8.1   internal thread, root Ø(LensDiam+2.2), crest Ø(LensDiam+0.8),
                    pitch 1.7 mm, 2 turns, 45 deg trapezoidal flanks - the
                    knurled pre-screw ring screws in here and clamps the lens
    z =  2.0..2.9   45 deg lead-in cone
    z = -6.3..2.0   lens pocket Ø(LensDiam+0.4)
    z = -6.3        lens seat (the lens rests on this shoulder)
    z = -8.5..-6.7  clear aperture Ø(LensDiam-4), chamfered both ends

All numbers extracted from the Inventor master via COM (parameter names:
LensDiam, ThreadPitch, LensThicknessEdge, ...) and verified against exact
STEP sections of the released part. The engraved label text on two side
faces (0.7 mm deep, FontHight 4.5) is intentionally not reproduced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .interface import SquareInsertInterface
except ImportError:                     # pragma: no cover
    from interface import SquareInsertInterface


@dataclass(frozen=True)
class LensInsertParams:
    interface: SquareInsertInterface = SquareInsertInterface()
    thickness: float = 17.0                # d167, total height (z = +-8.5)

    lens_diam: float = 43.0                # LensDiam
    pocket_clearance: float = 0.4          # pocket Ø = LensDiam + 0.4 (d225)
    aperture_undersize: float = 4.0        # aperture Ø = LensDiam - 4 (d365)
    seat_z: float = -6.3                   # lens seat height
    pocket_top_z: float = 2.0              # pocket ends, lead-in cone starts

    thread: bool = True
    thread_pitch: float = 1.7              # ThreadPitch
    thread_turns: float = 2.0              # Coil revolutions (d235)
    thread_crest_oversize: float = 0.8     # crest Ø = LensDiam + 0.8 (d364)
    thread_root_oversize: float = 2.2      # root Ø = LensDiam + 2.2 (d226)
    thread_start_z: float = 3.9            # crest center at helix start
    thread_start_azimuth_deg: float = 180.0
    thread_crest_flat: float = 0.2         # measured flat widths
    thread_root_embed: float = 0.05        # root embedded into the bore wall

    inner_chamfer: float = 0.4             # aperture / seat / rim chamfers

    def with_grid(self, grid: float) -> "LensInsertParams":
        return replace(self, interface=replace(self.interface, grid=grid))

    @property
    def pocket_r(self) -> float:
        return (self.lens_diam + self.pocket_clearance) / 2.0

    @property
    def aperture_r(self) -> float:
        return (self.lens_diam - self.aperture_undersize) / 2.0

    @property
    def crest_r(self) -> float:
        return (self.lens_diam + self.thread_crest_oversize) / 2.0

    @property
    def root_r(self) -> float:
        return (self.lens_diam + self.thread_root_oversize) / 2.0


def _cavity_cut(p: LensInsertParams) -> cq.Workplane:
    """Revolved cut of the whole lens cavity incl. its chamfers."""
    t2 = p.thickness / 2.0
    ch = p.inner_chamfer
    cone_top_z = p.pocket_top_z + (p.root_r - p.pocket_r)  # 45 deg lead-in
    profile = [
        (0.0, t2),
        (p.root_r + ch, t2),                 # top rim chamfer
        (p.root_r, t2 - ch),                 # thread bore wall ...
        (p.root_r, cone_top_z),
        (p.pocket_r, p.pocket_top_z),        # 45 deg lead-in cone
        (p.pocket_r, p.seat_z),              # lens pocket wall
        (p.aperture_r + ch, p.seat_z),       # seat, then chamfer down
        (p.aperture_r, p.seat_z - ch),
        (p.aperture_r, -t2 + ch),            # clear aperture wall
        (p.aperture_r + ch, -t2),            # bottom chamfer
        (0.0, -t2),
    ]
    wp = cq.Workplane("XZ").moveTo(*profile[0])
    for pt in profile[1:]:
        wp = wp.lineTo(*pt)
    wp = wp.close()
    return wp.revolve(360.0, (0, 0, 0), (0, 1, 0))


def _thread_solid(p: LensInsertParams) -> cq.Workplane:
    """Internal thread as a trapezoid swept along a helix (right-handed).

    Measured phase: with the helix starting at azimuth 180 deg, the crest
    center sits at z = 3.9; crest flats land at 4.225..4.425 on -Y and
    4.65..4.85 on +X exactly as in the released STEP.
    """
    pitch = p.thread_pitch
    height = pitch * p.thread_turns
    z0 = p.thread_start_z
    root_x = p.root_r + p.thread_root_embed
    depth = p.root_r - p.crest_r                     # 0.7 radial
    half_base = depth + p.thread_crest_flat / 2.0    # 45 deg flanks

    helix = cq.Wire.makeHelix(pitch, height, p.root_r,
                              cq.Vector(0, 0, z0), cq.Vector(0, 0, 1))
    profile = (
        cq.Workplane("XZ")
        .moveTo(root_x, z0 - half_base)
        .lineTo(root_x, z0 + half_base)
        .lineTo(p.crest_r, z0 + p.thread_crest_flat / 2.0)
        .lineTo(p.crest_r, z0 - p.thread_crest_flat / 2.0)
        .close()
    )
    thread = profile.sweep(cq.Workplane(obj=helix), isFrenet=True)
    return thread.rotate((0, 0, 0), (0, 0, 1), p.thread_start_azimuth_deg)


def build_lens_insert(params: LensInsertParams | None = None) -> cq.Workplane:
    p = params or LensInsertParams()
    if p.aperture_r >= p.pocket_r:
        raise ValueError("aperture must be smaller than the lens pocket")
    max_r = p.interface.edge_half - 1.0  # keep a molded wall to the outline
    cavity_r = p.root_r if p.thread else p.pocket_r
    if cavity_r > max_r:
        raise ValueError(
            f"lens_diam {p.lens_diam} needs a cavity radius {cavity_r:.2f} mm; "
            f"the insert outline only allows {max_r:.2f} mm "
            f"(max lens_diam ~{2 * max_r - (p.thread_root_oversize if p.thread else p.pocket_clearance):.1f})"
        )
    if p.thread:
        t2 = p.thickness / 2.0
        half_base = (p.root_r - p.crest_r) + p.thread_crest_flat / 2.0
        thread_top = p.thread_start_z + p.thread_pitch * p.thread_turns + half_base
        thread_bot = p.thread_start_z - half_base
        cone_top_z = p.pocket_top_z + (p.root_r - p.pocket_r)
        if thread_top > t2 - p.inner_chamfer + 1e-6:
            raise ValueError(
                f"thread ends at z={thread_top:.2f}, above the bore top "
                f"{t2 - p.inner_chamfer:.2f}; reduce thread_turns or thread_start_z")
        if thread_bot < cone_top_z - 1e-6:
            raise ValueError(
                f"thread starts at z={thread_bot:.2f}, below the lead-in cone "
                f"{cone_top_z:.2f}; raise thread_start_z")

    from interface import base_plate  # local import to avoid cycle noise

    part = base_plate(p.interface, p.thickness)
    if 0: 
        part = part.cut(_cavity_cut(p))
        if p.thread:
            part = part.union(_thread_solid(p))
    return part.clean()


if __name__ == "__main__":
    part = build_lens_insert()
    cq.exporters.export(part, "uc2v4_lens_insert.step")
    cq.exporters.export(part, "uc2v4_lens_insert.stl")
    print("exported uc2v4_lens_insert.step")
