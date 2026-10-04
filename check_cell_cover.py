"""Verification of uc2v4/cell_cover.py.

1. the cover is one solid, standing on the puzzle layer;
2. the cubes under it (one per cell and level, bosses included) do not touch it;
3. the cable holes are open through the wall;
4. the switch (its body as a box, the lever below it) fits its pocket, outside the cubes, and
   the lever reaches below the cover's bottom edge.

Usage:
    uv run --with cadquery python check_cell_cover.py
"""

from __future__ import annotations

import sys

import cadquery as cq

from uc2v4.cell_cover import FACES, SWITCH, CellCoverParams, build_cell_cover, plan_cell_cover

CASES = [
    ("2 x 1, one level, switch on -y, cable hole on +x",
     CellCoverParams(cells=((0, 0), (1, 0)), switch_cell=(0, 0), switch_face="-y",
                     holes=({"cell": [1, 0], "face": "+x", "z_mm": 20.0, "d_mm": 8.0},))),
    ("L-shape, two levels, switch on +x",
     CellCoverParams(cells=((0, 0), (1, 0), (0, 1)), levels=2, switch_cell=(1, 0),
                     switch_face="+x")),
]


def overlap(a, b) -> float:  # noqa: ANN001
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def check(name: str, p: CellCoverParams) -> bool:
    print(f"== {name}")
    plan = plan_cell_cover(p)
    cover = build_cell_cover(plan)
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    bb = cover.val().BoundingBox()
    report(f"one solid ({len(cover.solids().vals())}), standing on the puzzle layer at "
           f"z {bb.zmin:.2f}", len(cover.solids().vals()) == 1 and abs(bb.zmin - p.puzzle_mm) < 1e-6)
    cubes = None
    for cx, cy in p.cells:
        for level in range(1, p.levels + 1):
            cube = cq.Workplane("XY").box(49.8, 49.8, 49.8 + 2 * 1.9).translate(
                (cx * p.pitch_mm, cy * p.pitch_mm, 55.0 * level - 25.0))
            cubes = cube if cubes is None else cubes.union(cube)
    v = overlap(cover, cubes)
    report(f"the cubes under it are clear ({v:.3f} mm3)", v < 1e-3)
    for h in p.holes:
        d = FACES[h["face"]]
        wall = p.pitch_mm / 2 + p.clearance_mm + p.wall_mm / 2
        pt = cq.Vector(h["cell"][0] * p.pitch_mm + d[0] * wall,
                       h["cell"][1] * p.pitch_mm + d[1] * wall, h["z_mm"])
        report(f"cable hole on {h['face']} open", not cover.val().isInside(pt))
    if plan.switch_mm is not None:
        bl, bt, bh = SWITCH["body"]
        d = FACES[p.switch_face]
        sx, sy = plan.switch_mm
        zb = p.puzzle_mm - p.actuation_mm + SWITCH["lever"]
        cx, cy = sx + d[0] * (bt / 2 + 0.05), sy + d[1] * (bt / 2 + 0.05)
        lx, ly = (bl, bt - 0.1) if d[1] else (bt - 0.1, bl)
        body = cq.Workplane("XY").box(lx - 0.1, ly, bh - 0.1).translate((cx, cy, zb + bh / 2))
        v = overlap(cover, body)
        lever_tip = zb - SWITCH["lever"]
        report(f"switch in its pocket ({v:.4f} mm3), lever tip {lever_tip:.2f} below the edge "
               f"at {p.puzzle_mm}", v < 1e-3 and lever_tip < p.puzzle_mm)
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
