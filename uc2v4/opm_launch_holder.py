"""dvOPM light-sheet launch holder, its two side-slid retainers and the arc-rail bracket.

The holder is the monolithic printed bar that carries the launch train of the openUC2
dvOPM (see ``openuc2-opmsimulator/opm_layout.py``): the RMS-threaded 4x objective, the
Thorlabs LJ1878L1 cylinder lens and the f = 8 mm fibre collimator, each at the axial
position the simulation puts it (the cylinder's line focus in the objective's back focal
plane). Every element goes in from an end or from the side and is locked by a part that
slides in from the side:

- **objective**: screws into a printed RMS 0.800"-36 thread at the front face;
- **cylinder lens** (12 x 10 x 5.9): drops into a side slot (from +y) whose bottom
  centres it on the axis; a printed **key** slides in behind it and fills the slot;
- **collimator** (Ø12 body, Ø14 flange, Ø7.9 nose): enters from the back, its body
  butts against the step to the beam bore; a printed **fork clip** slides in from the
  side behind the flange and retains it.

Two M3 clamp screws pass sideways through the body, below the bores, into the two
concentric arc slots of the **bracket** standing on the launch XYZ stage. The slots
are arcs about B, the point where the sheet enters the dish, so loosening the screws
and sliding the holder along the slots changes the launch angle phi about B - the
paper's pivot - for a different medium, without moving the entry point.

Frames
    holder  X along the train axis, from the objective's air focus P (x = 0) towards
            the fibre; Z "up" = away from the stage (the launch plane is XZ);
            Y = the world's y (the sheet-width direction).  The part's origin is P.
    bracket world axes, origin on the launch stage's slide top, at its centre.
    Both come with a `frame` entry in the plan JSON: origin + axes in the world frame
    for the reference medium, so the Inventor builder can place them.

All numbers come from a layout JSON written by ``opm_layout.py``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .sm1_adapter import thread_depth_for
except ImportError:                     # pragma: no cover
    from sm1_adapter import thread_depth_for

RMS_MAJOR_MM = 20.32          # 0.800"-36 (Royal Microscopical Society objective thread)
RMS_PITCH_MM = 25.4 / 36.0


@dataclass
class HolderPlan:
    """Everything the builders need, in the holder frame (mm)."""
    t: Dict[str, float]                 # train mechanics, t from the focus P
    width: float
    height: float                       # deep section (thread .. collimator body)
    tail_height: float                  # around the flange / clip
    tail_from: float
    front: float
    back: float
    screws: List[Tuple[float, float]]   # (x, z) of the clamp screw holes
    screw_d: float
    cyl_len: float                      # along Z (cylinder axis, no power)
    cyl_h: float                        # along Y (power axis)
    cyl_ct: float
    col_body_d: float
    col_flange_d: float
    col_nose_d: float
    thread_len: float = 5.0
    thread_clearance: float = 0.10      # on the bore diameter
    lead_in: float = 0.6
    beam_bore_d: float = 10.0
    fit: float = 0.10                   # clearance on printed bores / slots, per side
    clip_t: float = 1.4
    clip_reach: float = 9.0             # the fork's arms go this far past the axis
    clip_half_h: float = 9.3
    key_handle: float = 2.0
    head_cbore_d: float = 6.5
    head_cbore_depth: float = 3.0
    label: str = ""
    # bracket
    rail: Dict = field(default_factory=dict)
    bracket_thick: float = 6.0
    bracket_gap: float = 0.5
    bracket_foot: float = 4.0
    slot_w: float = 3.6
    slide_hole_pitch: float = 25.0
    slide_hole_d: float = 4.5
    table: float = 40.0
    frame_holder: Dict = field(default_factory=dict)
    frame_bracket: Dict = field(default_factory=dict)
    vendor_poses: Dict = field(default_factory=dict)

    # ---- derived ------------------------------------------------------------------
    @property
    def bore_r(self) -> float:
        return (RMS_MAJOR_MM + self.thread_clearance) / 2.0

    @property
    def thread_depth(self) -> float:
        return thread_depth_for(RMS_PITCH_MM)

    @property
    def crest_r(self) -> float:
        return self.bore_r - self.thread_depth

    @property
    def clip_x(self) -> float:
        return self.t["col_nose"] + 0.15

    def halfheight(self, x: float) -> float:
        return self.height / 2 if x < self.tail_from else self.tail_height / 2

    def report(self) -> Dict:
        t = self.t
        return {
            "frame": "holder: X = train axis from the focus P towards the fibre, Z away from the stage, Y = world y",
            "rms_thread": {"major_mm": RMS_MAJOR_MM, "pitch_mm": round(RMS_PITCH_MM, 4), "bore_d_mm": round(2 * self.bore_r, 3),
                           "crest_d_mm": round(2 * self.crest_r, 3), "length_mm": self.thread_len,
                           "from_x": self.front, "to_x": self.front + self.thread_len},
            "beam_bore_d_mm": self.beam_bore_d,
            "cyl_slot": {"x": [t["cyl_near"] - self.fit, t["cyl_far"] + self.fit], "z_halfspan": self.cyl_len / 2 + self.fit,
                         "y_bottom": -(self.cyl_h / 2 + self.fit), "open_towards": "+y",
                         "flat_face_x": t["cyl_flat"], "curved_vertex_x": t["cyl_curved"]},
            "collimator": {"body_bore_d_mm": self.col_body_d + 2 * self.fit, "from_x": t["col_front"],
                           "flange_bore_d_mm": self.col_flange_d + 2 * self.fit, "flange_from_x": t["col_flange"],
                           "clip_slot_x": [self.clip_x, self.clip_x + self.clip_t + 2 * self.fit], "inserted_from": "the back face"},
            "clamp_screws_xz": self.screws,
            "body": {"x": [self.front, self.back], "width_y": self.width, "height_z": self.height,
                     "tail_height_z": self.tail_height, "tail_from_x": self.tail_from},
            "bracket": {"slots": [{"R_mm": s["R"], "angle_from_vertical_deg": s["angle_from_vertical_deg"]} for s in self.rail.get("slots", [])],
                        "plate": self.rail.get("plate"), "phi_range_deg": self.rail.get("phi_range_deg")},
            "frames": {"holder": self.frame_holder, "bracket": self.frame_bracket},
            "vendor_poses_in_holder_frame": self.vendor_poses,
            "label": self.label,
            # the complete parameter set, for the native Inventor builder (PyInventor/build_opm_holder_ipt.py)
            "params": {
                "front_x": self.front, "back_x": self.back, "tail_from_x": self.tail_from,
                "width": self.width, "height": self.height, "tail_height": self.tail_height, "chamfer": 1.0,
                "rms_major": RMS_MAJOR_MM, "rms_pitch": RMS_PITCH_MM, "thread_clearance": self.thread_clearance,
                "thread_len": self.thread_len, "lead_in": self.lead_in, "thread_depth": self.thread_depth,
                "crest_flat": min(0.1, RMS_PITCH_MM / 5.0), "bore_r": self.bore_r, "crest_r": self.crest_r,
                "beam_bore_d": self.beam_bore_d,
                "cyl_x0": t["cyl_near"] - self.fit, "cyl_x1": t["cyl_far"] + self.fit,
                "cyl_len": self.cyl_len, "cyl_h": self.cyl_h, "fit": self.fit,
                "col_front_x": t["col_front"], "col_body_d": self.col_body_d,
                "col_flange_x": t["col_flange"], "col_flange_d": self.col_flange_d,
                "clip_x": self.clip_x, "clip_t": self.clip_t, "clip_reach": self.clip_reach, "clip_half_h": self.clip_half_h,
                "screw_d": self.screw_d, "screws_xz": self.screws,
                "head_cbore_d": self.head_cbore_d, "head_cbore_depth": self.head_cbore_depth,
            },
        }


# --------------------------------------------------------------------------- plan
def plan_from_layout(layout: Dict, label: Optional[str] = None) -> HolderPlan:
    t = layout["train_mechanics_t"]
    cfg = layout["config"]
    h, cy, co = cfg["holder"], cfg["cyl"], cfg["collimator"]
    tail_from = t["col_flange"] if h.get("tail_from_t_mm") is None else h["tail_from_t_mm"]
    screws = [(float(hole["t"]), -float(hole["h"])) for hole in layout["launch"]["foot_holes"]]
    L = layout["launch"]
    phi = math.radians(L["phi_deg"])
    a = (math.sin(phi), 0.0, -math.cos(phi))          # holder X in the world
    up = (math.cos(phi), 0.0, math.sin(phi))          # holder Z in the world
    P = L["P"]
    n = L["n"]
    rail = layout["rail"]
    pl = rail["plate"]
    plan = HolderPlan(
        t=t, width=h["width_mm"], height=h["height_mm"], tail_height=h["tail_height_mm"], tail_from=tail_from,
        front=t["holder_front"], back=t["holder_back"], screws=screws, screw_d=h["screw_d_mm"],
        cyl_len=cy["length_mm"], cyl_h=cy["height_mm"], cyl_ct=cy["ct_mm"],
        col_body_d=co["body_d_mm"], col_flange_d=co["flange_d_mm"], col_nose_d=co["nose_d_mm"],
        rail=rail, bracket_thick=h["bracket_thick_mm"], bracket_gap=h["bracket_gap_mm"], bracket_foot=h["bracket_foot_mm"],
        table=cfg["stage"]["table_mm"],
        label=label or f"dvOPM launch n{n:.2f} phi{L['phi_deg']:.1f} fcol{co['f_mm']:g} LJ1878L1 4x",
    )
    plan.frame_holder = {"origin": [P[0], 0.0, P[1]], "x_axis": list(a), "y_axis": [0.0, 1.0, 0.0], "z_axis": list(up),
                         "n": n, "phi_deg": L["phi_deg"]}
    plan.frame_bracket = {"origin": [pl["stage_centre"][0], pl["stage_centre"][1], pl["slide_top_z"]],
                          "x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "z_axis": [0, 0, 1]}
    obj = cfg["objective"]
    plan.vendor_poses = {
        "objective": {"note": "SOPTOP part: axis = its +Y from the thread towards the nose, shoulder at y = 0",
                      "shoulder_x": t["shoulder"], "part_y_axis_in_holder": [-1, 0, 0], "part_z_axis_in_holder": [0, 0, 1],
                      "origin_in_holder": [t["shoulder"], 0.0, 0.0], "wd_mm": obj["wd_mm"]},
        "cyl_lens": {"note": "LJ1878L1 STEP: x = 12 mm cylinder axis, y = 10 mm power axis, flat face at z = -2.94",
                     "origin_in_holder": [t["cyl_flat"] + cy["ct_mm"] / 2, 0.0, 0.0],
                     "part_x_axis_in_holder": [0, 0, 1], "part_y_axis_in_holder": [0, 1, 0], "part_z_axis_in_holder": [1, 0, 0]},
        "collimator": {"note": "Taobao part: body from y = 0 (output face) to 13.7, flange to 18, nose to 23.25",
                       "origin_in_holder": [t["col_front"], 0.0, 0.0], "part_y_axis_in_holder": [1, 0, 0],
                       "part_z_axis_in_holder": [0, 0, 1]},
    }
    return plan


# --------------------------------------------------------------------------- builders
def _cyl_x(r: float, x0: float, x1: float, y: float = 0.0, z: float = 0.0) -> cq.Solid:
    return cq.Solid.makeCylinder(r, x1 - x0, cq.Vector(x0, y, z), cq.Vector(1, 0, 0))


def _cyl_y(r: float, y0: float, y1: float, x: float, z: float) -> cq.Solid:
    return cq.Solid.makeCylinder(r, y1 - y0, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))


def _box(x0, x1, y0, y1, z0, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def internal_thread(r_root: float, r_crest: float, pitch: float, z0: float, turns: float,
                    crest_flat: float, embed: float = 0.05, flank_deg: float = 45.0) -> cq.Solid:
    """Thread ridge of a female thread, right-handed along +Z: root on the bore wall
    (r_root, sunk `embed` into it), crest at r_crest, flanks `flank_deg` from radial
    (45, or 30 for a 60 deg thread), crest centre at z0 and azimuth 0. Built as ruled
    surfaces between four helices - a swept profile gives OCC a solid its booleans
    mishandle, this one fuses and cuts cleanly."""
    depth = r_root - r_crest
    hb = depth * math.tan(math.radians(flank_deg)) + crest_flat / 2.0
    height = pitch * turns
    rr = r_root + embed
    zs = [z0 - hb, z0 + hb, z0 + crest_flat / 2, z0 - crest_flat / 2]
    rs = [rr, rr, r_crest, r_crest]
    hel = [cq.Wire.makeHelix(pitch, height, r, cq.Vector(0, 0, z), cq.Vector(0, 0, 1)) for r, z in zip(rs, zs)]
    faces = [cq.Face.makeRuledSurface(hel[i], hel[(i + 1) % 4]) for i in range(4)]
    for end in (0, 1):
        pts = [h.endPoint() if end else h.startPoint() for h in hel]
        faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon(pts + [pts[0]])))
    solid = cq.Solid.makeSolid(cq.Shell.makeShell(faces))
    if solid.Volume() < 0:
        solid = cq.Solid(solid.wrapped.Reversed())
    return solid.fix()


def _rms_thread(p: HolderPlan) -> cq.Solid:
    """Internal RMS thread along +X from the front face (after the lead-in chamfer)."""
    depth = p.thread_depth
    crest_flat = min(0.1, RMS_PITCH_MM / 5.0)
    half_base = depth + crest_flat / 2.0
    start = p.front + p.lead_in + half_base
    turns = (p.thread_len - p.lead_in - 2 * half_base) / RMS_PITCH_MM
    thr = internal_thread(p.bore_r, p.crest_r, RMS_PITCH_MM, start, turns, crest_flat)
    return thr.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 90.0)     # Z -> X


def build_holder(p: HolderPlan) -> cq.Workplane:
    hw = p.width / 2
    body = (cq.Workplane("XY").add(_box(p.front, p.tail_from, -hw, hw, -p.height / 2, p.height / 2))
            .edges("|X").chamfer(1.0))
    tail = (cq.Workplane("XY").add(_box(p.tail_from, p.back, -hw, hw, -p.tail_height / 2, p.tail_height / 2))
            .edges("|X").chamfer(1.0))
    body = body.union(tail)
    t, f = p.t, p.fit
    tools: List[cq.Shape] = []
    # objective thread bore + lead-in
    tools.append(_cyl_x(p.bore_r, p.front - 1.0, p.front + p.thread_len))
    tools.append(cq.Solid.makeCone(p.bore_r + p.lead_in + 0.5, p.bore_r, p.lead_in + 0.5,
                                   cq.Vector(p.front - 0.5, 0, 0), cq.Vector(1, 0, 0)))
    # beam bore from the thread to the collimator step
    tools.append(_cyl_x(p.beam_bore_d / 2, p.front + p.thread_len - 0.5, t["col_front"] + 0.01))
    # cylinder-lens slot, open towards +y
    tools.append(_box(t["cyl_near"] - f, t["cyl_far"] + f, -(p.cyl_h / 2 + f), hw + 1.0,
                      -(p.cyl_len / 2 + f), p.cyl_len / 2 + f))
    # collimator: body bore from its seat, flange counterbore out to the back face
    tools.append(_cyl_x(p.col_body_d / 2 + f, t["col_front"], p.back + 1.0))
    tools.append(_cyl_x(p.col_flange_d / 2 + f, t["col_flange"] - 0.2, p.back + 1.0))
    # retaining-clip slot behind the flange, open towards +y
    tools.append(_box(p.clip_x, p.clip_x + p.clip_t + 2 * f, -(p.clip_reach + f), hw + 1.0,
                      -(p.clip_half_h + f), p.clip_half_h + f))
    # clamp screws through the body (heads on +y, recessed)
    for x, z in p.screws:
        tools.append(_cyl_y(p.screw_d / 2, -hw - 1.0, hw + 1.0, x, z))
        tools.append(_cyl_y(p.head_cbore_d / 2, hw - p.head_cbore_depth, hw + 1.0, x, z))
    # one boolean with every cutter as its own tool (never a compound of overlapping tools)
    solid = body.val().cut(*tools)
    solid = solid.fuse(_rms_thread(p)).clean()
    body = cq.Workplane("XY").add(solid)
    if len(body.solids().vals()) != 1:
        raise ValueError(f"the holder came out as {len(body.solids().vals())} solids")
    return body


def build_cyl_key(p: HolderPlan) -> cq.Workplane:
    """Fills the cylinder-lens slot between the lens (y <= +5) and the +y face; a handle
    stands proud of the face."""
    hw, f = p.width / 2, p.fit
    x0, x1 = p.t["cyl_near"], p.t["cyl_far"]
    zh = p.cyl_len / 2
    key = _box(x0, x1, p.cyl_h / 2, hw, -zh, zh)
    handle = _box(x0, x1, hw, hw + p.key_handle, -(zh + 3.0), zh + 3.0)
    return cq.Workplane("XY").add(key).union(cq.Workplane("XY").add(handle))


def build_collimator_clip(p: HolderPlan) -> cq.Workplane:
    """Fork that slides in from +y behind the collimator flange, around its nose."""
    hw = p.width / 2
    x0 = p.clip_x + p.fit
    x1 = x0 + p.clip_t
    r_nose = p.col_nose_d / 2 + 0.15
    plate = _box(x0, x1, -p.clip_reach, hw + p.key_handle, -p.clip_half_h, p.clip_half_h)
    opening = cq.Workplane("XY").add(_box(x0 - 1, x1 + 1, 0.0, hw + p.key_handle + 1, -r_nose, r_nose)) \
        .union(cq.Workplane("XY").add(_cyl_x(r_nose, x0 - 1, x1 + 1)))
    return cq.Workplane("XY").add(plate).cut(opening)


def _arc_slot(cx: float, cz: float, R: float, a0_deg: float, a1_deg: float, w: float,
              y0: float, y1: float) -> cq.Workplane:
    """Slot of width w along the arc of radius R about (cx, cz) in the XZ plane, from
    angle a0 to a1 measured from straight down (+ towards +x); extruded from y0 to y1."""
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    am = 0.5 * (a0 + a1)

    def pt(r, ang):
        return (cx + r * math.sin(ang), cz - r * math.cos(ang))
    ro, ri = R + w / 2, R - w / 2
    sector = (cq.Workplane("XY").moveTo(*pt(ro, a0)).threePointArc(pt(ro, am), pt(ro, a1))
              .lineTo(*pt(ri, a1)).threePointArc(pt(ri, am), pt(ri, a0)).close().extrude(y1 - y0))
    for ang in (a0, a1):
        sector = sector.union(cq.Workplane("XY").center(*pt(R, ang)).circle(w / 2).extrude(y1 - y0))
    # built in XY with the plate's z as the sketch y and the extrusion along +z:
    # rotate so sketch-y -> world z and extrusion -> world -y, then shift to [y0, y1]
    return sector.rotate((0, 0, 0), (1, 0, 0), 90.0).translate((0, y1, 0))


def build_bracket(p: HolderPlan) -> cq.Workplane:
    """L-bracket on the launch stage's slide: foot on the 40 mm table, vertical plate
    (beside the holder's -y face) with the two concentric arc slots about B."""
    rail = p.rail
    pl = rail["plate"]
    ox, oy, oz = pl["stage_centre"][0], pl["stage_centre"][1], pl["slide_top_z"]
    # local = world - origin
    yp0, yp1 = pl["y"][0] - oy, pl["y"][1] - oy
    x0, x1 = pl["x"][0] - ox, pl["x"][1] - ox
    z0, z1 = pl["z"][0] - oz, pl["z"][1] - oz
    B = (rail["centre_B"][0] - ox, rail["centre_B"][1] - oz)
    tb = p.table / 2
    if pl.get("hanging"):
        # the slots lie below the slide top: the foot reaches over to the plate, which hangs from
        # it; the nuts ride on the plate's back, below the foot, between the table and the plate
        foot = _box(min(-tb, x0), max(tb, x1), -tb, yp1, 0.0, p.bracket_foot)
        plate = _box(x0, x1, yp0, yp1, z0, p.bracket_foot)
        part = cq.Workplane("XY").add(foot).union(cq.Workplane("XY").add(plate))
        for xr in (x0 + 2.5, x1 - 2.5):                 # gussets under the foot at the plate's ends
            rib = (cq.Workplane("YZ", origin=(xr - 2.5, 0, 0))
                   .polyline([(max(-tb + 2.0, yp0 - 8.0), 0.0), (yp0, 0.0), (yp0, 0.6 * z0)]).close()
                   .extrude(5.0))
            part = part.union(rib)
    else:
        # the foot stops 6 mm short of the plate so the nuts on the plate's back can ride
        # the slots down to the slide top
        foot = _box(min(-tb, x0), max(tb, x1), -tb, yp0 - 6.0, 0.0, p.bracket_foot)
        plate = _box(x0, x1, yp0, yp1, 0.0, z1)
        part = cq.Workplane("XY").add(foot).union(cq.Workplane("XY").add(plate))
        # two ribs from the foot to the plate, at the plate's ends, clear of the slots (and
        # of the nuts that ride in them on this side)
        for xr in (x0 + 2.5, x1 - 2.5):
            rib = (cq.Workplane("YZ", origin=(xr - 2.5, 0, 0))
                   .polyline([(-tb + 2.0, p.bracket_foot), (yp0, p.bracket_foot), (yp0, min(z1, 0.7 * z1 + 6.0))]).close()
                   .extrude(5.0))
            part = part.union(rib)
    tools: List[cq.Shape] = []
    # mounting holes on the slide
    ph = p.slide_hole_pitch / 2
    for sx in (-ph, ph):
        for sy in (-ph, ph):
            tools.append(cq.Solid.makeCylinder(p.slide_hole_d / 2, p.bracket_foot + 2.0, cq.Vector(sx, sy, -1.0), cq.Vector(0, 0, 1)))
    for s in rail["slots"]:
        a0, a1 = s["angle_from_vertical_deg"]
        tools.append(_arc_slot(B[0], B[1], s["R"], a0, a1, p.slot_w, yp0 - 1.0, yp1 + 1.0).val())
    part = cq.Workplane("XY").add(part.val().cut(*tools).clean())
    if len(part.solids().vals()) != 1:
        raise ValueError(f"the bracket came out as {len(part.solids().vals())} solids")
    return part


def build_all(p: HolderPlan) -> Dict[str, cq.Workplane]:
    return {"holder": build_holder(p), "cyl_key": build_cyl_key(p),
            "collimator_clip": build_collimator_clip(p), "rail_bracket": build_bracket(p)}


# --------------------------------------------------------------------------- export
def generate(layout_json: str | Path, out_dir: str | Path = "generated/opm_launch", stem: str = "opm_launch",
             stl: bool = True, label: Optional[str] = None) -> HolderPlan:
    layout = json.loads(Path(layout_json).read_text())
    p = plan_from_layout(layout, label)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    parts = build_all(p)
    files = {}
    for name, wp in parts.items():
        path = out / f"{stem}_{name}.step"
        cq.exporters.export(wp, str(path))
        files[name + "_step"] = str(path)
        if stl:
            path = out / f"{stem}_{name}.stl"
            cq.exporters.export(wp, str(path), tolerance=0.02, angularTolerance=0.1)
            files[name + "_stl"] = str(path)
    rep = p.report()
    rep["files"] = files
    rep["volumes_mm3"] = {k: round(v.val().Volume(), 1) for k, v in parts.items()}
    (out / f"{stem}_plan.json").write_text(json.dumps(rep, indent=2))
    p.files = files  # type: ignore[attr-defined]
    return p


def _cli(argv: Optional[List[str]] = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="uc2cad opm-launch",
                                 description="dvOPM launch holder + retainers + arc-rail bracket from an opm_layout.json")
    ap.add_argument("layout", help="opm_layout.json written by opm_layout.py")
    ap.add_argument("--out-dir", default="generated/opm_launch")
    ap.add_argument("--stem", default="opm_launch")
    ap.add_argument("--no-stl", action="store_true")
    a = ap.parse_args(argv)
    p = generate(a.layout, a.out_dir, a.stem, stl=not a.no_stl)
    rep = p.report()
    print(json.dumps({k: rep[k] for k in ("rms_thread", "cyl_slot", "collimator", "clamp_screws_xz", "body")}, indent=2))
    for k, v in p.files.items():  # type: ignore[attr-defined]
        print(f"  {k:22s} {v}")


if __name__ == "__main__":
    _cli()
