"""Verification harness for the 1x1 inserts: fold_insert.py and sm1_adapter.py.

Checks the things that would bite on the bench:

1. each insert is exactly one solid, inside the cell envelope;
2. the nominal optic drops into its slot without touching the holder, and an
   oversized one does not (the pocket is a fit, not a cavern);
3. the plate can still be slid in from the +Y face (the slot is open all the
   way up);
4. every beam leg is actually bored — a ray along it meets no material;
5. the SM1 thread's crest and root radii, its pitch, and its stop shoulder
   measure back out of the geometry.

Usage:
    uv run --with cadquery python check_inserts.py
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).parent


def load(name: str):
    pkg = HERE / "uc2v4"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    spec = importlib.util.spec_from_file_location(name, pkg / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fi = load("fold_insert")
sm1 = load("sm1_adapter")
bs = load("beamsplitter_insert")

# The plate cases: the fluorescence dichroic, a 1" fold mirror, a round filter
# standing square across the beam.
PLATES = [
    ("DMLP505 dichroic 25.2x35.6x1.05, folding, transmissive",
     fi.Plate(thickness_mm=1.05, outline_mm=(35.6, 25.2)),
     fi.FoldInsertParams(transmissive=True)),
    ("Ø25.4 x 6 mirror at 45 deg",
     fi.Plate(thickness_mm=6.0, diameter_mm=25.4),
     fi.FoldInsertParams()),
    ("Ø25 x 3.5 filter square across the beam",
     fi.Plate(thickness_mm=3.5, diameter_mm=25.0),
     fi.FoldInsertParams(fold_deg=0.0, transmissive=True)),
    ("Ø12.7 x 1 pellicle at 30 deg",
     fi.Plate(thickness_mm=1.0, diameter_mm=12.7),
     fi.FoldInsertParams(fold_deg=30.0, transmissive=True, beam_diameter_mm=8.0)),
]


def solid_of(wp: cq.Workplane) -> cq.Solid:
    vals = wp.solids().vals()
    s = vals[0]
    for extra in vals[1:]:
        s = s.fuse(extra)
    return s


def posed_plate(plate, plan, clearance: float = 0.0, shift=(0.0, 0.0, 0.0)) -> cq.Solid:
    body = plate.solid(clearance)
    if plan.params.fold_deg:
        body = body.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), plan.params.fold_deg)
    return body.translate(cq.Vector(*shift))


def ray_clear(solid: cq.Solid, direction, radius: float, length: float) -> float:
    """Material volume inside a cylinder of *radius* along *direction*."""
    v = cq.Vector(*direction).normalized()
    probe = cq.Solid.makeCylinder(radius, length, pnt=cq.Vector(0, 0, 0), dir=v)
    return solid.intersect(probe).Volume()


def check_fold(name, plate, params) -> bool:
    print(f"=== {name}")
    plan = fi.plan_fold_insert(plate, params)
    part = fi.build_fold_insert(plate, plan=plan)
    ok = True

    n = len(part.solids().vals())
    print(f"  solids: {n}", "OK" if n == 1 else "FAIL")
    ok &= n == 1
    body = solid_of(part)

    iface = params.interface
    bb = body.BoundingBox()
    span = max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax))
    inside = span <= iface.edge_half + 1e-6
    print(f"  envelope: {span:.3f} <= {iface.edge_half:.3f}", "OK" if inside else "FAIL")
    ok &= inside
    tall = abs(bb.zlen - plan.thickness_mm) < 1e-6
    print(f"  thickness: {bb.zlen:.3f} == {plan.thickness_mm:.3f}", "OK" if tall else "FAIL")
    ok &= tall

    clash = body.intersect(posed_plate(plate, plan)).Volume()
    print(f"  nominal plate vs holder: {clash:.6f} mm^3", "OK" if clash < 1e-3 else "FAIL")
    ok &= clash < 1e-3

    grip = body.intersect(posed_plate(plate, plan, params.fit_clearance_mm * 3.0)).Volume()
    print(f"  slot snugness (oversized plate must clash): {grip:.4f} mm^3",
          "OK" if grip > 1e-3 else "FAIL")
    ok &= grip > 1e-3

    # Insertability: sweep the plate up and out of the +Y face; nothing may stand
    # in the way. Built independently of the generator's own sweep.
    swept = None
    travel = iface.edge_half + 6.0
    for i in range(12):
        step = posed_plate(plate, plan, shift=(0.0, travel * i / 11.0, 0.0))
        swept = step if swept is None else swept.fuse(step)
    corridor = body.intersect(swept).Volume()
    print(f"  slot open to the +Y face: {corridor:.6f} mm^3 obstructing",
          "OK" if corridor < 1e-3 else "FAIL")
    ok &= corridor < 1e-3

    legs = [("entry", (0, 0, -1))]
    if plan.exit_dir is not None:
        legs.append(("fold", plan.exit_dir))
    if params.transmissive or plan.exit_dir is None:
        legs.append(("through", (0, 0, 1)))
    for leg, direction in legs:
        blocked = ray_clear(body, direction, params.beam_diameter_mm / 2.0 - 0.05,
                            iface.edge_half + plan.thickness_mm)
        print(f"  {leg} leg clear: {blocked:.6f} mm^3", "OK" if blocked < 1e-3 else "FAIL")
        ok &= blocked < 1e-3

    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def check_refusals() -> bool:
    print("=== refusals")
    ok = True
    cases = [
        ("a plate too long for the cell",
         fi.Plate(thickness_mm=2.0, outline_mm=(20.0, 60.0)), fi.FoldInsertParams()),
        ("a plate deeper than the insert it was given",
         fi.Plate(thickness_mm=2.0, diameter_mm=25.4),
         fi.FoldInsertParams(thickness_mm=10.0)),
        ("a fold of 90 deg, which never reaches the plate",
         fi.Plate(thickness_mm=2.0, diameter_mm=12.7), fi.FoldInsertParams(fold_deg=90.0)),
    ]
    for label, plate, params in cases:
        try:
            fi.plan_fold_insert(plate, params)
        except ValueError as exc:
            print(f"  {label}: refused — {str(exc)[:70]}", "OK")
        else:
            print(f"  {label}: NOT refused", "FAIL")
            ok = False
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def check_sm1() -> bool:
    print("=== SM1 adapter, with a Ø22 stop shoulder")
    params = sm1.SM1AdapterParams(clear_aperture_mm=22.0)
    plan = sm1.plan_sm1_adapter(params)
    part = sm1.build_sm1_adapter(plan=plan)
    ok = True

    n = len(part.solids().vals())
    print(f"  solids: {n}", "OK" if n == 1 else "FAIL")
    ok &= n == 1
    body = solid_of(part)

    # A plain SM1 barrel (the major Ø) must pass down to the shoulder without
    # touching anything but the thread crests, which it is supposed to bite.
    t2 = params.thickness_mm / 2.0
    depth = t2 - plan.stop_z_mm
    barrel = cq.Solid.makeCylinder(params.crest_r - 0.02, depth,
                                   pnt=cq.Vector(0, 0, plan.stop_z_mm), dir=cq.Vector(0, 0, 1))
    clash = body.intersect(barrel).Volume()
    print(f"  Ø{2 * params.crest_r:.2f} barrel to the shoulder: {clash:.6f} mm^3",
          "OK" if clash < 1e-3 else "FAIL")
    ok &= clash < 1e-3

    # The thread is real: a ring at the crest radius must find material inside
    # the threaded span and none above the chamfered mouth.
    def ring_volume(z: float, r_in: float, r_out: float, dz: float = 0.2) -> float:
        outer = cq.Solid.makeCylinder(r_out, dz, pnt=cq.Vector(0, 0, z - dz / 2))
        inner = cq.Solid.makeCylinder(r_in, dz + 1.0, pnt=cq.Vector(0, 0, z - dz / 2 - 0.5))
        return body.intersect(outer.cut(inner)).Volume()

    mid = sum(plan.thread_span_mm) / 2.0
    crest = ring_volume(mid, params.crest_r, params.bore_r)
    print(f"  thread crests at z={mid:.2f}: {crest:.4f} mm^3",
          "OK" if crest > 1e-2 else "FAIL")
    ok &= crest > 1e-2
    mouth = ring_volume(t2 - 0.1, params.crest_r, params.bore_r)
    print(f"  chamfered mouth clear: {mouth:.4f} mm^3", "OK" if mouth < crest else "FAIL")
    ok &= mouth < crest

    # Pitch: one turn of the helix must lift the crest by exactly the pitch.
    turns = (plan.thread_span_mm[1] - plan.thread_span_mm[0]) / params.pitch_mm
    good = abs(turns - params.turns) < 1e-6 and abs(params.pitch_mm - 0.635) < 1e-9
    print(f"  {turns:.2f} turns at {params.pitch_mm} mm pitch", "OK" if good else "FAIL")
    ok &= good

    # The stop shoulder holds the optic where the plan says it does.
    below = ring_volume(plan.stop_z_mm - 0.3, params.clear_aperture_mm / 2.0, params.bore_r)
    print(f"  stop shoulder at z={plan.stop_z_mm:.2f}: {below:.4f} mm^3",
          "OK" if below > 1e-2 else "FAIL")
    ok &= below > 1e-2

    bb = body.BoundingBox()
    span = max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax))
    inside = span <= params.interface.edge_half + 1e-6
    print(f"  envelope: {span:.3f} <= {params.interface.edge_half:.3f}",
          "OK" if inside else "FAIL")
    ok &= inside

    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def check_beamsplitter() -> bool:
    print("=== beamsplitter clamshell: Ø25.4 exc + Ø25.4 emi + 25x25 dichroic")
    exc = fi.Plate(thickness_mm=4.0, diameter_mm=25.4)
    emi = fi.Plate(thickness_mm=4.0, diameter_mm=25.4)
    dic = fi.Plate(thickness_mm=1.0, outline_mm=(25.0, 25.0))
    params = bs.BeamsplitterParams(excitation=exc, emission=emi, dichroic=dic,
                                   beam_diameter_mm=18.0)
    plan = bs.plan_beamsplitter(params)
    lower, upper = bs.build_beamsplitter_insert(plan=plan)
    ok = True

    nl, nu = len(lower.solids().vals()), len(upper.solids().vals())
    print(f"  solids: lower={nl} upper={nu}", "OK" if nl == nu == 1 else "FAIL")
    ok &= nl == nu == 1
    lo, up = solid_of(lower), solid_of(upper)

    overlap = lo.intersect(up).Volume()
    print(f"  half-to-half overlap: {overlap:.6f} mm^3", "OK" if overlap < 1e-6 else "FAIL")
    ok &= overlap < 1e-6

    body = lo.fuse(up)
    bb = body.BoundingBox()
    span = max(abs(bb.xmin), abs(bb.xmax), abs(bb.ymin), abs(bb.ymax))
    inside = span <= params.interface.edge_half + 1e-6
    print(f"  envelope: {span:.3f} <= {params.interface.edge_half:.3f}",
          "OK" if inside else "FAIL")
    ok &= inside
    tall = abs(bb.zlen - plan.thickness_mm) < 1e-6
    print(f"  thickness: {bb.zlen:.3f} == {plan.thickness_mm:.3f}", "OK" if tall else "FAIL")
    ok &= tall

    optics = [("dichroic", bs.dichroic_solid(dic, params, 0.0),
               bs.dichroic_solid(dic, params, params.fit_clearance_mm * 3.0)),
              ("excitation", bs.filter_solid(bs.EXCITATION, exc, params, 0.0),
               bs.filter_solid(bs.EXCITATION, exc, params, params.fit_clearance_mm * 3.0)),
              ("emission", bs.filter_solid(bs.EMISSION, emi, params, 0.0),
               bs.filter_solid(bs.EMISSION, emi, params, params.fit_clearance_mm * 3.0))]
    for name, nominal, fat in optics:
        clash = body.intersect(nominal).Volume()
        print(f"  {name} nominal vs holder: {clash:.5f} mm^3",
              "OK" if clash < 1e-3 else "FAIL")
        ok &= clash < 1e-3
        grip = body.intersect(fat).Volume()
        print(f"  {name} seat snugness (oversized must clash): {grip:.3f} mm^3",
              "OK" if grip > 1e-3 else "FAIL")
        ok &= grip > 1e-3

    def corridor(seat_solid) -> float:
        swept = None
        for i in range(10):
            step = seat_solid.translate(cq.Vector(0, 0, params.interface.edge_half * i / 9.0))
            swept = step if swept is None else swept.fuse(step)
        return lo.intersect(swept).Volume()
    for name, nominal, _ in optics:
        obstruct = corridor(nominal)
        print(f"  {name} liftable from split: {obstruct:.5f} mm^3 obstructing",
              "OK" if obstruct < 1e-3 else "FAIL")
        ok &= obstruct < 1e-3

    legs = [("excitation in", (1, 0, 0)), ("sample", (0, -1, 0)),
            ("emission out", (0, 1, 0)), ("reflected", plan.reflected_dir)]
    for leg, direction in legs:
        blocked = ray_clear(body, direction, params.beam_diameter_mm / 2.0 - 0.05,
                            params.interface.edge_half + plan.thickness_mm)
        print(f"  {leg} leg clear: {blocked:.6f} mm^3", "OK" if blocked < 1e-3 else "FAIL")
        ok &= blocked < 1e-3

    for (x, y) in params.pin_positions:
        pin = cq.Solid.makeCylinder(params.pin_diameter_mm / 2.0, plan.thickness_mm,
                                    pnt=cq.Vector(x, y, -plan.thickness_mm / 2.0),
                                    dir=cq.Vector(0, 0, 1))
        in_lo = lo.intersect(pin).Volume()
        in_up = up.intersect(pin).Volume()
        clear = in_lo < 1e-3 and in_up < 1e-3
        print(f"  pin hole ({x:+.1f},{y:+.1f}) clear both halves: "
              f"lo={in_lo:.4f} up={in_up:.4f}", "OK" if clear else "FAIL")
        ok &= clear

    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def check_beamsplitter_shapes() -> bool:
    print("=== beamsplitter shape mix: square exc, round emi, round dichroic")
    params = bs.BeamsplitterParams(
        excitation=fi.Plate(thickness_mm=2.0, outline_mm=(20.0, 20.0)),
        emission=fi.Plate(thickness_mm=3.5, diameter_mm=25.0),
        dichroic=fi.Plate(thickness_mm=1.0, diameter_mm=25.4),
        beam_diameter_mm=16.0)
    plan = bs.plan_beamsplitter(params)
    lower, upper = bs.build_beamsplitter_insert(plan=plan)
    nl, nu = len(lower.solids().vals()), len(upper.solids().vals())
    ok = nl == nu == 1
    print(f"  solids: lower={nl} upper={nu}", "OK" if ok else "FAIL")
    for w in plan.warnings:
        print(f"  note: {w}")
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def check_beamsplitter_refusals() -> bool:
    print("=== beamsplitter refusals")
    ok = True
    cases = [
        ("a dichroic too tall for a forced-thin insert",
         bs.BeamsplitterParams(dichroic=fi.Plate(thickness_mm=1.0, outline_mm=(40, 40)),
                               thickness_mm=12.0)),
        ("a dichroic wider than the shoulder",
         bs.BeamsplitterParams(dichroic=fi.Plate(thickness_mm=1.0, outline_mm=(60, 10)))),
        ("a 90 deg fold",
         bs.BeamsplitterParams(dichroic=fi.Plate(thickness_mm=1.0, diameter_mm=20.0),
                               fold_deg=90.0)),
    ]
    for label, params in cases:
        try:
            bs.plan_beamsplitter(params)
        except ValueError as exc:
            print(f"  {label}: refused — {str(exc)[:64]}", "OK")
        else:
            print(f"  {label}: NOT refused", "FAIL")
            ok = False
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    results = [check_fold(*case) for case in PLATES]
    results.append(check_refusals())
    results.append(check_sm1())
    results.append(check_beamsplitter())
    results.append(check_beamsplitter_shapes())
    results.append(check_beamsplitter_refusals())
    print(f"{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
