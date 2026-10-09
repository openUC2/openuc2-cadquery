"""FRAME objective support: the printed part between the kinematic objective sled and an objective.

The design of ``FRAME - 0402 / 0408 - Support objective`` (derived from ``FRAME - 4000 -
Kinematic objective mount - master``), measured on the parts: a 5.2 mm flange on the sled with
two M2.5 lugs (Ø2.9 at r 16 mm, 55° / 235°), a Ø25.4 boss up to the objective's shoulder, the
objective's thread in the top of a through bore. Here the thread, the height and the boss are
parameters; ``parfocal_heights`` picks one height per slot so all objectives focus in one plane.

Frame: the sled's top face is z = 0, the slot's axis is +z through (0, 0), the objective's
shoulder sits at z = height. The same part fits either slot of the 2-position sled: the second
slot's screw pattern is the first one's turned 70° about the axis. Units mm.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .opm_launch_holder import internal_thread
except ImportError:                     # pragma: no cover
    from opm_launch_holder import internal_thread


#: name -> (major Ø, pitch, thread length on a typical objective). RMS is W0.8"x1/36".
OBJECTIVE_THREADS: dict[str, tuple[float, float, float]] = {
    "RMS": (20.32, 25.4 / 36.0, 4.5),
    "M25x0.75": (25.0, 0.75, 5.0),
    "M26x0.706": (26.0, 25.4 / 36.0, 5.0),
    "M27x0.75": (27.0, 0.75, 5.0),
    "M32x0.75": (32.0, 0.75, 5.0),
    "C-mount": (25.4, 25.4 / 32.0, 4.0),
}


def objective_thread(name: str) -> tuple[float, float, float]:
    """(major Ø, pitch, typical length) of a thread name: a table row or M<d>x<p> / W<d>x<p>."""
    key = name.strip()
    for k, v in OBJECTIVE_THREADS.items():
        if key.upper().replace(" ", "") == k.upper():
            return v
    if key.upper().replace(" ", "") in ('W0.8"X1/36"', "W0.8X1/36", "W20.32X0.706"):
        return OBJECTIVE_THREADS["RMS"]
    m = re.fullmatch(r"[MW](\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)", key.replace(" ", ""))
    if not m:
        raise ValueError(f"thread {name!r}: give {', '.join(OBJECTIVE_THREADS)} or M<Ø>x<pitch>")
    return float(m.group(1)), float(m.group(2)), 5.0


@dataclass(frozen=True)
class FrameSled:
    """The FRAME kinematic objective sled (FR110-0401) and the support's fixed features."""

    flange_mm: float = 5.2            # flange thickness; the screw heads sit on its top
    hole_radius_mm: float = 16.0      # M2.5 tapped holes in the sled, from the slot axis
    hole_angle_deg: float = 55.0      # first hole; the second is opposite
    hole_d_mm: float = 2.9            # clearance in the flange
    lug_r_mm: float = 2.75            # flange outline around each hole
    head_d_mm: float = 4.5            # ISO 4762 M2.5 head
    pocket_d_mm: float = 5.2          # screw access cut into a boss that covers the heads
    min_boss_d_mm: float = 25.4
    slot_pitch_mm: float = 29.8       # the 2-position sled's two slot axes


@dataclass(frozen=True)
class ObjectiveFacts:
    """What the support needs to know about the objective (all optional)."""

    parfocal_mm: float | None = None          # shoulder to focal plane
    working_distance_mm: float | None = None
    thread_length_mm: float | None = None     # thread below the shoulder
    barrel_diameter_mm: float | None = None


@dataclass(frozen=True)
class ObjectiveSupportParams:
    thread: str = "RMS"
    thread_major_mm: float | None = None      # override the table
    thread_pitch_mm: float | None = None
    height_mm: float = 16.4                   # sled top to the objective's shoulder
    engagement_mm: float | None = None        # thread length; default the objective's own
    lead_mm: float = 1.0                      # plain bore under the shoulder before the thread
    fit_clearance_mm: float = 0.18            # bore Ø over the major Ø (RMS: 20.32 -> 20.5)
    thread_depth_mm: float | None = None      # default: the deepest 60° form the pitch carries
    boss_diameter_mm: float | None = None     # default: min_boss_d, or the bore plus two walls
    wall_mm: float = 2.0
    chamfer_mm: float = 0.2
    label: str = ""                           # engraved on the boss, facing -y
    label_height_mm: float = 4.5
    label_depth_mm: float = 0.6
    objective: ObjectiveFacts = field(default_factory=ObjectiveFacts)
    sled: FrameSled = field(default_factory=FrameSled)


