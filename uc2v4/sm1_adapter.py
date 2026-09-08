"""openUC2 V4 SM1 adapter insert: a 1x1 insert with an SM1 thread on the axis.

This is the road for the CASED half of a vendor catalog. Every ``-ML`` mounted
Thorlabs lens, every mounted filter and every SM1 lens tube already carries its
own barrel, so it needs no cavity — it needs a thread to screw into. One insert
covers all of them.

SM1 is 1.035"-40: major Ø 26.289 mm, pitch 0.635 mm. The thread is cut as the
female half — the bore sits at the major diameter and the crests stand inward
by ``thread_depth_mm``. ``lens_insert._thread_solid`` sweeps the helix (the same
trapezoid the molded lens insert uses, at its own pitch).

Coordinates: optical axis = +Z, the insert's mid-plane at z = 0; the SM1 part
screws in from the +Z face. With ``clear_aperture_mm`` the bore narrows at
``stop_depth_mm`` into a shoulder, which is what fixes the optic's axial
position in the cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .interface import SquareInsertInterface, base_plate
    from .lens_insert import LensInsertParams, _thread_solid
except ImportError:                     # pragma: no cover
    from interface import SquareInsertInterface, base_plate
    from lens_insert import LensInsertParams, _thread_solid


#: SM1 = 1.035"-40 (Thorlabs' own designation).
SM1_MAJOR_DIAM_MM = 26.289
SM1_PITCH_MM = 0.635


@dataclass(frozen=True)
class SM1AdapterParams:
    interface: SquareInsertInterface = field(default_factory=SquareInsertInterface)
    thickness_mm: float = 12.0

    major_diam_mm: float = SM1_MAJOR_DIAM_MM
    pitch_mm: float = SM1_PITCH_MM
    #: Radial. The swept profile is 2*depth + crest_flat tall, and that has to
    #: stay under one pitch or consecutive turns intersect and the fuse fails.
    thread_depth_mm: float = 0.24
    fit_clearance_mm: float = 0.05         # on the bore Ø, for a printed fit
    engagement_mm: float = 5.0             # how much thread the part screws into
    chamfer_mm: float = 0.6                # lead-in at the entry face

    #: Optional stop: the bore steps down to this Ø, and the barrel butts on it.
    clear_aperture_mm: float | None = None
    stop_depth_mm: float | None = None     # from the entry face; None = just past the thread

    @property
    def bore_r(self) -> float:
        return (self.major_diam_mm + self.fit_clearance_mm) / 2.0

    @property
    def crest_r(self) -> float:
        return self.bore_r - self.thread_depth_mm

    @property
    def turns(self) -> float:
        return self.engagement_mm / self.pitch_mm

    @property
    def crest_flat(self) -> float:
        return min(0.1, self.pitch_mm / 5.0)

    @property
    def profile_height(self) -> float:
        """Axial height of one thread turn — must stay under the pitch."""
        return 2.0 * self.thread_depth_mm + self.crest_flat

    def thread_params(self, start_z: float) -> LensInsertParams:
        """The thread helper's inputs: crest at ``crest_r``, root on the bore wall."""
        return LensInsertParams(
            lens_diam=2.0 * self.crest_r,
            thread_pitch=self.pitch_mm,
            thread_turns=self.turns,
            thread_crest_oversize=0.0,
            thread_root_oversize=2.0 * self.thread_depth_mm,
            thread_start_z=start_z,
            thread_crest_flat=self.crest_flat,
            thread_root_embed=0.05,
            thread_start_azimuth_deg=0.0,
        )


@dataclass
class SM1Plan:
    params: SM1AdapterParams
    thread_span_mm: tuple[float, float] = (0.0, 0.0)
    stop_z_mm: float | None = None
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        p = self.params
        return {
            "thread": f'{p.major_diam_mm:.3f} mm major, {p.pitch_mm} mm pitch '
                      f'({25.4 / p.pitch_mm:.0f} TPI)',
            "bore_diam_mm": round(2 * p.bore_r, 3),
            "minor_diam_mm": round(2 * p.crest_r, 3),
            "turns": round(p.turns, 2),
            "thread_span_mm": [round(v, 3) for v in self.thread_span_mm],
            "insert_thickness_mm": p.thickness_mm,
            #: Where a part screwed home puts its shoulder, from the cell centre.
            "seat_z_mm": None if self.stop_z_mm is None else round(self.stop_z_mm, 3),
            "warnings": self.warnings,
        }


