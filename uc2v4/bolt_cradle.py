"""Cradle from a bolt pattern: a device held by the screw holes in one of its faces — a
board camera, a camera body, a photodiode or LED board.

Two forms:

- ``across`` — the holes are in a face across the beam (a board camera: its sensor faces the
  light). A square insert on the cube's notch grid with the holes, stand-off pads under them so
  parts on the board's face stay clear, and a window for the light.
- ``pedestal`` — the holes are in a face along the beam (a camera body's base). A block that
  stands on a plate, the device on top with its optical axis at the beam height, ears with M3
  holes for the plate.

The pattern is given in the face's own coordinates (u, v); ``axis_uv_mm`` is where the
device's optical axis crosses that face (``across``) or lies over it (``pedestal``: u along the
beam, v across, plus ``axis_height_mm`` above the face). Frames: ``across`` — the insert
frame of the other V4 inserts (beam = z, mid-plane at z = 0 before the notch shift);
``pedestal`` — the plate's top at z = 0, beam along +x over (0, 0). Units mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from .interface import SquareInsertInterface, base_plate

#: clearance Ø, thread-forming pilot Ø, head Ø, head height (ISO 4762 socket heads).
SCREWS = {"M2": (2.4, 1.6, 3.8, 2.0), "M2.5": (2.9, 2.1, 4.5, 2.5),
          "M3": (3.4, 2.5, 5.5, 3.0), "M4": (4.5, 3.3, 7.0, 4.0)}
NOTCHES = (-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0)


@dataclass(frozen=True)
class BoltCradleParams:
    holes_mm: tuple[tuple[float, float], ...]
    screw: str = "M3"
    form: str = "across"                      # across | pedestal
    tapped_device: bool = True                # the device's holes are threaded
    axis_uv_mm: tuple[float, float] = (0.0, 0.0)
    device_side: str = "+z"                   # across: which face of the plate the device sits on
    thickness_mm: float = 5.0                 # across: plate; pedestal: floor under the screw heads
    standoff_mm: float = 0.0                  # across: pads under the device's face
    window_mm: tuple[float, float] | float = 12.0   # across: Ø, or (w, h) of a rectangle
    z_mm: float = 0.0                         # across: where along the beam (nearest notch)
    axis_height_mm: float = 10.0              # pedestal: optical axis above the device's face
    beam_height_mm: float = 30.0              # pedestal: the beam above the plate
    margin_mm: float = 3.0                    # pedestal: block beyond the holes
    ear_mm: float = 8.0                       # pedestal: ear length for the M3 plate screws


@dataclass
class BoltCradlePlan:
    params: BoltCradleParams
    holes_mm: list[tuple[float, float]] = field(default_factory=list)   # in the part frame
    notch_mm: float = 0.0
    top_mm: float = 0.0                       # pedestal: block top (the device's face)
    footprint_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    ear_holes_mm: list[tuple[float, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"form": self.params.form, "screw": self.params.screw,
                "holes_mm": [[round(a, 3), round(b, 3)] for a, b in self.holes_mm],
                "notch_mm": self.notch_mm, "top_mm": round(self.top_mm, 3),
                "footprint_mm": [round(v, 3) for v in self.footprint_mm],
                "ear_holes_mm": [[round(a, 3), round(b, 3)] for a, b in self.ear_holes_mm],
                "warnings": self.warnings}


def plan_bolt_cradle(p: BoltCradleParams, iface: SquareInsertInterface | None = None) -> BoltCradlePlan:
    """Check the pattern against the insert or the plate; nothing is built."""
    if p.screw not in SCREWS:
        raise ValueError(f"screw must be one of {', '.join(SCREWS)}, got {p.screw!r}")
    if p.form not in ("across", "pedestal"):
        raise ValueError(f"form must be 'across' or 'pedestal', got {p.form!r}")
    if not p.holes_mm:
        raise ValueError("no holes: give the device's bolt pattern")
    clear, pilot, head, head_h = SCREWS[p.screw]
    u0, v0 = p.axis_uv_mm
    plan = BoltCradlePlan(params=p)
    if p.form == "across":
        iface = iface or SquareInsertInterface()
        plan.holes_mm = [(u - u0, v - v0) for u, v in p.holes_mm]
        limit = iface.shoulder_half - head / 2.0 - 0.5
        for u, v in plan.holes_mm:
            if abs(u) > limit or abs(v) > limit:
                raise ValueError(
                    f"a hole at ({u:.2f}, {v:.2f}) mm from the beam axis: the insert's flat "
                    f"centre is ±{iface.shoulder_half:g} mm, so an {p.screw} head needs it "
                    f"within ±{limit:.2f} mm")
        if p.device_side not in ("+z", "-z"):
            raise ValueError(f"device_side must be '+z' or '-z', got {p.device_side!r}")
        if p.tapped_device and p.thickness_mm < head_h + 1.0:
            raise ValueError(f"a {p.thickness_mm} mm plate leaves no floor under an {p.screw} "
                             f"head ({head_h} mm): make it at least {head_h + 1.0:g} mm")
        notch = min(NOTCHES, key=lambda n: abs(n - p.z_mm))
        if abs(notch - p.z_mm) > 2.5 + 1e-9:
            raise ValueError(f"z = {p.z_mm} mm is past the outer notch (±15 mm): move the "
                             "device to a neighbouring cube")
        if abs(notch - p.z_mm) > 1e-9:
            plan.warnings.append(f"the insert sits on the notch at {notch:g} mm, not at "
                                 f"{p.z_mm:g} mm")
        plan.notch_mm = notch
    else:
        us = [u for u, _ in p.holes_mm]
        vs = [v for _, v in p.holes_mm]
        plan.holes_mm = [(u - u0, v - v0) for u, v in p.holes_mm]
        plan.top_mm = p.beam_height_mm - p.axis_height_mm
        if plan.top_mm < p.thickness_mm + head_h:
            raise ValueError(
                f"the device's face would sit {plan.top_mm:.2f} mm above the plate; the block "
                f"needs {p.thickness_mm + head_h:g} mm for the {p.screw} heads under it")
        m = p.margin_mm + head / 2.0
        plan.footprint_mm = (min(us) - u0 - m, max(us) - u0 + m, min(vs) - v0 - m, max(vs) - v0 + m)
        x0, x1, _, _ = plan.footprint_mm
        plan.ear_holes_mm = [(x0 - p.ear_mm / 2.0, 0.0), (x1 + p.ear_mm / 2.0, 0.0)]
    return plan


def _cyl(r: float, p0, axis, length: float) -> cq.Workplane:  # noqa: ANN001
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(r, length, cq.Vector(*p0), cq.Vector(*axis)))


def build_bolt_cradle(plan: BoltCradlePlan) -> cq.Workplane:
    """The printed cradle: ``across`` in the insert frame, ``pedestal`` in the plate frame."""
    p = plan.params
    clear, pilot, head, head_h = SCREWS[p.screw]
    if p.form == "across":
        t = p.thickness_mm
        s = 1.0 if p.device_side == "+z" else -1.0
        body = base_plate(SquareInsertInterface(), t)
        face = s * t / 2.0
        if p.standoff_mm > 0:
            for u, v in plan.holes_mm:
                pad = _cyl(head / 2.0, (u, v, face), (0, 0, s), p.standoff_mm)
                body = body.union(pad)
        for u, v in plan.holes_mm:
            if p.tapped_device:
                body = body.cut(_cyl(clear / 2.0, (u, v, -40.0), (0, 0, 1), 80.0))
                head_cut = _cyl(head / 2.0 + 0.2, (u, v, -face - s * 1.0), (0, 0, s), head_h + 1.3)
                body = body.cut(head_cut)
            else:
                body = body.cut(_cyl(pilot / 2.0, (u, v, -40.0), (0, 0, 1), 80.0))
        w = p.window_mm
        if isinstance(w, (tuple, list)):
            window = cq.Workplane("XY").box(w[0], w[1], 80.0)
        else:
            window = _cyl(w / 2.0, (0, 0, -40.0), (0, 0, 1), 80.0)
        body = body.cut(window)
        return body.clean()
    x0, x1, y0, y1 = plan.footprint_mm
    top = plan.top_mm
    block = cq.Workplane("XY").box(x1 - x0, y1 - y0, top, centered=False).translate((x0, y0, 0))
    ear_h = min(5.0, top)
    ears = cq.Workplane("XY").box(x1 - x0 + 2 * p.ear_mm, min(y1 - y0, 14.0), ear_h,
                                  centered=False).translate((x0 - p.ear_mm, -min(y1 - y0, 14.0) / 2, 0))
    body = block.union(ears)
    for u, v in plan.holes_mm:
        if p.tapped_device:
            body = body.cut(_cyl(clear / 2.0, (u, v, -1.0), (0, 0, 1), top + 2.0))
            pocket_top = top - p.thickness_mm
            body = body.cut(_cyl(head / 2.0 + 0.2, (u, v, -1.0), (0, 0, 1), pocket_top + 1.0))
        else:
            body = body.cut(_cyl(pilot / 2.0, (u, v, top - 12.0), (0, 0, 1), 13.0))
    for u, v in plan.ear_holes_mm:
        body = body.cut(_cyl(SCREWS["M3"][0] / 2.0, (u, v, -1.0), (0, 0, 1), ear_h + 2.0))
    return body.clean()
