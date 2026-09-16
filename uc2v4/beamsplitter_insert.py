"""openUC2 V4 kinematic beamsplitter / fluorescence-filter insert.

A fluorescence filter cube routes three beams through one 50 mm cell::

    excitation  >---+
                    |  (dichroic, 45 deg)
        sample  |---+---|  emission >
                    |

It reflects the excitation down to the sample, and passes the returning
fluorescence straight through to the emission port.

This module builds the printable **clamshell** that carries those three
optics on the square-insert interface (MAS-2013 lineage, the same blank
``fold_insert.py`` uses). It is modelled on the released reference pair
PRT-2074 / PRT-2075 (``MAS - 2063 - Insert splitter plus 2 filters``):

- one tall square insert, split at its mid-plane (z = 0) into a **lower** and
  an **upper** printed half. You open it like a book, drop the three optics
  into their seats, close it and pin it -- every seat straddles z = 0, so the
  split plane is what gives you access;
- **three optic ports**, each independently a round disc or a rectangular
  plate, each with its own thickness:
    - ``excitation`` on the +X face (from the light source),
    - ``emission`` on the +Y face (to the camera),
    - ``dichroic`` at ``fold_deg`` (45 deg by default) across the centre;
- the **sample port** on -Y is a plain open bore (the objective looks in);
- **alignment pins** at three corners hold the two halves in register
  (dowels as in the reference, or printed boss/socket).

Coordinates: X and Y are the two horizontal beam axes; +Z is the stack /
split / pin axis (how the clamshell opens). Units mm. With a 45 deg dichroic a
+X excitation beam reflects to -Y; ``handedness=-1`` sends it to +Y instead.

Rectangular optics use ``outline_mm = (width, height)`` where *width* is the
in-plane horizontal and *height* is along the split (Z) axis.

    exc = Plate(thickness_mm=4.0, diameter_mm=25.4)     # exc filter, round
    emi = Plate(thickness_mm=4.0, diameter_mm=25.4)     # emi filter, round
    dic = Plate(thickness_mm=1.0, outline_mm=(25, 25))  # dichroic, square
    lower, upper = build_beamsplitter_insert(
        BeamsplitterParams(excitation=exc, emission=emi, dichroic=dic))
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

try:                                    # works as a package and as a loose script
    from .fold_insert import Plate
    from .interface import SquareInsertInterface, base_plate
except ImportError:                     # pragma: no cover
    from fold_insert import Plate
    from interface import SquareInsertInterface, base_plate


# ---------------------------------------------------------------------------
# ports
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Port:
    """A named optic port: the outward face direction, and a human label."""

    name: str
    axis: tuple[float, float, float]     # unit vector, centre -> outer face

    def vec(self) -> cq.Vector:
        return cq.Vector(*self.axis).normalized()


EXCITATION = Port("excitation", (1.0, 0.0, 0.0))    # +X, from the light source
EMISSION = Port("emission", (0.0, 1.0, 0.0))        # +Y, to the camera
SAMPLE = Port("sample", (0.0, -1.0, 0.0))           # -Y, the objective


@dataclass(frozen=True)
class BeamsplitterParams:
    """Everything about the printed clamshell that is not the cube itself."""

    interface: SquareInsertInterface = field(default_factory=SquareInsertInterface)

    #: The three optics. Any may be None (that port becomes a plain bore, or
    #: for the dichroic, nothing at all).
    excitation: Plate | None = None
    emission: Plate | None = None
    dichroic: Plate | None = None

    #: Dichroic tilt from the emission (through) axis. 45 folds excitation to
    #: the sample; 0 would stand it square (a plain plate beamsplitter).
    fold_deg: float = 45.0
    #: -1 mirrors the fold (excitation -> +Y instead of -Y).
    handedness: int = 1

    #: Total stack height (both halves together). None sizes it to the tallest
    #: optic plus a wall top and bottom.
    thickness_mm: float | None = None

    #: Clear beam bore through the cube; each filter's aperture is this wide.
    beam_diameter_mm: float = 20.0
    #: The lip that actually retains each disc/plate in its seat.
    retaining_lip_mm: float = 1.4
    fit_clearance_mm: float = 0.2
    min_wall_mm: float = 1.2

    #: Alignment pins. "dowel" = a plain through-hole in both halves for a
    #: bought pin; "printed" = a boss on the lower half, a socket in the upper.
    pin_style: str = "dowel"
    pin_diameter_mm: float = 2.0
    pin_length_mm: float = 4.0           # printed boss reach into the upper half
    pin_clearance_mm: float = 0.1
    #: The three corners (of four) that carry pins, as (x, y).
    pin_positions: tuple = ((-16.8, -16.8), (-16.8, 16.8), (16.8, 16.8))

    def optics(self) -> list[tuple[Port, "Plate | None"]]:
        return [(EXCITATION, self.excitation), (EMISSION, self.emission)]


@dataclass
class BeamsplitterPlan:
    params: BeamsplitterParams
    thickness_mm: float = 0.0
    dichroic_extent_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    reflected_dir: tuple[float, float, float] | None = None
    ports: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        def plate(p: Plate | None) -> dict | None:
            if p is None:
                return None
            return {"thickness_mm": p.thickness_mm, "diameter_mm": p.diameter_mm,
                    "outline_mm": list(p.outline_mm or ())}
        pr = self.params
        return {
            "excitation": plate(pr.excitation),
            "emission": plate(pr.emission),
            "dichroic": plate(pr.dichroic),
            "fold_deg": pr.fold_deg,
            "insert_thickness_mm": round(self.thickness_mm, 3),
            "dichroic_extent_mm": [round(v, 3) for v in self.dichroic_extent_mm],
            "reflected_dir": (None if self.reflected_dir is None
                              else [round(v, 4) for v in self.reflected_dir]),
            "beam_diameter_mm": pr.beam_diameter_mm,
            "pin_style": pr.pin_style,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# geometry helpers  (shared by the cutters and the verification harness)
# ---------------------------------------------------------------------------

def reflected_dir(fold_deg: float, handedness: int = 1) -> tuple[float, float, float]:
    """Where a -X excitation beam goes off a dichroic tilted *fold_deg*."""
    a = math.radians(2.0 * fold_deg)
    return (-math.cos(a), -handedness * math.sin(a), 0.0)


def dichroic_solid(plate: Plate, params: BeamsplitterParams,
                   clearance: float = 0.0) -> cq.Solid:
    """The dichroic, stood upright (normal -> -Y) and tilted into the fold."""
    s = plate.solid(clearance).rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90.0)
    return s.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1),
                    params.handedness * params.fold_deg)


def _dichroic_half_extent(plate: Plate, params: BeamsplitterParams,
                          clearance: float) -> tuple[float, float, float]:
    bb = dichroic_solid(plate, params, clearance).BoundingBox()
    return (max(abs(bb.xmin), abs(bb.xmax)),
            max(abs(bb.ymin), abs(bb.ymax)),
            max(abs(bb.zmin), abs(bb.zmax)))


def filter_seat_center(port: Port, plate: Plate,
                       params: BeamsplitterParams) -> float:
    """Distance of the glass centre from the origin, along the port axis.

    The glass sits with its outer face flush to the outline (it beds against
    the cube wall), so its centre is half a thickness in.
    """
    return params.interface.edge_half - plate.thickness_mm / 2.0


def _axis_box(port: Port, along: float, width: float, height: float,
              center_along: float) -> cq.Solid:
    """A box centred on the port axis: *along* thick, *width* horizontal,
    *height* vertical (Z), its centre *center_along* out along the axis.

    Ports are axis-aligned (+-X or +-Y), so this needs no general rotation.
    """
    ax, ay = port.axis[0], port.axis[1]
    if abs(ax) > abs(ay):                       # +-X port: thickness in X
        dx, dy, dz = along, width, height
        cx, cy = center_along * (1 if ax > 0 else -1), 0.0
    else:                                       # +-Y port: thickness in Y
        dx, dy, dz = width, along, height
        cx, cy = 0.0, center_along * (1 if ay > 0 else -1)
    return cq.Solid.makeBox(dx, dy, dz,
                            pnt=cq.Vector(cx - dx / 2.0, cy - dy / 2.0, -dz / 2.0))


def filter_solid(port: Port, plate: Plate, params: BeamsplitterParams,
                 clearance: float = 0.0) -> cq.Solid:
    """The glass itself, posed in its seat (normal along the port axis)."""
    v = port.vec()
    center = filter_seat_center(port, plate, params)
    if plate.diameter_mm is not None:
        r = plate.diameter_mm / 2.0 + clearance
        t = plate.thickness_mm + 2.0 * clearance
        return cq.Solid.makeCylinder(r, t, pnt=v.multiply(center - t / 2.0), dir=v)
    w, h = plate.extents
    return _axis_box(port, plate.thickness_mm + 2.0 * clearance,
                     w + 2.0 * clearance, h + 2.0 * clearance, center)


def _reach(iface: SquareInsertInterface, thickness: float) -> float:
    return iface.edge_half + thickness + 5.0


def _axis_bore(axis: tuple[float, float, float], radius: float, length: float,
               start: float = 0.0) -> cq.Solid:
    v = cq.Vector(*axis).normalized()
    return cq.Solid.makeCylinder(radius, length, pnt=v.multiply(start), dir=v)


def _filter_cutter(port: Port, plate: Plate, params: BeamsplitterParams) -> cq.Solid:
    """Seat pocket (for the glass) + retaining aperture bore, along *port*.

    The pocket opens at the outer face and stops at a lip; the aperture bores
    the rest of the way to the centre. The filter is laid into the open lower
    half at assembly (its seat straddles z = 0), retained inward by the lip
    and outward by the cube wall.
    """
    c = params.fit_clearance_mm
    v = port.vec()
    outer = params.interface.edge_half
    # the pocket spans from a lip just inside the glass out past the face
    inner = filter_seat_center(port, plate, params) - plate.thickness_mm / 2.0 - c
    length = (outer + 0.5) - inner
    center = (inner + outer + 0.5) / 2.0
    if plate.diameter_mm is not None:
        seat_r = plate.diameter_mm / 2.0 + c
        pocket = cq.Solid.makeCylinder(seat_r, length, pnt=v.multiply(inner), dir=v)
    else:
        w, h = plate.extents
        pocket = _axis_box(port, length, w + 2.0 * c, h + 2.0 * c, center)
    aperture = _axis_bore(port.axis, params.beam_diameter_mm / 2.0,
                          outer + 6.0, start=-2.0)
    return pocket.fuse(aperture)


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def plan_beamsplitter(params: BeamsplitterParams | None = None) -> BeamsplitterPlan:
    params = params or BeamsplitterParams()
    if not 0.0 <= params.fold_deg < 90.0:
        raise ValueError(f"fold_deg {params.fold_deg} must be in [0, 90)")
    for opt in (params.excitation, params.emission, params.dichroic):
        if opt is not None:
            opt.validate()

    iface = params.interface
    c = params.fit_clearance_mm
    plan = BeamsplitterPlan(params=params)

    ext = (0.0, 0.0, 0.0)
    if params.dichroic is not None:
        ext = _dichroic_half_extent(params.dichroic, params, c)
        plan.dichroic_extent_mm = ext
        plan.reflected_dir = reflected_dir(params.fold_deg, params.handedness)

    need_z = 2.0 * ext[2]                    # dichroic vertical span
    for _, opt in params.optics():
        if opt is not None:
            need_z = max(need_z, opt.extents[1] + 2 * c)   # filter's own height

    thickness = params.thickness_mm
    if thickness is None:
        thickness = math.ceil((need_z + 2.0 * params.min_wall_mm) * 2.0) / 2.0
    plan.thickness_mm = float(thickness)
    if need_z + 2.0 * params.min_wall_mm > thickness + 1e-9:
        raise ValueError(
            f"the optics need {need_z:.1f} mm of height plus walls; the insert is "
            f"only {thickness:.1f} mm -- raise thickness_mm or shrink the dichroic")

    if params.dichroic is not None:
        limit = iface.shoulder_half - params.min_wall_mm
        if max(ext[0], ext[1]) > limit:
            raise ValueError(
                f"the tilted dichroic reaches +-{max(ext[0], ext[1]):.1f} mm; the "
                f"insert shoulder leaves +-{limit:.1f} mm -- use a smaller dichroic")

    lip = params.retaining_lip_mm
    for port, opt in params.optics():
        if opt is None:
            continue
        clear = min(opt.extents) / 2.0
        if params.beam_diameter_mm / 2.0 > clear - lip:
            plan.warnings.append(
                f"{port.name}: the {params.beam_diameter_mm:g} mm bore leaves under "
                f"{lip} mm of lip on a {2 * clear:.1f} mm optic -- it may fall through")
        plan.ports[port.name] = {"axis": port.axis, "seat_mm": 2 * clear}
    return plan


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def _all_cutters(plan: BeamsplitterPlan) -> list[cq.Solid]:
    params = plan.params
    c = params.fit_clearance_mm
    r = params.beam_diameter_mm / 2.0
    reach = _reach(params.interface, plan.thickness_mm)
    cutters: list[cq.Solid] = []

    if params.dichroic is not None:
        cutters.append(dichroic_solid(params.dichroic, params, c))

    for port, opt in params.optics():
        if opt is not None:
            cutters.append(_filter_cutter(port, opt, params))
        else:
            cutters.append(_axis_bore(port.axis, r, reach))

    cutters.append(_axis_bore(SAMPLE.axis, r, reach))       # sample, always open
    if plan.reflected_dir is not None:
        cutters.append(_axis_bore(plan.reflected_dir, r, reach))
    return cutters


def _half_blanks(plan: BeamsplitterPlan) -> tuple[cq.Workplane, cq.Workplane]:
    """The plain plate cut at z = 0 into (lower, upper) prisms.

    Splitting the plate *before* the optics are hollowed keeps this a clean
    planar cut: booleans on the fully-cut, z-symmetric body drop a whole half.
    """
    params = plan.params
    big = params.interface.edge_half + 15.0

    def slab(z0: float, z1: float) -> cq.Workplane:
        return cq.Workplane("XY").add(cq.Solid.makeBox(
            2 * big, 2 * big, z1 - z0, pnt=cq.Vector(-big, -big, z0)))

    block = base_plate(params.interface, plan.thickness_mm)
    return block.cut(slab(0.0, big)), block.cut(slab(-big, 0.0))


def _pin(lower: cq.Workplane, upper: cq.Workplane, plan: BeamsplitterPlan
         ) -> tuple[cq.Workplane, cq.Workplane]:
    params = plan.params
    t2 = plan.thickness_mm / 2.0
    pd = params.pin_diameter_mm
    for (x, y) in params.pin_positions:
        if params.pin_style == "printed":
            reach = params.pin_length_mm
            boss = cq.Solid.makeCylinder(pd / 2.0, reach,
                                         pnt=cq.Vector(x, y, 0.0), dir=cq.Vector(0, 0, 1))
            socket = cq.Solid.makeCylinder(pd / 2.0 + params.pin_clearance_mm,
                                           reach + params.pin_clearance_mm,
                                           pnt=cq.Vector(x, y, -0.01), dir=cq.Vector(0, 0, 1))
            lower = lower.union(cq.Workplane("XY").add(boss))
            upper = upper.cut(cq.Workplane("XY").add(socket))
        else:  # dowel: one through-hole per half for a bought pin
            hole = cq.Solid.makeCylinder(
                pd / 2.0 + params.pin_clearance_mm, plan.thickness_mm + 2.0,
                pnt=cq.Vector(x, y, -t2 - 1.0), dir=cq.Vector(0, 0, 1))
            lower = lower.cut(cq.Workplane("XY").add(hole))
            upper = upper.cut(cq.Workplane("XY").add(hole))
    return lower.clean(), upper.clean()  # _pin


def build_beamsplitter_insert(params: BeamsplitterParams | None = None,
                              plan: BeamsplitterPlan | None = None
                              ) -> tuple[cq.Workplane, cq.Workplane]:
    """The (lower, upper) printed clamshell halves, in the cube frame."""
    plan = plan or plan_beamsplitter(params)
    lower, upper = _half_blanks(plan)
    for cutter in _all_cutters(plan):
        cw = cq.Workplane("XY").add(cutter)
        lower, upper = lower.cut(cw), upper.cut(cw)
    lower, upper = _pin(lower.clean(), upper.clean(), plan)
    for name, half in (("lower", lower), ("upper", upper)):
        solids = half.solids().vals()
        if not solids:
            raise ValueError(f"the {name} half came out empty -- the optics swallow it")
        if len(solids) > 1:
            plan.warnings.append(
                f"the {name} half is {len(solids)} disconnected pieces; it will not "
                "print as one part. Shrink the bores or the ports")
    return lower, upper


def generate(params: BeamsplitterParams | None = None,
             out_dir: str = "generated", stem: str = "beamsplitter_insert",
             stl: bool = True) -> BeamsplitterPlan:
    """Plan, build and write the lower/upper STEP (+STL) and the plan JSON."""
    import json
    from pathlib import Path

    plan = plan_beamsplitter(params)
    lower, upper = build_beamsplitter_insert(plan=plan)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, half in (("lower", lower), ("upper", upper)):
        cq.exporters.export(half, str(out / f"{stem}_{name}.step"))
        if stl:
            cq.exporters.export(half, str(out / f"{stem}_{name}.stl"), tolerance=0.02)
    (out / f"{stem}_plan.json").write_text(
        json.dumps(plan.report(), indent=2), encoding="utf-8")
    return plan


def _optic_from_args(prefix: str, args) -> Plate | None:
    """Build a Plate from --<prefix>-diam / --<prefix>-w/-h / --<prefix>-thick."""
    thick = getattr(args, f"{prefix}_thick")
    diam = getattr(args, f"{prefix}_diam")
    w = getattr(args, f"{prefix}_w")
    h = getattr(args, f"{prefix}_h")
    if thick is None or (diam is None and w is None):
        return None
    if diam is not None:
        return Plate(thickness_mm=thick, diameter_mm=diam)
    return Plate(thickness_mm=thick, outline_mm=(w, h if h is not None else w))


def _cli(argv: list[str] | None = None) -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Generate the printable clamshell that holds an excitation "
                    "filter, an emission filter and a 45 deg dichroic inside a "
                    "V4 cube. Each optic is round (--*-diam) or rectangular "
                    "(--*-w [--*-h]); give its --*-thick to include it.")
    for prefix, label in (("exc", "excitation filter"), ("emi", "emission filter"),
                          ("dic", "dichroic")):
        g = ap.add_argument_group(label)
        g.add_argument(f"--{prefix}-diam", type=float, default=None,
                       help=f"{label} diameter (round)")
        g.add_argument(f"--{prefix}-w", type=float, default=None,
                       help=f"{label} width (rectangular)")
        g.add_argument(f"--{prefix}-h", type=float, default=None,
                       help=f"{label} height along the split axis (defaults to width)")
        g.add_argument(f"--{prefix}-thick", type=float, default=None,
                       help=f"{label} thickness -- REQUIRED to include this optic")
    ap.add_argument("--fold", type=float, default=45.0, help="dichroic tilt (deg)")
    ap.add_argument("--handedness", type=int, default=1, choices=[1, -1],
                    help="reflect excitation to -Y (1) or +Y (-1)")
    ap.add_argument("--beam", type=float, default=20.0, help="clear beam bore diameter")
    ap.add_argument("--thickness", type=float, default=None,
                    help="total stack height (auto-sized when omitted)")
    ap.add_argument("--pins", default="dowel", choices=["dowel", "printed", "none"])
    ap.add_argument("--out-dir", default="generated")
    ap.add_argument("--stem", default="beamsplitter_insert")
    args = ap.parse_args(argv)

    params = BeamsplitterParams(
        excitation=_optic_from_args("exc", args),
        emission=_optic_from_args("emi", args),
        dichroic=_optic_from_args("dic", args),
        fold_deg=args.fold, handedness=args.handedness,
        beam_diameter_mm=args.beam, thickness_mm=args.thickness,
        pin_positions=() if args.pins == "none" else BeamsplitterParams.pin_positions,
        pin_style="printed" if args.pins == "printed" else "dowel")
    plan = generate(params, out_dir=args.out_dir, stem=args.stem)
    print(json.dumps(plan.report(), indent=2))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        _cli()
    else:                                   # no args: build the reference set
        import json

        plan = generate(BeamsplitterParams(
            excitation=Plate(thickness_mm=4.0, diameter_mm=25.4),
            emission=Plate(thickness_mm=4.0, diameter_mm=25.4),
            dichroic=Plate(thickness_mm=1.0, outline_mm=(25.0, 25.0))))
        print(json.dumps(plan.report(), indent=2))
