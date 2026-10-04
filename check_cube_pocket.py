"""Verification of uc2v4/cube_pocket.py.

For each cube size: both halves are one solid each; the cube (nominal) does not enter them;
moved 0.3 mm towards any of its six faces it meets a wall (it is held); the four bores are
open along ±x and ±y; a closed port has no bore.

Usage:
    uv run --with cadquery python check_cube_pocket.py
"""

from __future__ import annotations

import sys

import cadquery as cq

from uc2v4.cube_pocket import CubePocketParams, build_cube_pocket, plan_cube_pocket

CASES = [("12.7 mm cube", CubePocketParams(cube_mm=12.7)),
         ("20 mm cube", CubePocketParams(cube_mm=20.0)),
         ("25.4 mm cube", CubePocketParams(cube_mm=25.4)),
         ("25.4 mm cube, -y closed", CubePocketParams(cube_mm=25.4, ports=("+x", "-x", "+y")))]


def overlap(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        return sum(s.Volume() for s in a.intersect(b).solids().vals())
    except Exception:  # noqa: BLE001
        return 0.0


def check(name: str, p: CubePocketParams) -> bool:
    print(f"== {name}")
    plan = plan_cube_pocket(p)
    lower, upper = build_cube_pocket(plan)
    body = lower.union(upper)
    ok = True

    def report(text: str, good: bool) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] {text}")

    counts = [len(lower.solids().vals()), len(upper.solids().vals())]
    report(f"one solid each ({counts})", counts == [1, 1])
    cube = cq.Workplane("XY").box(p.cube_mm, p.cube_mm, p.cube_mm)
    report(f"the cube is free ({overlap(body, cube):.4f} mm3)", overlap(body, cube) < 1e-3)
    held = all(overlap(body, cube.translate(tuple(0.3 * v for v in d))) > 0
               for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)))
    report("moved 0.3 mm towards any face it meets a wall", held)
    r = plan.bore_r_mm - 0.2
    solid = body.val()
    opened = {q: not any(solid.isInside(cq.Vector(*(t * c + (r if i == 2 else 0.0)
                                                     for i, c in enumerate(v))))
                         for t in (p.cube_mm / 2 + 1.0, 16.0))
              for q, v in {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0),
                           "-y": (0, -1, 0)}.items()}
    want = {q: q in p.ports for q in opened}
    report(f"bores open where asked: {opened}", opened == want)
    print(f"  --> {'PASS' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = [check(*case) for case in CASES]
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