CREST_FLAT_MM = 0.1
FLANK_DEG = 30.0                          # 60° thread form


@dataclass
class ObjectiveSupportPlan:
    params: ObjectiveSupportParams
    major_mm: float
    pitch_mm: float
    depth_mm: float
    engagement_mm: float
    bore_d_mm: float
    boss_d_mm: float
    min_height_mm: float
    pockets: bool
    thread_z_mm: tuple[float, float]
    warnings: list[str] = field(default_factory=list)

    @property
    def focal_plane_mm(self) -> float | None:
        pf = self.params.objective.parfocal_mm
        return None if pf is None else self.params.height_mm + pf

    def report(self) -> dict:
        o = self.params.objective
        top = (None if o.parfocal_mm is None or o.working_distance_mm is None
               else self.params.height_mm + o.parfocal_mm - o.working_distance_mm)
        return {
            "thread": self.params.thread, "major_mm": round(self.major_mm, 3),
            "pitch_mm": round(self.pitch_mm, 4), "thread_depth_mm": round(self.depth_mm, 3),
            "engagement_mm": round(self.engagement_mm, 3), "bore_d_mm": round(self.bore_d_mm, 3),
            "boss_d_mm": round(self.boss_d_mm, 3), "height_mm": round(self.params.height_mm, 3),
            "min_height_mm": round(self.min_height_mm, 3), "screw_pockets": self.pockets,
            "thread_z_mm": [round(v, 3) for v in self.thread_z_mm],
            "focal_plane_mm": None if self.focal_plane_mm is None else round(self.focal_plane_mm, 3),
            "objective_front_mm": None if top is None else round(top, 3),
            "warnings": self.warnings,
        }


def deepest_thread(pitch_mm: float) -> float:
    """The deepest 60° female form a pitch carries without its turns touching."""
    return (0.9 * pitch_mm - CREST_FLAT_MM) / (2.0 * math.tan(math.radians(FLANK_DEG)))


def min_height(p: ObjectiveSupportParams) -> float:
    """Lowest support for these params: the flange, or the thread plus its lead."""
    _, _, length = objective_thread(p.thread)
    engagement = p.engagement_mm or p.objective.thread_length_mm or length
    return max(p.sled.flange_mm, engagement + p.lead_mm)


def plan_objective_support(p: ObjectiveSupportParams) -> ObjectiveSupportPlan:
    """Check the params against the sled; ValueError is the refusal the build would give."""
    major, pitch, length = objective_thread(p.thread)
    major = p.thread_major_mm or major
    pitch = p.thread_pitch_mm or pitch
    engagement = p.engagement_mm or p.objective.thread_length_mm or length
    depth = p.thread_depth_mm or deepest_thread(pitch)
    if 2 * depth * math.tan(math.radians(FLANK_DEG)) + CREST_FLAT_MM >= pitch:
        raise ValueError(f"thread depth {depth:.2f} mm is too deep for a {pitch} mm pitch")
    s = p.sled
    bore = major + p.fit_clearance_mm
    boss = p.boss_diameter_mm or max(s.min_boss_d_mm, bore + 2 * p.wall_mm)
    if boss < bore + 2 * 1.0:
        raise ValueError(f"boss Ø{boss} mm leaves less than 1 mm around the Ø{bore:.2f} mm bore")
    h_min = max(s.flange_mm, engagement + p.lead_mm)
    if p.height_mm < h_min - 1e-9:
        raise ValueError(f"height {p.height_mm} mm is below the {h_min:.2f} mm the flange and "
                         f"{engagement} mm of thread need: raise the focal plane or shorten the thread")
    warnings: list[str] = []
    pockets = boss / 2 > s.hole_radius_mm - s.head_d_mm / 2 - 0.25
    if pockets:
        wall = s.hole_radius_mm - s.pocket_d_mm / 2 - bore / 2
        if wall < 0.6:
            raise ValueError(f"the Ø{bore:.1f} mm bore reaches the sled's M2.5 screws (r "
                             f"{s.hole_radius_mm} mm): a thread this wide needs another sled")
        if wall < 1.2:
            warnings.append(f"only {wall:.1f} mm between the bore and the screw pockets")
    if boss > s.slot_pitch_mm - 0.5:
        warnings.append(f"boss Ø{boss:.1f} mm: no room for a support in the neighbouring slot")
    if p.label and p.height_mm - s.flange_mm < p.label_height_mm + 1.0:
        warnings.append(f"no room for the label {p.label!r} above the flange")
    o = p.objective
    if o.thread_length_mm is not None and o.thread_length_mm > p.height_mm:
        warnings.append(f"the objective's {o.thread_length_mm} mm thread reaches into the sled")
    top = p.height_mm - p.lead_mm
    return ObjectiveSupportPlan(p, major, pitch, depth, engagement, bore, boss, h_min, pockets,
                                (top - engagement, top), warnings)


