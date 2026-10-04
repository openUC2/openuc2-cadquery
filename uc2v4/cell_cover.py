"""Cover over a list of cells: a light-tight hood over the cubes of a design with a laser, with a
seat for an interlock microswitch that the plate presses when the cover is down.

The hood stands on the puzzle layer around the cells — the union of the cell squares grown by
the clearance (inside) and the wall (outside), so an L-shaped set works — and is as tall as
``levels`` cube levels. Its walls lie over the neighbouring cells' edges, so those cells must
hold no cube (``blocked_cells``). Cable holes go through the walls. The switch sits in a
housing on the outside of one wall, its lever reaching ``actuation_mm`` below the cover's
bottom edge.

Frame: the base plate's top at z = 0, cell (0, 0) centred on the origin (the frame of
``off_grid_plate``). Units mm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

#: A KW11-style microswitch: body (along the wall, through it, up), the lever's reach below the
#: body when free, the two mounting holes (along the wall, up from the body's bottom).
SWITCH = {"body": (20.0, 6.5, 10.5), "lever": 3.0, "holes": ((-4.75, 3.0), (4.75, 3.0)),
          "hole_d": 2.0}
FACES = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


@dataclass(frozen=True)
class CellCoverParams:
    cells: tuple[tuple[int, int], ...]
    pitch_mm: float = 50.0
    levels: int = 1                       # cube levels under the cover
    puzzle_mm: float = 5.0                # the puzzle layer it stands on
    clearance_mm: float = 1.0
    wall_mm: float = 2.4
    blocked_cells: tuple[tuple[int, int], ...] = ()
    holes: tuple[dict, ...] = ()          # {"cell": [c, r], "face": "+x", "z_mm": h, "d_mm": d}
    switch_cell: tuple[int, int] | None = None   # the wall of this cell that carries the switch
    switch_face: str = "-y"
    actuation_mm: float = 1.0             # lever below the cover's bottom edge
    print_bed_mm: float = 250.0


@dataclass
class CellCoverPlan:
    params: CellCoverParams
    height_mm: float = 0.0                # inner height above the puzzle layer
    bbox_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    switch_mm: tuple[float, float] | None = None   # the switch's centre on its wall (x, y)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict:
        return {"cells": [list(c) for c in self.params.cells],
                "height_mm": round(self.height_mm, 3),
                "bbox_mm": [round(v, 3) for v in self.bbox_mm],
                "switch_mm": None if self.switch_mm is None else
                [round(v, 3) for v in self.switch_mm],
                "warnings": self.warnings}


def _outer_walls(p: CellCoverParams, cells: set) -> list[tuple[tuple[int, int], str]]:
    return [(c, f) for c in sorted(cells) for f, d in FACES.items()
            if (c[0] + d[0], c[1] + d[1]) not in cells]


def plan_cell_cover(p: CellCoverParams) -> CellCoverPlan:
    """Check cells, walls, holes and the switch; nothing is built."""
    if not p.cells:
        raise ValueError("no cells: give the cells the cover goes over")
    cells = {tuple(c) for c in p.cells}
    if len(cells) != len(p.cells):
        raise ValueError("a cell is listed twice")
    if not 1 <= p.levels <= 4:
        raise ValueError(f"{p.levels} levels: the cover takes 1 to 4 cube levels")
    walls = _outer_walls(p, cells)
    for c, f in walls:
        d = FACES[f]
        nb = (c[0] + d[0], c[1] + d[1])
        if nb in set(map(tuple, p.blocked_cells)):
            raise ValueError(f"the cover's wall on the {f} side of cell {c} lies over cell {nb}, "
                             "which holds a cube: take that cell in or leave it empty")
    plan = CellCoverPlan(params=p)
    plan.height_mm = 55.0 * p.levels - p.puzzle_mm + 2.0 + p.clearance_mm
    pitch, g = p.pitch_mm, p.clearance_mm + p.wall_mm
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    plan.bbox_mm = (min(xs) * pitch - pitch / 2 - g, max(xs) * pitch + pitch / 2 + g,
                    min(ys) * pitch - pitch / 2 - g, max(ys) * pitch + pitch / 2 + g)
    size = max(plan.bbox_mm[1] - plan.bbox_mm[0], plan.bbox_mm[3] - plan.bbox_mm[2])
    if size > p.print_bed_mm:
        plan.warnings.append(f"the cover is {size:.0f} mm across, larger than a "
                             f"{p.print_bed_mm:g} mm print bed: print it in parts")
    for h in p.holes:
        key = (tuple(h["cell"]), h["face"])
        if key not in set(walls):
            raise ValueError(f"cable hole {h}: cell {key[0]} has no outer wall on {key[1]}")
        if not h["d_mm"] / 2 + 2.0 <= h["z_mm"] - p.puzzle_mm <= plan.height_mm - h["d_mm"] / 2:
            raise ValueError(f"cable hole {h}: its height is outside the wall")
    if p.switch_cell is not None:
        key = (tuple(p.switch_cell), p.switch_face)
        if key not in set(walls):
            raise ValueError(f"the switch: cell {key[0]} has no outer wall on {key[1]}")
        d = FACES[p.switch_face]
        c = p.switch_cell
        wall = pitch / 2 + p.clearance_mm + p.wall_mm      # the wall's outer face
        plan.switch_mm = (c[0] * pitch + d[0] * wall, c[1] * pitch + d[1] * wall)
    return plan


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:  # noqa: ANN001
    return cq.Workplane("XY").add(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0,
                                                   cq.Vector(x0, y0, z0)))


def build_cell_cover(plan: CellCoverPlan) -> cq.Workplane:
    """The printed hood in the plate frame."""
    p = plan.params
    pitch, c, w = p.pitch_mm, p.clearance_mm, p.wall_mm
    z0 = p.puzzle_mm
    z_in = z0 + plan.height_mm
    outer = inner = None
    for cx, cy in p.cells:
        x, y = cx * pitch, cy * pitch
        o = _box(x - pitch / 2 - c - w, x + pitch / 2 + c + w, y - pitch / 2 - c - w,
                 y + pitch / 2 + c + w, z0, z_in + w)
        i = _box(x - pitch / 2 - c, x + pitch / 2 + c, y - pitch / 2 - c, y + pitch / 2 + c,
                 z0 - 1.0, z_in)
        outer = o if outer is None else outer.union(o)
        inner = i if inner is None else inner.union(i)
    hood = outer.cut(inner)
    for h in p.holes:
        d = FACES[h["face"]]
        cx, cy = h["cell"]
        wall = pitch / 2 + c + w / 2
        at = cq.Vector(cx * pitch + d[0] * wall, cy * pitch + d[1] * wall, h["z_mm"])
        axis = cq.Vector(d[0], d[1], 0)
        hood = hood.cut(cq.Workplane("XY").add(
            cq.Solid.makeCylinder(h["d_mm"] / 2, 3 * w, at - axis * (1.5 * w), axis)))
    if plan.switch_mm is not None:
        bl, bt, bh = SWITCH["body"]
        d = FACES[p.switch_face]
        sx, sy = plan.switch_mm
        # the switch's body against the wall's outside, low enough that its lever reaches
        # past the cover's bottom edge
        zb = z0 - p.actuation_mm + SWITCH["lever"]
        along = (abs(d[1]), abs(d[0]))                 # unit vector along the wall
        out = (d[0], d[1])

        def spot(a: float, t: float) -> tuple[float, float]:
            return (sx + along[0] * a + out[0] * t, sy + along[1] * a + out[1] * t)
        x0, y0 = spot(-bl / 2 - 2.0, 0.0)
        x1, y1 = spot(bl / 2 + 2.0, bt + 2.0)
        housing = _box(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), z0, zb + bh + 2.0)
        x0, y0 = spot(-bl / 2 - 0.1, 0.0)
        x1, y1 = spot(bl / 2 + 0.1, bt + 0.1)
        pocket = _box(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), z0 - 1.0, zb + bh + 0.1)
        hood = hood.union(housing).cut(pocket)
        for a, h in SWITCH["holes"]:
            hx, hy = spot(a, 0.0)
            pilot = cq.Solid.makeCylinder(SWITCH["hole_d"] / 2 * 0.8, bt + 3.0 + w,
                                          cq.Vector(hx - out[0] * (w - 0.8),
                                                    hy - out[1] * (w - 0.8), zb + h),
                                          cq.Vector(out[0], out[1], 0))
            hood = hood.cut(cq.Workplane("XY").add(pilot))
        cx, cy = spot(0.0, bt / 2)
        slot = _box(cx - 2.0, cx + 2.0, cy - 2.0, cy + 2.0, zb + bh - 0.1, zb + bh + 2.1)
        hood = hood.cut(slot)                          # the cable leaves the housing's top
    return hood.clean()
