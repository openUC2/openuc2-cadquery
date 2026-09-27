"""Verification harness for the OPM plate generator (uc2v4/opm_plates.py).

Checks the things that would bite on the bench:

1. the automatic tie-rod rule puts the rods exactly where the released V04
   plates have them (3x3, 3x6, 3x7+1x1, 3x8+1x1, 3x3+1x2; measured from the
   Inventor STEPs, drawing tolerance 0.1 mm);
2. for a spread of layouts -- plain rectangle, the released L, extra units on
   all four sides with a port and an aperture, a ring with an enclosed hole, a
   single cell -- each plate is one valid solid of the right extent, carries
   4 M3 holes per cell and a pocket per cell, the rods pass straight through
   both plates, the counterbores / sleeve-nut recesses / pockets / port take
   their hardware, and only the outward face is chamfered;
3. against the released PRT-1052 top / PRT-1051 base STEPs (when
   ``extracted/plates/`` is present): volume, every cylindrical feature
   matched within 0.11 mm, and -- with trimesh -- the surface deviation;
4. impossible layouts and misplaced features are refused with a message.

Usage:
    uv run --with cadquery python check_opm_plates.py
    uv run --with cadquery --with trimesh --with rtree --with scipy python check_opm_plates.py
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

HERE = Path(__file__).parent
REF = HERE / "extracted" / "plates"


def load(name: str):
    pkg = HERE / "uc2v4"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    spec = importlib.util.spec_from_file_location(name, pkg / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


op = load("opm_plates")

# Tie rods of the released plates, read off their STEP exports (cylinders of
# r 1.7 / 2.25 along z). PRT-1045 predates MAS-1003's 50.1 row pitch.
RELEASED_RODS = [
    ("PRT-1045 TOPPLA3X3", "3x3", "auto", (50.0, 50.0),
     [(-20.5, -20.5), (-20.5, 120.5), (120.5, -20.5), (120.5, 120.5)]),
    ("PRT-1026/1027 3X6", "3x6", "auto", (50.0, 50.1),
     [(-20.5, -20.5), (-20.5, 129.8), (-20.5, 271.0),
      (120.5, -20.5), (120.5, 129.8), (120.5, 271.0)]),
    ("PRT-1053/1054 3X7+1X1", "3x7+1x1@-1,0", "auto", (50.0, 50.1),
     [(-20.5, -20.5), (-20.5, 70.6), (-20.5, 230.0), (-20.5, 321.1),
      (120.5, -20.5), (120.5, 70.6), (120.5, 230.0), (120.5, 321.1)]),
    ("PRT-1051/1052 3X8+1X1", "3x8+1x1@-1,0", "auto", (50.0, 50.1),
     [(-20.5, -20.5), (-20.5, 120.7), (-20.5, 230.0), (-20.5, 371.2),
      (120.5, -20.5), (120.5, 120.7), (120.5, 230.0), (120.5, 371.2)]),
    ("PRT-1047/1048 3X3+1X2", "3x3@0,3+1x2@1,1", "outline", (50.0, 50.1),
     [(-20.5, 129.75), (-20.5, 271.05), (29.5, 29.55), (70.5, 29.55),
      (120.5, 129.75), (120.5, 271.05)]),
]


def solid_of(wp: cq.Workplane) -> cq.Solid:
    solids = wp.solids().vals()
    return solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)


def clash(solid: cq.Shape, probe: cq.Shape) -> float:
    """Volume of material inside the probe (0 = the probe fits)."""
    return solid.intersect(probe).Volume()


def z_cylinders(shape: cq.Shape) -> set:
    """Distinct cylindrical features along z: (r, x, y, zmin, zmax), rounded."""
    out = set()
    for f in shape.Faces():
        s = BRepAdaptor_Surface(f.wrapped)
        if s.GetType() != GeomAbs_Cylinder:
            continue
        c = s.Cylinder()
        if abs(c.Axis().Direction().Z()) < 0.999:
            continue
        loc, bb = c.Axis().Location(), f.BoundingBox()
        out.add((round(c.Radius(), 3), round(loc.X(), 2), round(loc.Y(), 2),
                 round(bb.zmin, 2), round(bb.zmax, 2)))
    return out


def ok(flag: bool) -> str:
    return "OK" if flag else "FAIL"


# ---------------------------------------------------------------------------

def check_rod_rule() -> bool:
    print("=== tie-rod rule vs the released plates")
    good = True
    for part, layout, mode, pitch, ref in RELEASED_RODS:
        geo = op.PlateGeometry(pitch_mm=pitch)
        plan = op.plan_opm_plates(op.OpmPlateSpec(
            layout=op.PlateLayout.parse(layout), tie_rods=mode, geometry=geo))
        mine = sorted(xy for _, xy, _ in plan.tie_rods)
        ref = sorted(ref)
        match = len(mine) == len(ref) and all(
            any(math.dist(m, r) <= 0.1 + 1e-9 for m in mine) for r in ref)
        worst = max((min(math.dist(m, r) for m in mine) for r in ref), default=0.0)
        print(f"  {part:24s} {layout:18s} {len(mine)} rods, worst {worst:.3f} mm", ok(match))
        good &= match
    print(f"  --> {'PASS' if good else 'FAIL'}\n")
    return good


def check_layout(label: str, spec) -> bool:
    print(f"=== {label}")
    plan = op.plan_opm_plates(spec)
    parts = op.build_opm_plates(plan)
    g = plan.geometry
    zb, zt = g.z_bottom, g.z_top
    top, base = solid_of(parts["top"]), solid_of(parts["base"])
    good = True
    print("  layout:", " / ".join(spec.layout.to_ascii().splitlines()))

    for which, s in (("top", top), ("base", base)):
        n = len(parts[which].solids().vals())
        valid = s.isValid()
        print(f"  {which}: {n} solid, valid={valid}", ok(n == 1 and valid))
        good &= n == 1 and valid

        bb = s.BoundingBox()
        x0, y0, x1, y1 = plan.extent()
        fit = all(abs(a - b) < 1e-3 for a, b in
                  ((bb.xmin, x0), (bb.ymin, y0), (bb.xmax, x1), (bb.ymax, y1),
                   (bb.zmin, zb), (bb.zmax, zt)))
        print(f"    extent {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} == cells x pitch", ok(fit))
        good &= fit

        feats = z_cylinders(s)
        m3 = {(x, y) for r, x, y, *_ in feats if abs(r - g.m3_hole_d_mm / 2) < 1e-3}
        want = 4 * len(plan.centres)
        print(f"    M3 holes {len(m3)} == 4 x {len(plan.centres)} cells", ok(len(m3) == want))
        good &= len(m3) == want

        ports_here = {p.cell for p in spec.ports if p.plate == which}
        pockets = {(x, y) for r, x, y, *_ in feats if abs(r - g.pocket_d_mm / 2) < 1e-3}
        want_p = len(plan.centres) - len(ports_here) if spec.pockets else 0
        print(f"    pockets {len(pockets)} == {want_p}", ok(len(pockets) == want_p))
        good &= len(pockets) == want_p

        # every pocket takes a slightly smaller disc from the cube side
        inner = zb if which == "top" else zt
        into = 1.0 if which == "top" else -1.0
        worst = 0.0
        for cell, (x, y) in plan.centres.items():
            if cell in ports_here or not spec.pockets:
                continue
            d = g.pocket_depth_mm - 0.05
            z0 = min(inner, inner + into * d)
            worst = max(worst, clash(s, op._cyl(g.pocket_d_mm / 2 - 0.1, x, y, z0, z0 + d)))
        print(f"    pockets clear: {worst:.2e} mm^3", ok(worst < 1e-6))
        good &= worst < 1e-6

        # outward face chamfered, inner face sharp: probe 0.3 mm inside an edge
        mid_cell = min(plan.centres, key=lambda c: (c[1], c[0]))
        cx, cy = plan.centres[mid_cell]
        ey = cy - g.pitch_mm[1] / 2 + 0.3                  # 0.3 mm in from the -y edge
        outer = zt if which == "top" else zb
        near_outer = cq.Vector(cx, ey, outer - 0.2 * into)     # 0.2 below the outward face
        near_inner = cq.Vector(cx, ey, inner + 0.2 * into)     # 0.2 above the cube face
        chamfered = not s.isInside(near_outer) and s.isInside(near_inner)
        edge_open = (mid_cell[0], mid_cell[1] - 1) not in plan.centres
        if edge_open:
            print("    outward face chamfered, cube face sharp", ok(chamfered))
            good &= chamfered

    # tie rods: a slightly thinner rod passes straight through both plates, and
    # each end's hardware seats
    rods_ok = True
    for rod, (x, y), _ in plan.tie_rods:
        through = op._cyl(1.5, x, y, zb - 1, zt + 1)                 # M3 = 3.0
        c1 = clash(top, through) + clash(base, through)
        head = op._cyl(g.top_rod_cbore_d_mm / 2 - 0.25, x, y,          # ISO 4762 head 5.5
                       zt - g.top_rod_cbore_depth_mm + 0.05, zt)
        nut = op._cyl(g.base_recess_r_mm - 0.25, x, y, zb,
                      zb + g.base_recess_depth_mm - 0.05)
        shank = op._cyl(g.base_rod_d_mm / 2 - 0.2, x, y, zb, zt)       # sleeve shank 4
        c2 = clash(top, head) + clash(base, nut) + clash(base, shank)
        rods_ok &= c1 < 1e-6 and c2 < 1e-6
    print(f"  {len(plan.tie_rods)} tie rods pass through both plates, heads/nuts seat",
          ok(rods_ok))
    good &= rods_ok

    for p in spec.ports:
        s = top if p.plate == "top" else base
        x, y = plan.centres[p.cell]
        clear = clash(s, op._cyl(p.aperture_d_mm / 2 - 0.1, x, y, zb - 1, zt + 1))
        lip = clash(s, op._cyl(p.aperture_d_mm / 2 + 0.3, x, y, zb - 1, zt + 1))
        inner = zb if p.plate == "top" else zt
        d = 2.5
        z0 = inner if p.plate == "top" else inner - d
        thread = clash(s, op._cyl(p.thread_minor_d_mm / 2 - 0.05, x, y, z0, z0 + d))
        crest = clash(s, op._cyl(p.thread_major_d_mm / 2, x, y, z0, z0 + d))
        port_ok = clear < 1e-6 and lip > 0.5 and thread < 1e-6 and crest > 1.0
        print(f"  port {p.cell}: aperture clear, lip {lip:.1f} mm^3, thread bore clear, "
              f"thread flank {crest:.1f} mm^3", ok(port_ok))
        good &= port_ok

    for a in spec.apertures:
        x, y = plan.centres[a.cell]
        for which in (("top", "base") if a.plate == "both" else (a.plate,)):
            s = top if which == "top" else base
            c = clash(s, op._cyl(a.d_mm / 2 - 0.05, x, y, zb - 1, zt + 1))
            print(f"  aperture {a.cell} d{a.d_mm:g} in the {which} plate: {c:.2e} mm^3",
                  ok(c < 1e-6))
            good &= c < 1e-6

    print(f"  stack: top plate +{plan.top_offset_z_mm:g} mm, "
          f"{plan.report()['hardware']['tie_rod_screw']}")
    print(f"  --> {'PASS' if good else 'FAIL'}\n")
    return good


def check_released() -> bool:
    top_ref = REF / "PRT_-_1052_-_TOPPLA3X8+1X1_-_V04.step"
    base_ref = REF / "PRT_-_1051_-_BASPLA3X8+1X1_-_V04.step"
    print("=== the released FLIM 488 pair: PRT-1052 top / PRT-1051 base")
    if not (top_ref.exists() and base_ref.exists()):
        print(f"  reference STEPs not found in {REF} -- skipped\n")
        return True
    # PRT-1051 also carries module-specific holes (feet pockets, two 4.2 holes)
    # that are not part of the generic recipe; add them so the diff isolates
    # what the generator itself does. Its 2.1 mm slots stay unmatched.
    base_extras = tuple(
        [op.CustomHole(d_mm=4.2, cell=c) for c in ((0, 1), (2, 1))]
        + [op.CustomHole(d_mm=10.0, offset_mm=xy, depth_mm=2.4, plate="base", face="outer")
           for xy in ((14.0, 263.7), (22.0, 309.7), (78.0, 309.7), (86.0, 263.7))])
    spec = op.released_3x8_1x1()
    spec = op.OpmPlateSpec(layout=spec.layout, ports=spec.ports, holes=base_extras)
    parts = op.build_opm_plates(spec)
    good = True
    for which, ref_path, allowed in (("top", top_ref, set()),
                                     ("base", base_ref, {1.05})):
        mine = solid_of(parts[which])
        ref = cq.importers.importStep(str(ref_path)).val()
        vm, vr = mine.Volume(), ref.Volume()
        dv = (vm - vr) / vr * 100
        print(f"  {which}: volume {vm:.1f} vs {vr:.1f} mm^3 ({dv:+.3f} %), "
              f"faces {len(mine.Faces())} vs {len(ref.Faces())}")
        fm, fr = z_cylinders(mine), z_cylinders(ref)

        def matched(f, pool):
            return any(abs(f[0] - p[0]) < 0.01 and abs(f[1] - p[1]) <= 0.11
                       and abs(f[2] - p[2]) <= 0.11 and abs(f[3] - p[3]) < 0.02
                       and abs(f[4] - p[4]) < 0.02 for p in pool)

        miss_ref = sorted(f for f in fr if not matched(f, fm))
        miss_mine = sorted(f for f in fm if not matched(f, fr))
        unexpected = [f for f in miss_ref if f[0] not in allowed]
        print(f"    cylindrical features: {len(fr) - len(miss_ref)}/{len(fr)} of the "
              f"reference matched; {len(miss_mine)} of mine unmatched")
        for f in miss_ref[:8]:
            tag = "expected (2.1 mm slot, module-specific)" if f[0] in allowed else "MISSING"
            print(f"      ref r={f[0]} at ({f[1]}, {f[2]}) z[{f[3]}, {f[4]}]  {tag}")
        for f in miss_mine[:8]:
            print(f"      mine r={f[0]} at ({f[1]}, {f[2]}) z[{f[3]}, {f[4]}]  EXTRA")
        feat_ok = not unexpected and not miss_mine
        vol_ok = abs(dv) < (0.05 if which == "top" else 0.2)
        print(f"    features {ok(feat_ok)}, volume {ok(vol_ok)}")
        good &= feat_ok and vol_ok
        _mesh_deviation(mine, ref)
    print(f"  --> {'PASS' if good else 'FAIL'}\n")
    return good


def _mesh_deviation(mine: cq.Shape, ref: cq.Shape) -> None:
    try:
        import numpy as np
        import trimesh
    except ImportError:
        print("    (surface deviation needs trimesh/rtree/scipy -- skipped)")
        return

    def mesh(s):
        v, t = s.tessellate(0.01)
        m = trimesh.Trimesh(vertices=[p.toTuple() for p in v], faces=t)
        m.merge_vertices()
        return m

    ma, mb = mesh(mine), mesh(ref)
    for label, src, dst in (("mine->ref", ma, mb), ("ref->mine", mb, ma)):
        pts, _ = trimesh.sample.sample_surface(src, 40000)
        _, dist, _ = trimesh.proximity.closest_point(dst, pts)
        far = pts[dist > 0.15]
        where = ""
        if len(far):
            lo, hi = far.min(axis=0), far.max(axis=0)
            where = (f"; >0.15 mm only in x[{lo[0]:.0f},{hi[0]:.0f}] "
                     f"y[{lo[1]:.0f},{hi[1]:.0f}]")
        print(f"    deviation {label}: median {np.median(dist):.4f}  p99 "
              f"{np.percentile(dist, 99):.4f}  max {dist.max():.3f} mm{where}")


def check_refusals() -> bool:
    print("=== refusals")
    good = True
    cases = [
        ("two separate islands", lambda: op.PlateLayout.parse("1x1+1x1@2,0")),
        ("cells touching only at a corner", lambda: op.PlateLayout.parse("1x1+1x1@1,1")),
        ("extra block without a position", lambda: op.PlateLayout.parse("3x8+1x1")),
        ("port outside the layout", lambda: op.plan_opm_plates(op.OpmPlateSpec(
            layout=op.PlateLayout.parse("3x3"), ports=(op.Port(cell=(5, 5)),)))),
        ("tie rod outside the layout", lambda: op.plan_opm_plates(op.OpmPlateSpec(
            layout=op.PlateLayout.parse("3x3"), tie_rods=(op.TieRod((-1, 0), "sw"),)))),
        ("tie rod with a bad corner", lambda: op.TieRod((0, 0), "up")),
        ("zero cube layers", lambda: op.plan_opm_plates(op.OpmPlateSpec(
            layout=op.PlateLayout.parse("2x2"), layers=0))),
        ("port too big for its cell", lambda: op.plan_opm_plates(op.OpmPlateSpec(
            layout=op.PlateLayout.parse("2x2"),
            ports=(op.Port(cell=(0, 0), relief_d_mm=46.0),)))),
    ]
    for label, fn in cases:
        try:
            fn()
        except ValueError as exc:
            print(f"  {label}: refused -- {str(exc)[:70]}", "OK")
        else:
            print(f"  {label}: NOT refused", "FAIL")
            good = False
    print(f"  --> {'PASS' if good else 'FAIL'}\n")
    return good


def check_interfaces() -> bool:
    """Spec string, ASCII art and the optikit dict surface agree."""
    print("=== layout parsing and the dict (optikit) surface")
    good = True
    a = op.PlateLayout.parse("3x8+1x1@-1,0")
    b = op.PlateLayout.from_ascii(a.to_ascii())
    same = a.cells == b.cells and a.core == b.core
    print(f"  spec -> ASCII -> layout round trip ({len(a.cells)} cells, "
          f"{len(a.extra)} extra)", ok(same))
    good &= same and len(a.cells) == 25 and a.extra == {(-1, 0)}
    d = {"layout": "3x3+1x1@-1,1", "layers": 1,
         "ports": [{"cell": [1, 2]}], "apertures": [{"cell": [0, 0], "d_mm": 20, "plate": "base"}]}
    spec = op.spec_from_dict(d)
    direct = op.OpmPlateSpec(layout=op.PlateLayout.parse("3x3+1x1@-1,1"), layers=1,
                             ports=(op.Port(cell=(1, 2)),),
                             apertures=(op.Aperture(cell=(0, 0), d_mm=20, plate="base"),))
    p1, p2 = op.build_parts(d), op.build_opm_plates(direct)
    agree = all(abs(p1[w].val().Volume() - p2[w].val().Volume()) < 1e-6 for w in ("top", "base"))
    print("  build_parts(dict) == build_opm_plates(spec)", ok(agree))
    good &= agree and spec.layers == 1
    plan = op.plan_opm_plates(spec)
    screw = plan.screw_length_mm()
    print(f"  one-layer stack: top plate +{plan.top_offset_z_mm:g} mm, M3x{screw:g} rods",
          ok(plan.top_offset_z_mm == 65.0 and screw == 60.0))
    good &= plan.top_offset_z_mm == 65.0 and screw == 60.0
    print(f"  --> {'PASS' if good else 'FAIL'}\n")
    return good


def main() -> None:
    results = [check_rod_rule(), check_interfaces()]
    layouts = [
        ("3x3 plain rectangle", op.OpmPlateSpec(layout=op.PlateLayout.parse("3x3"))),
        ("3x8+1x1, the released FLIM 488 pair", op.released_3x8_1x1()),
        ("3x3 with extra units on all four sides, M37 port + 25 mm base aperture",
         op.OpmPlateSpec(layout=op.PlateLayout.parse("3x3+1x1@-1,1+1x2@3,0+2x1@0,3+1x1@2,-1"),
                         ports=(op.Port(cell=(1, 1)),),
                         apertures=(op.Aperture(cell=(1, 3), d_mm=25.0, plate="base",
                                                chamfer_mm=1.0),))),
        ("a ring with an enclosed hole (ASCII, outline rods)",
         op.OpmPlateSpec(layout=op.PlateLayout.from_ascii("###\n#.#\n###", name="ring"),
                         tie_rods="outline")),
        ("a single cell, one layer", op.OpmPlateSpec(layout=op.PlateLayout.parse("1x1"),
                                                     layers=1)),
    ]
    results += [check_layout(label, spec) for label, spec in layouts]
    results.append(check_released())
    results.append(check_refusals())
    print(f"{sum(results)}/{len(results)} checks passed")
    # Leave without interpreter teardown: OCC can segfault while freeing the
    # imported reference STEPs, which would turn a pass into exit code 139.
    sys.stdout.flush()
    os._exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