def _flange_outline(r: float, s: FrameSled) -> cq.Wire:
    """Hull of the boss circle and the two lugs: boss arcs, lug arcs, four tangents."""
    a = s.lug_r_mm
    d = s.hole_radius_mm
    k = (r - a) / d
    pts: list[tuple[str, tuple]] = []
    for ang in (s.hole_angle_deg, s.hole_angle_deg + 180.0):
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-u[1], u[0])
        c = (d * u[0], d * u[1])
        tang = []
        for side in (-1.0, 1.0):
            nt = (k * u[0] + side * math.sqrt(1 - k * k) * n[0], k * u[1] + side * math.sqrt(1 - k * k) * n[1])
            tang.append(((r * nt[0], r * nt[1]), (c[0] + a * nt[0], c[1] + a * nt[1])))
        pts.append(("lug", (c, u, tang)))
    (c1, u1, t1), (c2, u2, t2) = pts[0][1], pts[1][1]
    w = cq.Workplane("XY").moveTo(*t1[0][0]).lineTo(*t1[0][1])
    w = w.threePointArc((c1[0] + a * u1[0], c1[1] + a * u1[1]), t1[1][1]).lineTo(*t1[1][0])
    mid = math.radians(s.hole_angle_deg + 90.0)
    w = w.threePointArc((r * math.cos(mid), r * math.sin(mid)), t2[0][0]).lineTo(*t2[0][1])
    w = w.threePointArc((c2[0] + a * u2[0], c2[1] + a * u2[1]), t2[1][1]).lineTo(*t2[1][0])
    mid = math.radians(s.hole_angle_deg - 90.0)
    w = w.threePointArc((r * math.cos(mid), r * math.sin(mid)), t1[0][0]).close()
    return w.val()


def _label_cut(plan: ObjectiveSupportPlan) -> cq.Solid | None:
    p = plan.params
    r = plan.boss_d_mm / 2
    zc = (p.sled.flange_mm + p.height_mm) / 2
    text = (cq.Workplane("XZ", origin=(0, -r - 1.0, zc))
            .text(p.label, p.label_height_mm, -(r + 2.0), kind="bold", halign="center", valign="center"))
    shell = cq.Solid.makeCylinder(r + 0.1, p.height_mm, cq.Vector(0, 0, 0)).cut(
        cq.Solid.makeCylinder(r - p.label_depth_mm, p.height_mm, cq.Vector(0, 0, 0)))
    return text.val().intersect(shell)