def plan_sm1_adapter(params: SM1AdapterParams | None = None) -> SM1Plan:
    """Check the thread against the insert, and say where the part comes to rest."""
    p = params or SM1AdapterParams()
    if p.pitch_mm <= 0 or p.thread_depth_mm <= 0:
        raise ValueError("pitch and thread depth must be positive")
    if p.engagement_mm <= p.pitch_mm:
        raise ValueError(
            f"engagement {p.engagement_mm} mm is less than one {p.pitch_mm} mm turn")
    if p.profile_height >= p.pitch_mm:
        raise ValueError(
            f"a {p.thread_depth_mm} mm deep thread is {p.profile_height:.3f} mm tall per "
            f"turn, more than the {p.pitch_mm} mm pitch — consecutive turns would "
            "intersect. Use thread_depth_for(pitch)")
    max_r = p.interface.edge_half - 1.0
    if p.bore_r > max_r:
        raise ValueError(
            f"an SM1 bore needs r = {p.bore_r:.2f} mm; the insert outline only allows "
            f"{max_r:.2f} mm")

    t2 = p.thickness_mm / 2.0
    top = t2 - p.chamfer_mm
    start = top - p.engagement_mm
    plan = SM1Plan(params=p, thread_span_mm=(start, top))
    if start < -t2 + p.chamfer_mm:
        raise ValueError(
            f"{p.engagement_mm} mm of thread does not fit a {p.thickness_mm} mm insert "
            "— raise thickness_mm or lower engagement_mm")

    if p.clear_aperture_mm is not None:
        if p.clear_aperture_mm >= 2.0 * p.crest_r:
            raise ValueError(
                f"the stop Ø{p.clear_aperture_mm} mm is not smaller than the thread's "
                f"Ø{2 * p.crest_r:.2f} mm — it would not stop anything")
        depth = (p.chamfer_mm + p.engagement_mm + 0.5 if p.stop_depth_mm is None
                 else p.stop_depth_mm)
        plan.stop_z_mm = t2 - depth
        if plan.stop_z_mm < -t2:
            raise ValueError(
                f"the stop sits {depth} mm in, past the {p.thickness_mm} mm insert")
        if plan.stop_z_mm > start:
            plan.warnings.append(
                "the stop shoulder sits inside the threaded length; a part screwed "
                "home will bottom out before it is fully engaged")
    return plan


def _bore_cutter(plan: SM1Plan) -> cq.Workplane:
    """The revolved bore: chamfered mouth, thread bore, then the stop step."""
    p = plan.params
    t2 = p.thickness_mm / 2.0
    ch = p.chamfer_mm
    floor = -t2 if plan.stop_z_mm is None else plan.stop_z_mm
    profile = [(0.0, t2), (p.bore_r + ch, t2), (p.bore_r, t2 - ch), (p.bore_r, floor)]
    if plan.stop_z_mm is not None:
        r = p.clear_aperture_mm / 2.0
        profile += [(r, floor), (r, -t2 + 0.4), (r + 0.4, -t2)]
    profile.append((0.0, -t2))
    wp = cq.Workplane("XZ").moveTo(*profile[0])
    for point in profile[1:]:
        wp = wp.lineTo(*point)
    return wp.close().revolve(360.0, (0, 0, 0), (0, 1, 0))


def build_sm1_adapter(params: SM1AdapterParams | None = None,
                      plan: SM1Plan | None = None) -> cq.Workplane:
    """The printed 1x1 insert with its SM1 thread, in the cube frame."""
    plan = plan or plan_sm1_adapter(params)
    p = plan.params
    body = base_plate(p.interface, p.thickness_mm).cut(_bore_cutter(plan))
    body = body.union(_thread_solid(p.thread_params(plan.thread_span_mm[0])))
    body = body.clean()
    if len(body.solids().vals()) != 1:
        raise ValueError("the adapter did not come out as one solid")
    return body


def thread_depth_for(pitch_mm: float) -> float:
    """The deepest radial thread *pitch_mm* can carry without turns intersecting."""
    return max(0.4 * pitch_mm - 0.02, 0.05)


if __name__ == "__main__":
    import json

    plan = plan_sm1_adapter(SM1AdapterParams(clear_aperture_mm=22.0))
    part = build_sm1_adapter(plan=plan)
    cq.exporters.export(part, "uc2v4_sm1_adapter.step")
    cq.exporters.export(part, "uc2v4_sm1_adapter.stl", tolerance=0.02)
    print(json.dumps(plan.report(), indent=2))