def build_objective_support(plan: ObjectiveSupportPlan) -> cq.Workplane:
    """The support as one solid, sled top at z = 0, the objective's shoulder at z = height."""
    p, s = plan.params, plan.params.sled
    h, r = p.height_mm, plan.boss_d_mm / 2
    flange_t = min(s.flange_mm, h)
    body = cq.Solid.extrudeLinear(cq.Face.makeFromWires(_flange_outline(r, s)), cq.Vector(0, 0, flange_t))
    boss = cq.Workplane("XY").circle(r).extrude(h).faces(">Z").edges().chamfer(p.chamfer_mm).val()
    body = body.fuse(boss)
    tools: list[cq.Shape] = [cq.Solid.makeCylinder(plan.bore_d_mm / 2, h + 2, cq.Vector(0, 0, -1)),
                             cq.Solid.makeCone(plan.bore_d_mm / 2, plan.bore_d_mm / 2 + p.chamfer_mm + 1.0,
                                               p.chamfer_mm + 1.0, cq.Vector(0, 0, h - p.chamfer_mm))]
    for ang in (s.hole_angle_deg, s.hole_angle_deg + 180.0):
        x = s.hole_radius_mm * math.cos(math.radians(ang))
        y = s.hole_radius_mm * math.sin(math.radians(ang))
        tools.append(cq.Solid.makeCylinder(s.hole_d_mm / 2, flange_t + 2, cq.Vector(x, y, -1)))
        if plan.pockets:
            tools.append(cq.Solid.makeCylinder(s.pocket_d_mm / 2, h, cq.Vector(x, y, flange_t)))
    solid = body.cut(*tools)
    hb = plan.depth_mm * math.tan(math.radians(FLANK_DEG)) + CREST_FLAT_MM / 2
    z_lo, z_hi = plan.thread_z_mm
    turns = (z_hi - z_lo - 2 * hb) / plan.pitch_mm
    if turns > 0.5:
        r_root = plan.bore_d_mm / 2
        thread = internal_thread(r_root, r_root - plan.depth_mm, plan.pitch_mm, z_lo + hb, turns,
                                 CREST_FLAT_MM, flank_deg=FLANK_DEG)
        solid = solid.fuse(thread)
    if p.label and "no room for the label" not in " ".join(plan.warnings):
        try:
            cut = _label_cut(plan)
        except Exception as exc:  # noqa: BLE001 - a missing font must not cost the part
            plan.warnings.append(f"label not engraved: {exc}")
        else:
            solid = solid.cut(cut)
    out = cq.Workplane("XY").add(solid.clean())
    if len(out.solids().vals()) != 1:
        raise ValueError(f"the support came out as {len(out.solids().vals())} solids")
    return out


def parfocal_heights(objectives: Sequence[ObjectiveSupportParams | None],
                     focal_plane_mm: float | None = None, reference_mm: float = 61.4,
                     step_mm: float = 0.1) -> tuple[float, list[float | None]]:
    """(focal plane above the sled, height per slot) so every objective focuses in one plane.

    The plane is ``focal_plane_mm`` if given, else the FRAME's (61.4 mm: a PF-45 objective on
    the 16.4 mm 4x support) or higher when an objective needs it. Heights round down to
    ``step_mm`` so an objective never comes closer to the sample than its WD; None marks a
    slot without a parfocal distance.
    """
    plane = focal_plane_mm
    if plane is None:
        need = [min_height(p) + p.objective.parfocal_mm for p in objectives
                if p is not None and p.objective.parfocal_mm is not None]
        plane = max([reference_mm, *need])
    heights: list[float | None] = []
    for p in objectives:
        if p is None or p.objective.parfocal_mm is None:
            heights.append(None)
            continue
        heights.append(round(math.floor((plane - p.objective.parfocal_mm) / step_mm + 1e-9) * step_mm, 6))
    return plane, heights


def generate_objective_support(params: ObjectiveSupportParams, out_stem: str) -> dict:
    """Write <out_stem>.step / .stl and return the plan report."""
    plan = plan_objective_support(params)
    part = build_objective_support(plan)
    cq.exporters.export(part, f"{out_stem}.step")
    cq.exporters.export(part, f"{out_stem}.stl", tolerance=0.02)
    return plan.report()


if __name__ == "__main__":
    import json

    four = ObjectiveSupportParams(label="4x", objective=ObjectiveFacts(45.0, 17.3, 4.5, 24.0))
    apo = replace(four, thread="M25x0.75", label="20x",
                  objective=ObjectiveFacts(60.0, 1.0, 4.9, 32.5))
    plane, (h4, h20) = parfocal_heights([four, apo])
    print(json.dumps({"plane": plane, "heights": [h4, h20]}))
    print(json.dumps(generate_objective_support(replace(four, height_mm=h4), "frame_objective_support_4x"), indent=1))
