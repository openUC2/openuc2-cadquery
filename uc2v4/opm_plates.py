"""Top and base plates of an openUC2 V4 optical module (OPM), for any layout.

An OPM is a block of 50 mm cubes clamped between two 5 mm aluminium plates.
Every cube layer stands on a 5 mm puzzle layer (PUZ11 pieces), and M3 tie
rods run through the cube corners from the top plate down to sleeve nuts
under the base plate::

    top plate     z = 55 L - 25 .. +5  <- M3 tie-rod heads (counterbored), ports
    puzzle layer  5 mm
    cube layer L  ...
    puzzle layer  z  25 ..  30
    cube layer 1  z -25 ..  25          (cube centres at z = 0)
    puzzle layer  z -30 .. -25
    base plate    z -35 .. -30          <- sleeve nuts in U-slot recesses

This module turns a **layout** -- a base rectangle such as ``3x8`` or ``3x3``
plus any number of extra puzzle units on any side -- into both plates, as
STEP/STL, plus a JSON plan (cells, tie rods, ports, hardware) that an OPM
designer can consume.

Every dimension was extracted from the Inventor sources over COM
(``PyInventor/inventor_part_probe.py``; dumps in ``extracted/plates/``):

- ``MAS - 1003 - Base plates Al - V04`` -- the master. A plate is literally a
  union of cell squares ``Grid x (Grid + 0.1)`` = 50.0 x 50.1 mm, 5 mm thick,
  each with four M3x0.5 tapped through holes at +-22 mm (``Hole7`` +
  ``Circular Pattern9``), patterned ``NoColumns x NoRows`` at 50.0 / 50.1.
- ``PRT - 1052 - TOPPLA3X8+1X1 - V04`` / ``PRT - 1051 - BASPLA3X8+1X1 - V04``
  -- the released pair (FLIM 488 module), cross-checked against
  PRT-1053/1054 (3x7+1x1), PRT-1026/1027 (3x6), PRT-1047/1048 (3x3+1x2):
    - a 38 x 3 mm pocket per cell on the cube-facing face;
    - vertical edges R1.5 at outside corners, R10.2 at inside corners;
    - a 1 mm x 45 deg chamfer round the outward face;
    - tie rods at +-20.5 mm from a cell centre (the PUZ11 corner holes):
      top plate 3.4 through + 6.5 x 3.1 counterbore for the ISO 4762 head,
      base plate 4.5 through + an R4.5 x 2.4 recess for the M3x8 sleeve nut,
      opened into a U-slot towards any plate edge it would otherwise graze;
    - tie rods at the corners of the core rectangle, plus intermediate rods so
      no more than three cells separate two rods along an edge (3x6: middle,
      3x7: rows 1|2 and 4|5, 3x8: rows 2|3 and 4|5 -- each rod on the side of
      the nearer end);
    - optionally an M37x0.5 port (33 aperture, 0.8 lip, 37.4 relief) for a
      retaining ring, in the top plate's far-end middle cell.

Frame (identical to the Inventor parts, so both plates can be compared 1:1):
cell ``(0, 0)`` is centred on the origin, cell ``(c, r)`` at ``(c * pitch_x,
r * pitch_y)``, and **both** plates are modelled at z = -35 .. -30. The base
plate is used as is; the top plate is *translated* (not flipped) by
``55 L + 5 + thickness`` for an L-layer stack -- 120 mm for two layers,
exactly as in ``OPM - 0004 - FLIM 488``. So the cube-facing ("inner") face is
z = -30 on the base plate and z = -35 on the top plate.

    from uc2v4.opm_plates import OpmPlateSpec, PlateLayout, Port, generate

    spec = OpmPlateSpec(layout=PlateLayout.parse("3x8+1x1@-1,0"),
                        ports=(Port(cell=(1, 7)),))
    generate(spec, out_dir="generated/opm_3x8")   # top/base STEP+STL, plan, png
"""

from __future__ import annotations

import json
import math
import re
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

import cadquery as cq

Cell = tuple[int, int]

#: Cube pitch of the V04 aluminium plates (MAS-1003 ``Rectangular Pattern1``:
#: columns at ``Grid``, rows at ``Grid + 0.1``). PRT-1045 (3x3) predates it and
#: uses 50.0 both ways; the FLIM 488 assembly places cubes at 50.1 both ways.
V04_PITCH_MM: tuple[float, float] = (50.0, 50.1)
CUBE_MM = 50.0              # cube edge; one cube layer + one puzzle layer = 55
PUZZLE_LAYER_MM = 5.0       # PUZ11 thickness
PLATE_INNER_Z = -30.0       # base plate's cube-facing face (cube centre at z=0)
AL_DENSITY_G_MM3 = 2.70e-3  # EN AW-6063 -- PRT-1052: 222525 mm^3 -> 601 g

CORNERS: dict[str, Cell] = {"sw": (-1, -1), "se": (1, -1), "ne": (1, 1), "nw": (-1, 1)}
_CORNER_NAME = {v: k for k, v in CORNERS.items()}


class LayoutError(ValueError):
    """A layout that cannot become one plate (disconnected, corner-touching...)."""


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

def _neighbours(c: Cell) -> Iterable[Cell]:
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


@dataclass(frozen=True)
class PlateLayout:
    """Which grid cells the plates cover.

    ``cells`` is every cell under the plate; ``core`` is the structural part
    that carries the tie rods (the base rectangle of ``3x8+1x1``); the rest are
    *extra puzzle units* hanging off it. Cell ``(0, 0)`` is the lower-left cell
    of the base rectangle; extras may sit at negative indices.
    """

    cells: frozenset
    core: frozenset = frozenset()
    name: str = ""

    def __post_init__(self):
        cells = frozenset((int(c), int(r)) for c, r in self.cells)
        core = frozenset((int(c), int(r)) for c, r in self.core) or cells
        object.__setattr__(self, "cells", cells)
        object.__setattr__(self, "core", core)
        if not cells:
            raise LayoutError("empty layout")
        if not core <= cells:
            raise LayoutError(f"core cells outside the layout: {sorted(core - cells)}")
        islands = _islands(cells)
        if len(islands) > 1:
            raise LayoutError(
                "layout is not one piece -- these groups do not share an edge: "
                + "; ".join(str(sorted(i)) for i in islands))
        _boundary_loops(cells)  # raises on corner-only contacts

    # ---- constructors -----------------------------------------------------

    @classmethod
    def rect(cls, cols: int, rows: int, extra: Iterable[Cell] = (), name: str = ""
             ) -> "PlateLayout":
        """``cols x rows`` core rectangle plus extra (non-structural) cells."""
        if cols < 1 or rows < 1:
            raise LayoutError("a rectangle needs at least one column and one row")
        core = {(c, r) for c in range(cols) for r in range(rows)}
        cells = core | {tuple(e) for e in extra}
        return cls(frozenset(cells), frozenset(core), name or f"{cols}x{rows}")

    @classmethod
    def parse(cls, spec: str) -> "PlateLayout":
        """Parse ``"3x8"``, ``"3x8+1x1@-1,0"``, ``"3x3@0,3+1x2@1,1-1x1@2,5"``.

        The first ``CxR[@c,r]`` block is the core rectangle (default at 0,0).
        ``+WxH@c,r`` adds a block of extra puzzle units whose lower-left cell
        is ``(c, r)``; ``-WxH@c,r`` removes one. Blocks may sit on any side.
        """
        s = spec.replace(" ", "")
        m = re.match(r"^(\d+)[xX](\d+)(?:@\(?(-?\d+),(-?\d+)\)?)?", s)
        if not m:
            raise LayoutError(f"cannot parse layout {spec!r}: expected e.g. '3x8+1x1@-1,0'")
        cols, rows = int(m.group(1)), int(m.group(2))
        c0, r0 = int(m.group(3) or 0), int(m.group(4) or 0)
        if cols < 1 or rows < 1:
            raise LayoutError(f"{spec!r}: a block needs at least one column and one row")
        core = {(c0 + c, r0 + r) for c in range(cols) for r in range(rows)}
        cells = set(core)
        rest = s[m.end():]
        block = re.compile(r"([+-])(\d+)[xX](\d+)@\(?(-?\d+),(-?\d+)\)?")
        pos = 0
        while pos < len(rest):
            b = block.match(rest, pos)
            if not b:
                raise LayoutError(
                    f"cannot parse {rest[pos:]!r} in layout {spec!r}: extra blocks "
                    "need a position, e.g. '+1x2@1,3' (lower-left cell of the block)")
            w, h, bc, br = (int(b.group(i)) for i in range(2, 6))
            blk = {(bc + c, br + r) for c in range(w) for r in range(h)}
            if b.group(1) == "+":
                cells |= blk
            else:
                cells -= blk
                core -= blk
            pos = b.end()
        return cls(frozenset(cells), frozenset(core), spec.strip())

    @classmethod
    def from_ascii(cls, art: str, name: str = "") -> "PlateLayout":
        """Layout drawn as text, top line = highest row (plan view from above).

        ``#`` or ``X`` = core cell, ``+`` or ``o`` = extra puzzle unit,
        ``.``/space/``-`` = empty; ``P`` / ``p`` = a core / extra cell that
        carries a port (see :func:`layout_and_ports_from_ascii`). Without any
        extra units every cell is core. Cell (0, 0) is the lower-left cell of
        the core's bounding box::

            .###
            .###
            +###     # 3x3 core with one extra unit on its left
        """
        core, extra, _ = _parse_ascii(art)
        return cls(frozenset(core | extra), frozenset(core), name)

    @classmethod
    def from_cells(cls, cells: Iterable[Sequence[int]], core: Iterable[Sequence[int]] = (),
                   name: str = "") -> "PlateLayout":
        return cls(frozenset(tuple(c) for c in cells), frozenset(tuple(c) for c in core), name)

    # ---- views ------------------------------------------------------------

    @property
    def extra(self) -> frozenset:
        return self.cells - self.core

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        cs = [c for c, _ in self.cells]
        rs = [r for _, r in self.cells]
        return min(cs), min(rs), max(cs), max(rs)

    def to_ascii(self) -> str:
        c0, r0, c1, r1 = self.bounds
        rows = []
        for r in range(r1, r0 - 1, -1):
            rows.append("".join(
                "#" if (c, r) in self.core else "+" if (c, r) in self.cells else "."
                for c in range(c0, c1 + 1)))
        return "\n".join(rows)

    def label(self) -> str:
        return self.name or f"{len(self.cells)}cells"


def _parse_ascii(art: str) -> tuple[set, set, set]:
    """(core, extra, port cells) of an ASCII layout, shifted so the core's
    bounding box starts at (0, 0)."""
    lines = [ln.rstrip() for ln in art.strip("\n").splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        raise LayoutError("empty ASCII layout")
    core, extra, ports = set(), set(), set()
    n = len(lines)
    for i, ln in enumerate(lines):
        r = n - 1 - i
        for c, ch in enumerate(ln):
            if ch in "#XxP":
                core.add((c, r))
            elif ch in "+oOp":
                extra.add((c, r))
            elif ch not in ". -_":
                raise LayoutError(f"unexpected character {ch!r} in ASCII layout "
                                  "(use # core, + extra, P/p port, . empty)")
            if ch in "Pp":
                ports.add((c, r))
    if not core:
        core, extra = extra, set()
    c0 = min(c for c, _ in core)
    r0 = min(r for _, r in core)
    shift = lambda s: {(c - c0, r - r0) for c, r in s}  # noqa: E731
    return shift(core), shift(extra), shift(ports)


def _islands(cells: frozenset) -> list[set]:
    todo, out = set(cells), []
    while todo:
        seed = todo.pop()
        comp, q = {seed}, deque([seed])
        while q:
            for n in _neighbours(q.popleft()):
                if n in todo:
                    todo.discard(n)
                    comp.add(n)
                    q.append(n)
        out.append(comp)
    return out


def _boundary_loops(cells: Iterable[Cell]) -> list[list[Cell]]:
    """Boundary loops of a cell set in grid-corner coordinates.

    Corner ``(i, j)`` is the lower-left corner of cell ``(i, j)``. Loops are
    traversed with the material on the LEFT: the outline counter-clockwise,
    holes clockwise. Collinear vertices are dropped.
    """
    edges: set = set()
    for c, r in cells:
        k = [(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)]
        for a, b in zip(k, k[1:] + k[:1]):
            if (b, a) in edges:
                edges.discard((b, a))
            else:
                edges.add((a, b))
    nxt: dict = {}
    for a, b in edges:
        if a in nxt:
            raise LayoutError(
                f"cells meet only at a corner at grid corner {a}: the plate would "
                "pinch to a point there -- add a cell to join them")
        nxt[a] = b
    loops, todo = [], set(nxt)
    while todo:
        start = min(todo)
        loop, v = [start], nxt[start]
        todo.discard(start)
        while v != start:
            loop.append(v)
            todo.discard(v)
            v = nxt[v]
        keep = []
        for i, p in enumerate(loop):
            a, b = loop[i - 1], loop[(i + 1) % len(loop)]
            if (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0]) != 0:
                keep.append(p)
        loops.append(keep)
    return loops


def _signed_area(pts: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlateGeometry:
    """The V04 aluminium plate recipe (MAS-1003 + PRT-1051/1052)."""

    pitch_mm: tuple[float, float] = V04_PITCH_MM
    thickness_mm: float = 5.0
    corner_fillet_mm: float = 1.5          # Fillet10 -- outside vertical edges
    inside_fillet_mm: float = 10.2         # Fillet11/12 -- inside corners (D20 cutter)
    outer_chamfer_mm: float = 1.0          # Chamfer16 -- outward face only
    m3_offset_mm: float = 22.0             # Hole7: 4 per cell at (+-22, 0), (0, +-22)
    m3_hole_d_mm: float = 2.46             # M3x0.5-6H tapped: minor diameter, as exported
    pocket_d_mm: float = 38.0              # Hole13/16 + Rectangular Pattern4
    pocket_depth_mm: float = 3.0
    tie_rod_offset_mm: float = 20.5        # PUZ11 corner holes, both axes
    tie_rod_max_span: int = 3              # cells between rods along an edge
    top_rod_d_mm: float = 3.4              # M3 clearance
    top_rod_cbore_d_mm: float = 6.5        # ISO 4762 M3 head 5.5
    top_rod_cbore_depth_mm: float = 3.1
    base_rod_d_mm: float = 4.5             # sleeve nut M3x8, shank 4
    base_recess_r_mm: float = 4.5          # d256
    base_recess_depth_mm: float = 2.4      # d220

    def __post_init__(self):
        if self.outer_chamfer_mm and self.corner_fillet_mm <= self.outer_chamfer_mm:
            raise ValueError("corner_fillet_mm must exceed outer_chamfer_mm "
                             "(the chamfer runs round the fillet)")
        if self.thickness_mm <= max(self.pocket_depth_mm, self.base_recess_depth_mm,
                                    self.top_rod_cbore_depth_mm):
            raise ValueError("plate too thin for its pockets/recesses")

    @property
    def z_bottom(self) -> float:
        return PLATE_INNER_Z - self.thickness_mm

    @property
    def z_top(self) -> float:
        return PLATE_INNER_Z


@dataclass(frozen=True)
class Port:
    """Threaded port for an M37x0.5 retaining ring (PRT-1052 ``Revolution1``).

    Seen from the cube side: the thread (minor diameter) runs in from the inner
    face, a 45 deg step opens into the thread relief, and a lip on the outward
    face stops the optic with a clear ``aperture_d_mm``. The cell gets no pocket.
    """

    cell: Cell
    plate: str = "top"                     # "top" | "base"
    aperture_d_mm: float = 33.0            # d356
    thread_major_d_mm: float = 37.0        # d361, M37x0.5
    thread_pitch_mm: float = 0.5
    relief_d_mm: float = 37.4              # d358
    lip_mm: float = 0.8                    # d357
    relief_mm: float = 1.0

    @property
    def thread_minor_d_mm(self) -> float:
        return self.thread_major_d_mm - 1.082532 * self.thread_pitch_mm


@dataclass(frozen=True)
class Aperture:
    """Plain through hole at a cell centre, e.g. the 35 mm port of PRT-1045."""

    cell: Cell
    d_mm: float
    plate: str = "top"                     # "top" | "base" | "both"
    chamfer_mm: float = 0.0                # 45 deg, on the outward face
    offset_mm: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class CustomHole:
    """Any round hole: through, or blind from the inner/outer face.

    Position = centre of ``cell`` (origin cell when ``None``) + ``offset_mm``.
    """

    d_mm: float
    offset_mm: tuple[float, float] = (0.0, 0.0)
    cell: Cell | None = None
    depth_mm: float | None = None          # None = through
    plate: str = "base"                    # "top" | "base" | "both"
    face: str = "outer"                    # "outer" | "inner" (for blind holes)


@dataclass(frozen=True)
class TieRod:
    """One tie rod: at ``cell``'s ``corner`` ('sw','se','ne','nw')."""

    cell: Cell
    corner: str

    def __post_init__(self):
        if self.corner not in CORNERS:
            raise ValueError(f"corner must be one of {sorted(CORNERS)}, not {self.corner!r}")

    @property
    def sign(self) -> Cell:
        return CORNERS[self.corner]


@dataclass(frozen=True)
class OpmPlateSpec:
    """Everything that defines one OPM's plate pair."""

    layout: PlateLayout
    layers: int = 2                                    # cube layers in the stack
    ports: tuple[Port, ...] = ()
    apertures: tuple[Aperture, ...] = ()
    holes: tuple[CustomHole, ...] = ()
    tie_rods: str | tuple[TieRod, ...] = "auto"        # "auto" | "outline" | "none" | rods
    pockets: bool = True
    geometry: PlateGeometry = field(default_factory=PlateGeometry)
    name: str | None = None

    def stem(self) -> str:
        base = self.name or f"opm_plates_{self.layout.label()}"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("_")


# ---------------------------------------------------------------------------
# tie-rod rule
# ---------------------------------------------------------------------------

def _edge_breaks(n: int, span: int) -> list[int]:
    """Cell boundaries (1..n-1) that get an intermediate rod along an n-cell edge."""
    if n <= span:
        return []
    groups = math.ceil(n / span)
    return sorted({math.floor(k * n / groups + 0.5) for k in range(1, groups)})


def auto_tie_rods(region: Iterable[Cell], span: int = 3) -> list[TieRod]:
    """Rods at every outside corner of ``region`` plus intermediate rods along
    its straight edges so no more than ``span`` cells separate two rods.

    An intermediate rod sits in the cell on the side of the nearer edge end
    (a tie goes to the higher row/column), which reproduces PRT-1027 (3x6),
    PRT-1053 (3x7+1x1) and PRT-1051 (3x8+1x1); applied to the whole outline it
    also reproduces PRT-1048 (3x3+1x2). Inside corners get no rod; holes in the
    region are ignored.
    """
    region = frozenset(region)
    loops = _boundary_loops(region)
    rods: dict = {}
    for loop in loops:
        if _signed_area(loop) <= 0:
            continue                                   # a hole in the region
        n = len(loop)
        for k in range(n):
            a, b = loop[k], loop[(k + 1) % n]
            d = ((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))
            length = abs(b[0] - a[0]) + abs(b[1] - a[1])
            right = (d[1], -d[0])                      # outward normal (material on the left)
            # the cell alongside step s of this edge (inside the region)
            def cell_at(s):
                px, py = a[0] + d[0] * s, a[1] + d[1] * s        # corner at step s
                cx = px + (d[0] - 1) // 2 if d[0] else px + (-1 if right[0] > 0 else 0)
                cy = py + (d[1] - 1) // 2 if d[1] else py + (-1 if right[1] > 0 else 0)
                return (cx, cy)
            for s in range(length):
                assert cell_at(s) in region, (a, b, s, cell_at(s))
            # outside corner at the edge start (left turn from the previous edge)
            p = loop[k - 1]
            din = ((a[0] > p[0]) - (a[0] < p[0]), (a[1] > p[1]) - (a[1] < p[1]))
            if din[0] * d[1] - din[1] * d[0] > 0:
                cell = cell_at(0)
                sx = right[0] or -d[0]
                sy = right[1] or -d[1]
                rods[(cell, (sx, sy))] = TieRod(cell, _CORNER_NAME[(sx, sy)])
            for brk in _edge_breaks(length, span):
                # Boundary brk lies between step brk-1 and brk. The rod goes in
                # the cell on the side of the nearer edge end; a tie (the middle
                # of an even edge) goes to the higher row/column, so opposite
                # edges -- traversed in opposite directions -- stay mirror images.
                before = brk < length - brk or (brk == length - brk and d[0] + d[1] < 0)
                if before:
                    cell, along = cell_at(brk - 1), d
                else:
                    cell, along = cell_at(brk), (-d[0], -d[1])
                sx = right[0] or along[0]
                sy = right[1] or along[1]
                rods[(cell, (sx, sy))] = TieRod(cell, _CORNER_NAME[(sx, sy)])
    return sorted(rods.values(), key=lambda t: (t.cell[1], t.cell[0], t.corner))


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

@dataclass
class OpmPlatePlan:
    spec: OpmPlateSpec
    centres: dict                     # cell -> (x, y) mm
    loops_mm: list                    # boundary loops (unrounded), material on the left
    tie_rods: list                    # [(TieRod, (x, y), open_dirs)]
    top_offset_z_mm: float            # translation that places the top plate
    warnings: list = field(default_factory=list)
    files: dict = field(default_factory=dict)          # filled by generate()
    volumes_mm3: dict = field(default_factory=dict)    # filled by generate()

    @property
    def geometry(self) -> PlateGeometry:
        return self.spec.geometry

    def centre(self, cell: Cell) -> tuple[float, float]:
        px, py = self.geometry.pitch_mm
        return (cell[0] * px, cell[1] * py)

    def extent(self) -> tuple[float, float, float, float]:
        xs = [x for loop in self.loops_mm for x, _ in loop]
        ys = [y for loop in self.loops_mm for _, y in loop]
        return min(xs), min(ys), max(xs), max(ys)

    def screw_length_mm(self) -> float:
        """ISO 4762 M3 length: counterbore floor -> 3.5 mm into the sleeve nut."""
        g = self.geometry
        head_seat = self.top_offset_z_mm + g.z_top - g.top_rod_cbore_depth_mm
        sleeve_top = g.z_bottom + g.base_recess_depth_mm + 8.0
        return round(head_seat - sleeve_top + 3.5, 1)

    def report(self) -> dict:
        s, g = self.spec, self.geometry
        x0, y0, x1, y1 = self.extent()
        pocket_cells = [c for c in sorted(self.centres) if s.pockets]
        rods = [{"cell": list(t.cell), "corner": t.corner, "xy_mm": [round(x, 3), round(y, 3)],
                 "recess_open_to": sorted(open_dirs)} for t, (x, y), open_dirs in self.tie_rods]
        return {
            "layout": {
                "spec": s.layout.name, "ascii": s.layout.to_ascii().splitlines(),
                "cells": [list(c) for c in sorted(s.layout.cells, key=lambda c: (c[1], c[0]))],
                "core": [list(c) for c in sorted(s.layout.core, key=lambda c: (c[1], c[0]))],
                "extra": [list(c) for c in sorted(s.layout.extra, key=lambda c: (c[1], c[0]))],
                "pitch_mm": list(g.pitch_mm),
            },
            "frame": ("cell (0,0) centred on the origin; both plates modelled at "
                      f"z {g.z_bottom:g}..{g.z_top:g}; the base plate is used as is, the "
                      f"top plate translated by +{self.top_offset_z_mm:g} mm in z"),
            "plate_size_mm": [round(x1 - x0, 3), round(y1 - y0, 3), g.thickness_mm],
            "plate_extent_mm": [round(v, 3) for v in (x0, y0, x1, y1)],
            "layers": s.layers,
            "top_offset_z_mm": self.top_offset_z_mm,
            "cell_centres_mm": {f"{c[0]},{c[1]}": [round(v, 3) for v in xy]
                                for c, xy in sorted(self.centres.items())},
            "m3_tapped_holes": {"thread": "M3x0.5-6H through", "per_cell": 4,
                                "count": 4 * len(self.centres),
                                "offset_mm": g.m3_offset_mm},
            "pockets": {"d_mm": g.pocket_d_mm, "depth_mm": g.pocket_depth_mm,
                        "face": "inner (cube side)",
                        **{w: [list(c) for c in pocket_cells
                               if not any(p.cell == c and p.plate == w for p in s.ports)]
                           for w in ("top", "base")}},
            "tie_rods": rods,
            "ports": [{"cell": list(p.cell), "plate": p.plate,
                       "thread": f"M{p.thread_major_d_mm:g}x{p.thread_pitch_mm:g}",
                       "aperture_d_mm": p.aperture_d_mm} for p in s.ports],
            "apertures": [{"cell": list(a.cell), "plate": a.plate, "d_mm": a.d_mm}
                          for a in s.apertures],
            "custom_holes": [{"cell": list(h.cell) if h.cell else None,
                              "offset_mm": list(h.offset_mm), "d_mm": h.d_mm,
                              "depth_mm": h.depth_mm, "plate": h.plate, "face": h.face}
                             for h in s.holes],
            "hardware": {
                "tie_rod_screw": (f"{len(self.tie_rods)} x ISO 4762 M3x"
                                  f"{self.screw_length_mm():g}" if self.tie_rods else None),
                "sleeve_nut": (f"{len(self.tie_rods)} x sleeve nut with flat head M3x8, "
                               "shank 4" if self.tie_rods else None),
                "retaining_rings": [f"M{p.thread_major_d_mm:g}x{p.thread_pitch_mm:g}"
                                    for p in s.ports],
                "puzzle_pieces_per_layer": len(self.centres),
                "puzzle_layers": s.layers + 1,
            },
            **({"volume_mm3": {w: round(v, 1) for w, v in self.volumes_mm3.items()},
                "mass_g": {w: round(v * AL_DENSITY_G_MM3, 1)
                           for w, v in self.volumes_mm3.items()}}
               if self.volumes_mm3 else {}),
            **({"files": {k: str(v) for k, v in self.files.items()}} if self.files else {}),
            "warnings": list(self.warnings),
        }


def plan_opm_plates(spec: OpmPlateSpec) -> OpmPlatePlan:
    """Resolve the layout into positions and validate every feature."""
    g, lay = spec.geometry, spec.layout
    if spec.layers < 1:
        raise ValueError("an OPM needs at least one cube layer")
    px, py = g.pitch_mm
    centres = {c: (c[0] * px, c[1] * py) for c in sorted(lay.cells)}
    loops = [[((i - 0.5) * px, (j - 0.5) * py) for i, j in loop]
             for loop in _boundary_loops(lay.cells)]
    if sum(1 for lp in loops if _signed_area(lp) > 0) != 1:
        raise LayoutError("layout must form exactly one plate outline")

    def need(cell, what):
        cell = (int(cell[0]), int(cell[1]))
        if cell not in lay.cells:
            raise LayoutError(f"{what} at cell {cell}, which is not part of the layout")
        return cell

    for p in spec.ports:
        need(p.cell, "port")
        if p.plate not in ("top", "base"):
            raise ValueError(f"port plate must be 'top' or 'base', not {p.plate!r}")
        if p.relief_d_mm / 2 > min(px, py) / 2 - 3.5:
            raise ValueError(f"port at {p.cell}: the {p.relief_d_mm} relief would cut the M3 holes")
    for a in spec.apertures:
        need(a.cell, "aperture")
        if a.plate not in ("top", "base", "both"):
            raise ValueError(f"aperture plate must be top/base/both, not {a.plate!r}")
    for h in spec.holes:
        if h.cell is not None:
            need(h.cell, "custom hole")
        if h.plate not in ("top", "base", "both") or h.face not in ("inner", "outer"):
            raise ValueError(f"custom hole: bad plate/face {h.plate!r}/{h.face!r}")
    seen = {}
    for p in spec.ports:
        key = (tuple(p.cell), p.plate)
        if key in seen:
            raise ValueError(f"two ports in cell {p.cell} of the {p.plate} plate")
        seen[key] = p

    if isinstance(spec.tie_rods, str):
        mode = spec.tie_rods
        if mode == "auto":
            rods = auto_tie_rods(lay.core, g.tie_rod_max_span)
        elif mode == "outline":
            rods = auto_tie_rods(lay.cells, g.tie_rod_max_span)
        elif mode == "none":
            rods = []
        else:
            raise ValueError(f"tie_rods must be 'auto', 'outline', 'none' or a list, not {mode!r}")
    else:
        rods = [TieRod(need(t.cell, "tie rod"), t.corner) for t in spec.tie_rods]

    o = g.tie_rod_offset_mm
    placed, seen_xy = [], set()
    for t in rods:
        sx, sy = t.sign
        cx, cy = centres[t.cell]
        xy = (cx + sx * o, cy + sy * o)
        key = (round(xy[0], 3), round(xy[1], 3))
        if key in seen_xy:
            continue
        seen_xy.add(key)
        open_dirs = set()
        if (t.cell[0] + sx, t.cell[1]) not in lay.cells:
            open_dirs.add("+x" if sx > 0 else "-x")
        if (t.cell[0], t.cell[1] + sy) not in lay.cells:
            open_dirs.add("+y" if sy > 0 else "-y")
        placed.append((t, xy, open_dirs))

    warnings = []
    if spec.tie_rods in ("auto", "outline") and not placed:
        warnings.append("no tie rods placed")
    # The top plate's inner face sits on the top puzzle layer, whose top is at
    # -25 + 55 L; its inner face is z = -30 - T in the plate frame, hence
    # 55 L + 5 + T (120 for two layers and a 5 mm plate, as in OPM-0004).
    top_dz = (CUBE_MM + PUZZLE_LAYER_MM) * spec.layers - CUBE_MM / 2 \
        - (PLATE_INNER_Z - g.thickness_mm)
    return OpmPlatePlan(spec, centres, loops, placed, top_dz, warnings)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def _turns(pts):
    """+1 for a left turn (outside corner w.r.t. material on the left), -1 right."""
    n = len(pts)
    out = []
    for k in range(n):
        din = _dir(pts[k - 1], pts[k])
        dout = _dir(pts[k], pts[(k + 1) % n])
        cr = din[0] * dout[1] - din[1] * dout[0]
        out.append(1 if cr > 0 else -1)
    return out


def _offset_poly(pts, radii, d):
    """Shift a rectilinear loop by ``d`` towards its left side (the material);
    radii follow (outside corners shrink, inside corners grow; sharp stay sharp)."""
    n = len(pts)
    turns = _turns(pts)
    out_pts, out_r = [], []
    for k in range(n):
        din = _dir(pts[k - 1], pts[k])
        dout = _dir(pts[k], pts[(k + 1) % n])
        nx = -din[1] - dout[1]
        ny = din[0] + dout[0]
        out_pts.append((pts[k][0] + d * nx, pts[k][1] + d * ny))
        r = radii[k]
        out_r.append(0.0 if r <= 0 else r - d if turns[k] > 0 else r + d)
    if any(r < 0 for r in out_r):
        raise ValueError("offset larger than a corner radius")
    return out_pts, out_r


def _rounded_wire(pts, radii, z) -> cq.Wire:
    """Closed wire through a rectilinear loop with each corner rounded."""
    n = len(pts)
    V = lambda p: cq.Vector(p[0], p[1], z)  # noqa: E731
    starts, ends, arcs = [], [], []
    for k in range(n):
        v, r = pts[k], radii[k]
        din = _dir(pts[k - 1], v)
        dout = _dir(v, pts[(k + 1) % n])
        if r <= 1e-9:
            starts.append(v)
            ends.append(v)
            arcs.append(None)
            continue
        t1 = (v[0] - din[0] * r, v[1] - din[1] * r)
        t2 = (v[0] + dout[0] * r, v[1] + dout[1] * r)
        c = (t1[0] + dout[0] * r, t1[1] + dout[1] * r)
        s2 = math.sqrt(0.5)
        m = (c[0] + (din[0] - dout[0]) * s2 * r, c[1] + (din[1] - dout[1]) * s2 * r)
        starts.append(t1)
        ends.append(t2)
        arcs.append(m)
    edges = []
    for k in range(n):
        if arcs[k] is not None:
            edges.append(cq.Edge.makeThreePointArc(V(starts[k]), V(arcs[k]), V(ends[k])))
        a, b = ends[k], starts[(k + 1) % n]
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-7:
            edges.append(cq.Edge.makeLine(V(a), V(b)))
    return cq.Wire.assembleEdges(edges)


def _loft(w1: cq.Wire, w2: cq.Wire) -> cq.Solid:
    return cq.Solid.makeLoft([w1, w2], True)


def _prism(pts, radii, z0, z1) -> cq.Solid:
    face = cq.Face.makeFromWires(_rounded_wire(pts, radii, z0))
    return cq.Solid.extrudeLinear(face, cq.Vector(0, 0, z1 - z0))


def _cyl(r, x, y, z0, z1) -> cq.Solid:
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(x, y, z0), cq.Vector(0, 0, 1))


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def _loop_radii(loop, g: PlateGeometry):
    return [g.corner_fillet_mm if t > 0 else g.inside_fillet_mm for t in _turns(loop)]


def _slab(plan: OpmPlatePlan, which: str) -> cq.Shape:
    """Outline extrusion with the outward-face chamfer (a ruled band per loop,
    as ``interface.base_plate`` does: OCC's chamfer chokes on tangent chains)."""
    g = plan.geometry
    zb, zt, c = g.z_bottom, g.z_top, g.outer_chamfer_mm
    outer_is_top = which == "top"
    z_out = zt if outer_is_top else zb
    z_c = z_out - c if outer_is_top else z_out + c            # chamfer's inner rim
    core_z = (zb, z_c) if outer_is_top else (z_c, zt)
    if c <= 0:
        core_z = (zb, zt)
    loops = plan.loops_mm
    outer = next(lp for lp in loops if _signed_area(lp) > 0)
    holes = [lp for lp in loops if _signed_area(lp) < 0]
    face = cq.Face.makeFromWires(
        _rounded_wire(outer, _loop_radii(outer, g), core_z[0]),
        [_rounded_wire(h, _loop_radii(h, g), core_z[0]) for h in holes])
    body: cq.Shape = cq.Solid.extrudeLinear(face, cq.Vector(0, 0, core_z[1] - core_z[0]))
    if c > 0:
        r0 = _loop_radii(outer, g)
        p1, r1 = _offset_poly(outer, r0, c)
        band: cq.Shape = _loft(_rounded_wire(outer, r0, z_c), _rounded_wire(p1, r1, z_out))
        for h in holes:
            rh = _loop_radii(h, g)
            ph, rh1 = _offset_poly(h, rh, c)
            band = band.cut(_loft(_rounded_wire(h, rh, z_c), _rounded_wire(ph, rh1, z_out)))
        body = body.fuse(band).clean()
    return body


def _recess_outline(plan: OpmPlatePlan, rod, xy, open_dirs):
    """Plan-view outline (rectilinear loop + corner radii, CCW) of a base-plate
    sleeve-nut recess: an R4.5 round, run out into a U-slot towards each plate
    edge it would otherwise graze (the rod sits only 4.5 from a free edge)."""
    g = plan.geometry
    R, c = g.base_recess_r_mm, g.outer_chamfer_mm
    px, py = g.pitch_mm
    sx, sy = rod.sign
    cx, cy = plan.centres[rod.cell]
    x, y = xy
    run = c + 1.0                                     # slot overshoot past the edge
    xo = bool(open_dirs & {"+x", "-x"})
    yo = bool(open_dirs & {"+y", "-y"})
    x_in, y_in = x - sx * R, y - sy * R               # the plate-interior side
    x_out = cx + sx * (px / 2 + run) if xo else x + sx * R
    y_out = cy + sy * (py / 2 + run) if yo else y + sy * R
    xa, xb = sorted((x_in, x_out))
    ya, yb = sorted((y_in, y_out))
    pts = [(xa, ya), (xb, ya), (xb, yb), (xa, yb)]    # CCW
    # Round (R) every corner that stays inside the plate: along an open axis
    # only the interior side, along a closed axis both sides. No slot -> a
    # circle; one slot -> a U; a corner rod -> a notch with one rounded corner.
    radii = [R if ((not xo or math.isclose(vx, x_in, abs_tol=1e-9))
                   and (not yo or math.isclose(vy, y_in, abs_tol=1e-9))) else 0.0
             for vx, vy in pts]
    return pts, radii


def _recess_cutter(plan: OpmPlatePlan, rod, xy, open_dirs) -> cq.Shape:
    """The recess as a cutter: 2.4 deep, 45 deg chamfer where it meets the face."""
    g = plan.geometry
    c = g.outer_chamfer_mm
    pts, radii = _recess_outline(plan, rod, xy, open_dirs)
    zb = g.z_bottom
    depth = g.base_recess_depth_mm
    body: cq.Shape = _prism(pts, radii, zb - 1.0, zb + depth)
    if c > 0:
        p1, r1 = _offset_poly(pts, radii, -c)         # grows outward
        body = body.fuse(_loft(_rounded_wire(pts, radii, zb + c),
                               _rounded_wire(p1, r1, zb)))
        body = body.fuse(_prism(p1, r1, zb - 1.0, zb))
    return body


def _port_cutter(plan: OpmPlatePlan, port: Port) -> cq.Shape:
    """Revolved M37x0.5 port: thread minor from the inner face, 45 deg step to
    the relief, lip with the clear aperture on the outward face."""
    g = plan.geometry
    T = g.thickness_mm
    if port.plate == "top":
        z_in, s = g.z_bottom, 1.0             # inner face at the bottom, depth goes +z
    else:
        z_in, s = g.z_top, -1.0
    rm = port.thread_minor_d_mm / 2
    rr = port.relief_d_mm / 2
    ra = port.aperture_d_mm / 2
    d_relief = T - port.lip_mm - port.relief_mm           # relief starts here
    d_thread = d_relief - (rr - rm)                        # 45 deg step
    prof = [(0.0, -1.0), (rm, -1.0), (rm, d_thread), (rr, d_relief),
            (rr, T - port.lip_mm), (ra, T - port.lip_mm), (ra, T + 1.0), (0.0, T + 1.0)]
    pts = [(r, z_in + s * d) for r, d in prof]
    solid = (cq.Workplane("XZ").polyline(pts).close()
             .revolve(360, (0, 0, 0), (0, 1, 0)).val())
    x, y = plan.centres[port.cell]
    return solid.translate(cq.Vector(x, y, 0))


def build_plate(plan: OpmPlatePlan, which: str) -> cq.Workplane:
    """One plate (``"top"`` or ``"base"``) in the common plate frame."""
    if which not in ("top", "base"):
        raise ValueError("which must be 'top' or 'base'")
    spec, g = plan.spec, plan.geometry
    zb, zt, T = g.z_bottom, g.z_top, g.thickness_mm
    inner_z = zb if which == "top" else zt
    outer_z = zt if which == "top" else zb
    into = 1.0 if which == "top" else -1.0          # from the inner face into the plate
    body = _slab(plan, which)

    # 4 x M3 tapped through per cell
    o, r3 = g.m3_offset_mm, g.m3_hole_d_mm / 2
    m3 = [_cyl(r3, x + dx, y + dy, zb - 1, zt + 1)
          for (x, y) in plan.centres.values()
          for dx, dy in ((o, 0), (-o, 0), (0, o), (0, -o))]
    cutters = list(m3)

    # pockets on the cube side (not under a port of this plate)
    port_cells = {p.cell for p in spec.ports if p.plate == which}
    if spec.pockets and g.pocket_d_mm > 0:
        for cell, (x, y) in plan.centres.items():
            if cell in port_cells:
                continue
            z0, z1 = sorted((inner_z - into * 1.0, inner_z + into * g.pocket_depth_mm))
            cutters.append(_cyl(g.pocket_d_mm / 2, x, y, z0, z1))

    # tie rods
    for rod, (x, y), open_dirs in plan.tie_rods:
        if which == "top":
            cutters.append(_cyl(g.top_rod_d_mm / 2, x, y, zb - 1, zt + 1))
            cutters.append(_cyl(g.top_rod_cbore_d_mm / 2, x, y,
                                zt - g.top_rod_cbore_depth_mm, zt + 1))
        else:
            cutters.append(_cyl(g.base_rod_d_mm / 2, x, y, zb - 1, zt + 1))
            cutters.append(_recess_cutter(plan, rod, (x, y), open_dirs))

    # plain apertures
    for a in spec.apertures:
        if a.plate not in (which, "both"):
            continue
        x, y = plan.centres[a.cell]
        x, y = x + a.offset_mm[0], y + a.offset_mm[1]
        cutters.append(_cyl(a.d_mm / 2, x, y, zb - 1, zt + 1))
        if a.chamfer_mm > 0:
            # 45 deg cone: d/2 + ch at the outward face, d/2 at depth ch; it
            # starts 0.5 mm outside the face so the cut is clean
            e, inward = 0.5, (-1.0 if which == "top" else 1.0)
            cutters.append(cq.Solid.makeCone(
                a.d_mm / 2 + a.chamfer_mm + e, a.d_mm / 2, a.chamfer_mm + e,
                cq.Vector(x, y, outer_z - inward * e), cq.Vector(0, 0, inward)))

    # custom holes
    for h in spec.holes:
        if h.plate not in (which, "both"):
            continue
        cx, cy = plan.centres[h.cell] if h.cell is not None else (0.0, 0.0)
        x, y = cx + h.offset_mm[0], cy + h.offset_mm[1]
        if h.depth_mm is None:
            z0, z1 = zb - 1, zt + 1
        else:
            face_z = outer_z if h.face == "outer" else inner_z
            inward = (1.0 if face_z == zb else -1.0)
            z0, z1 = sorted((face_z - inward * 1.0, face_z + inward * h.depth_mm))
        cutters.append(_cyl(h.d_mm / 2, x, y, z0, z1))

    # One boolean, every cutter as its OWN tool argument. Never wrap them in a
    # single compound: OCC treats a compound argument as one non-self-
    # intersecting shape, and the coaxial through-hole + counterbore pairs
    # overlap -- the counterbores then silently vanish (and the recess cutters
    # can send the boolean into a multi-GB spin).
    cutters += [_port_cutter(plan, p) for p in spec.ports if p.plate == which]
    body = body.cut(*cutters).clean()
    return cq.Workplane("XY").add(body)


def build_opm_plates(spec_or_plan) -> dict[str, cq.Workplane]:
    plan = spec_or_plan if isinstance(spec_or_plan, OpmPlatePlan) else plan_opm_plates(spec_or_plan)
    return {"top": build_plate(plan, "top"), "base": build_plate(plan, "base")}


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def generate(spec: OpmPlateSpec, out_dir: str | Path = "generated", stem: str | None = None,
             stl: bool = True, assembly: bool = True, diagram: bool = True) -> OpmPlatePlan:
    """Plan, build and write ``<stem>_top/_base.step|.stl``, ``<stem>_stack.step``
    (both plates in place), ``<stem>_plan.json`` and ``<stem>_layout.png``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = stem or spec.stem()
    plan = plan_opm_plates(spec)
    parts = build_opm_plates(plan)
    files: dict[str, Path] = {}
    volumes = {}
    for which, wp in parts.items():
        step = out / f"{stem}_{which}.step"
        cq.exporters.export(wp, str(step))
        files[f"{which}_step"] = step
        if stl:
            p = out / f"{stem}_{which}.stl"
            cq.exporters.export(wp, str(p), tolerance=0.02, angularTolerance=0.1)
            files[f"{which}_stl"] = p
        volumes[which] = wp.val().Volume()
    if assembly:
        asm = cq.Assembly(name=stem)
        asm.add(parts["base"], name="base_plate", color=cq.Color(0.25, 0.25, 0.27))
        asm.add(parts["top"], name="top_plate", color=cq.Color(0.35, 0.35, 0.38),
                loc=cq.Location(cq.Vector(0, 0, plan.top_offset_z_mm)))
        p = out / f"{stem}_stack.step"
        if hasattr(asm, "export"):
            asm.export(str(p))
        else:  # pragma: no cover - older CadQuery
            asm.save(str(p))
        files["stack_step"] = p
    if diagram:
        try:
            png = out / f"{stem}_layout.png"
            plot_plates(plan, png)
            files["layout_png"] = png
        except ImportError:
            plan.warnings.append("matplotlib missing: no layout diagram")
    files["plan_json"] = out / f"{stem}_plan.json"
    plan.files = files
    plan.volumes_mm3 = volumes
    files["plan_json"].write_text(json.dumps(plan.report(), indent=2))
    return plan


def plot_plates(plan: OpmPlatePlan, path: str | Path):
    """Plan view of both plates (seen from above): cells, holes, rods, ports."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon, Rectangle

    g, spec = plan.geometry, plan.spec
    px, py = g.pitch_mm
    x0, y0, x1, y1 = plan.extent()
    w, h = x1 - x0, y1 - y0
    fig, axes = plt.subplots(1, 2, figsize=(2 * (2.2 + w / 60), 1.6 + h / 60))
    for ax, which in zip(axes, ("base", "top")):
        outline = None
        for loop in plan.loops_mm:
            pts = _outline_points(loop, _loop_radii(loop, g))
            hole = _signed_area(loop) < 0
            patch = ax.add_patch(Polygon(pts, closed=True, fc="white" if hole else "#d9dde3",
                                         ec="#333", lw=1.2, zorder=1 if not hole else 2))
            outline = outline or (None if hole else patch)
        for cell, (x, y) in plan.centres.items():
            core = cell in spec.layout.core
            ax.add_patch(Rectangle((x - px / 2, y - py / 2), px, py, fill=False,
                                   ec="#8a94a6" if core else "#c08a2d", lw=0.6,
                                   ls="--", zorder=3))
            ax.text(x, y + py * 0.3, f"{cell[0]},{cell[1]}", ha="center", va="center",
                    fontsize=7, color="#555" if core else "#a0671a", zorder=6)
            for dx, dy in ((g.m3_offset_mm, 0), (-g.m3_offset_mm, 0),
                           (0, g.m3_offset_mm), (0, -g.m3_offset_mm)):
                ax.add_patch(Circle((x + dx, y + dy), g.m3_hole_d_mm / 2, fc="white",
                                    ec="#333", lw=0.5, zorder=4))
            port = next((p for p in spec.ports if p.cell == cell and p.plate == which), None)
            if port:
                ax.add_patch(Circle((x, y), port.relief_d_mm / 2, fc="none", ec="#1f5fbf",
                                    lw=1.0, ls=":", zorder=4))
                ax.add_patch(Circle((x, y), port.aperture_d_mm / 2, fc="white",
                                    ec="#1f5fbf", lw=1.2, zorder=4))
                ax.text(x, y, f"M{port.thread_major_d_mm:g}", ha="center", va="center",
                        fontsize=7, color="#1f5fbf", zorder=6)
            elif spec.pockets:
                ax.add_patch(Circle((x, y), g.pocket_d_mm / 2, fc="none", ec="#8a94a6",
                                    lw=0.7, ls="--", zorder=3))
        for a in spec.apertures:
            if a.plate in (which, "both"):
                x, y = plan.centres[a.cell]
                ax.add_patch(Circle((x + a.offset_mm[0], y + a.offset_mm[1]), a.d_mm / 2,
                                    fc="white", ec="#1f5fbf", lw=1.2, zorder=4))
        for h_ in spec.holes:
            if h_.plate in (which, "both"):
                cx, cy = plan.centres[h_.cell] if h_.cell is not None else (0.0, 0.0)
                ax.add_patch(Circle((cx + h_.offset_mm[0], cy + h_.offset_mm[1]), h_.d_mm / 2,
                                    fc="white" if h_.depth_mm is None else "#eef",
                                    ec="#6a3d9a", lw=0.8, zorder=4))
        for rod, (x, y), open_dirs in plan.tie_rods:
            if which == "top":
                ax.add_patch(Circle((x, y), g.top_rod_cbore_d_mm / 2, fc="#f4c7c3",
                                    ec="#b3261e", lw=0.8, zorder=5))
            else:
                pts, radii = _recess_outline(plan, rod, (x, y), open_dirs)
                ax.add_patch(Polygon(_outline_points(pts, radii), closed=True, fc="#f4c7c3",
                                     ec="#b3261e", lw=0.8, zorder=5)).set_clip_path(outline)
            ax.add_patch(Circle((x, y), 1.6, fc="#b3261e", ec="none", zorder=6))
        ax.set_xlim(x0 - 12, x1 + 12)
        ax.set_ylim(y0 - 12, y1 + 12)
        ax.set_aspect("equal")
        ax.set_title(f"{which} plate - {spec.layout.label()}  ({w:.1f} x {h:.1f} mm)",
                     fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(False)
    fig.text(0.5, 0.01,
             f"grey = core cells, orange = extra puzzle units; red = {len(plan.tie_rods)} tie rods "
             f"(M3x{plan.screw_length_mm():g}); blue = ports/apertures; dashed circles = "
             f"{g.pocket_d_mm:g} mm pockets on the cube side",
             ha="center", fontsize=7, color="#444")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _outline_points(pts, radii, seg=8):
    """Polyline approximation of a rounded loop (for plotting)."""
    out = []
    n = len(pts)
    for k in range(n):
        v, r = pts[k], radii[k]
        din = _dir(pts[k - 1], v)
        dout = _dir(v, pts[(k + 1) % n])
        if r <= 0:
            out.append(v)
            continue
        t1 = (v[0] - din[0] * r, v[1] - din[1] * r)
        c = (t1[0] + dout[0] * r, t1[1] + dout[1] * r)
        a0 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        t2 = (v[0] + dout[0] * r, v[1] + dout[1] * r)
        a1 = math.atan2(t2[1] - c[1], t2[0] - c[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for i in range(seg + 1):
            a = a0 + da * i / seg
            out.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return out


# ---------------------------------------------------------------------------
# presets, dict interface (optikit) and CLI
# ---------------------------------------------------------------------------

def released_3x8_1x1() -> OpmPlateSpec:
    """PRT-1051 / PRT-1052 (FLIM 488): 3x8 core, one extra unit left of cell
    (0,0), M37 port in the top plate's far-end middle cell. (The base plate's
    module-specific extras -- feet pockets, 2.1 slots -- are not included.)"""
    return OpmPlateSpec(layout=PlateLayout.parse("3x8+1x1@-1,0"), ports=(Port(cell=(1, 7)),),
                        name="opm_3x8+1x1")


def _cell(v) -> Cell:
    if isinstance(v, str):
        a, b = v.replace("(", "").replace(")", "").split(",")
        return (int(a), int(b))
    return (int(v[0]), int(v[1]))


def layout_and_ports_from_ascii(art: str, name: str = "", plate: str = "top"
                                ) -> tuple[PlateLayout, tuple[Port, ...]]:
    """An ASCII layout plus the M37 ports its ``P``/``p`` cells mark."""
    core, extra, ports = _parse_ascii(art)
    layout = PlateLayout(frozenset(core | extra), frozenset(core), name)
    return layout, tuple(Port(cell=c, plate=plate) for c in sorted(ports))


def _ascii_of(v) -> str | None:
    """The ASCII art in a layout value, if it is one."""
    if isinstance(v, dict) and "ascii" in v:
        v = v["ascii"]
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, str) for x in v):
        v = "\n".join(v)
    if isinstance(v, str) and ("\n" in v.strip() or re.fullmatch(r"[#Xx+oOPp.\s-]+", v.strip())):
        return v
    return None


def layout_from_any(v) -> PlateLayout:
    """A layout from a spec string, ASCII art, a list of cells or a dict."""
    if isinstance(v, PlateLayout):
        return v
    art = _ascii_of(v)
    if art is not None:
        return PlateLayout.from_ascii(art, v.get("name", "") if isinstance(v, dict) else "")
    if isinstance(v, str):
        return PlateLayout.parse(v)
    if isinstance(v, dict):
        if "spec" in v:
            return PlateLayout.parse(v["spec"])
        return PlateLayout.from_cells(v["cells"], v.get("core", ()), v.get("name", ""))
    return PlateLayout.from_cells(v)


def spec_from_dict(d: dict) -> OpmPlateSpec:
    """Build a spec from JSON-able parameters (the optikit generator surface).

    Keys: ``layout`` (spec string / ASCII / cell list / dict), ``layers``,
    ``ports`` [{cell, plate}], ``apertures`` [{cell, d_mm, plate, chamfer_mm}],
    ``holes`` [{d_mm, offset_mm, cell, depth_mm, plate, face}],
    ``tie_rods`` ("auto" | "outline" | "none" | [{cell, corner}]),
    ``pockets`` (bool), ``pitch_mm`` [x, y], ``m3_hole_d_mm``, ``name``.
    ``P``/``p`` cells of an ASCII layout add top-plate ports.
    """
    art = _ascii_of(d["layout"])
    if art is not None:
        layout, marked = layout_and_ports_from_ascii(
            art, d["layout"].get("name", "") if isinstance(d["layout"], dict) else "")
    else:
        layout, marked = layout_from_any(d["layout"]), ()
    geo = PlateGeometry()
    over = {k: d[k] for k in ("m3_hole_d_mm", "thickness_mm", "pocket_d_mm",
                              "pocket_depth_mm") if k in d}
    if "pitch_mm" in d:
        p = d["pitch_mm"]
        over["pitch_mm"] = (float(p), float(p)) if isinstance(p, (int, float)) \
            else (float(p[0]), float(p[1]))
    if over:
        geo = replace(geo, **over)
    rods = d.get("tie_rods", "auto")
    if not isinstance(rods, str):
        rods = tuple(TieRod(_cell(t["cell"]), t["corner"]) for t in rods)
    return OpmPlateSpec(
        layout=layout,
        layers=int(d.get("layers", 2)),
        ports=tuple(marked) + tuple(
            Port(cell=_cell(p["cell"]), plate=p.get("plate", "top"),
                 **{k: p[k] for k in ("aperture_d_mm", "thread_major_d_mm",
                                      "thread_pitch_mm", "relief_d_mm",
                                      "lip_mm", "relief_mm") if k in p})
            for p in d.get("ports", ())),
        apertures=tuple(Aperture(cell=_cell(a["cell"]), d_mm=float(a["d_mm"]),
                                 plate=a.get("plate", "top"),
                                 chamfer_mm=float(a.get("chamfer_mm", 0.0)),
                                 offset_mm=tuple(a.get("offset_mm", (0.0, 0.0))))
                        for a in d.get("apertures", ())),
        holes=tuple(CustomHole(d_mm=float(h["d_mm"]),
                               offset_mm=tuple(h.get("offset_mm", (0.0, 0.0))),
                               cell=_cell(h["cell"]) if h.get("cell") is not None else None,
                               depth_mm=h.get("depth_mm"), plate=h.get("plate", "base"),
                               face=h.get("face", "outer"))
                    for h in d.get("holes", ())),
        tie_rods=rods,
        pockets=bool(d.get("pockets", True)),
        geometry=geo,
        name=d.get("name"),
    )


def build_parts(params: dict) -> dict[str, cq.Workplane]:
    """optikit generator contract: ``{"top": ..., "base": ...}``."""
    return build_opm_plates(spec_from_dict(params))


def _cli(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="uc2cad plates",
        description="Top and base plates of an openUC2 V4 optical module for any "
                    "layout: a core rectangle plus extra puzzle units on any side.",
        epilog="examples:\n"
               "  uc2cad plates --layout 3x3\n"
               "  uc2cad plates --layout 3x8+1x1@-1,0 --port 1,7\n"
               "  uc2cad plates --layout '3x3@0,3+1x2@1,1' --tie-rods outline "
               "--aperture 1,5:35:1\n"
               "  uc2cad plates --ascii-file module.txt --layers 1\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--layout", help="core rectangle + blocks, e.g. 3x8+1x1@-1,0 "
                                      "(blocks: +WxH@c,r adds, -WxH@c,r removes)")
    src.add_argument("--ascii-file", help="text file: '#' core cell, '+' extra unit, "
                                          "'P'/'p' cell with an M37 port, '.' empty")
    ap.add_argument("--layers", type=int, default=2, help="cube layers in the stack (default 2)")
    ap.add_argument("--port", action="append", default=[], metavar="C,R[:top|base]",
                    help="M37x0.5 retaining-ring port in a cell (repeatable)")
    ap.add_argument("--aperture", action="append", default=[], metavar="C,R:D[:CH[:PLATE]]",
                    help="plain through hole of diameter D at a cell centre, optional "
                         "45 deg chamfer CH on the outward face (plate top|base|both)")
    ap.add_argument("--tie-rods", default="auto",
                    help="'auto' (core corners), 'outline' (all outside corners), 'none', "
                         "or 'c,r:corner;...' e.g. '0,0:sw;2,0:se'")
    ap.add_argument("--no-pockets", action="store_true", help="omit the 38 mm cell pockets")
    ap.add_argument("--pitch", default=None, help="cell pitch x,y in mm (default 50,50.1)")
    ap.add_argument("--m3-hole", type=float, default=None,
                    help="M3 hole diameter (default 2.46 = tapped; 3.2 for clearance)")
    ap.add_argument("--name", default=None, help="output stem")
    ap.add_argument("--out-dir", default="generated")
    ap.add_argument("--no-stl", action="store_true")
    ap.add_argument("--no-stack", action="store_true", help="skip the assembled stack STEP")
    ap.add_argument("--plan-only", action="store_true", help="print the plan, build nothing")
    args = ap.parse_args(argv)

    ports: list = []
    if args.ascii_file:
        layout, marked = layout_and_ports_from_ascii(Path(args.ascii_file).read_text(),
                                                     name=Path(args.ascii_file).stem)
        ports += marked
    else:
        layout = PlateLayout.parse(args.layout or "3x8+1x1@-1,0")
    for p in args.port:
        cell, _, plate = p.partition(":")
        ports.append(Port(cell=_cell(cell), plate=plate or "top"))
    apertures = []
    for a in args.aperture:
        parts = a.split(":")
        apertures.append(Aperture(cell=_cell(parts[0]), d_mm=float(parts[1]),
                                  chamfer_mm=float(parts[2]) if len(parts) > 2 and parts[2] else 0.0,
                                  plate=parts[3] if len(parts) > 3 else "top"))
    rods: str | tuple = args.tie_rods
    if rods not in ("auto", "outline", "none"):
        rods = tuple(TieRod(_cell(item.split(":")[0]), item.split(":")[1].strip().lower())
                     for item in rods.split(";") if item.strip())
    geo = PlateGeometry()
    if args.pitch:
        vals = [float(v) for v in args.pitch.split(",")]
        geo = replace(geo, pitch_mm=(vals[0], vals[-1]))
    if args.m3_hole:
        geo = replace(geo, m3_hole_d_mm=args.m3_hole)
    spec = OpmPlateSpec(layout=layout, layers=args.layers, ports=tuple(ports),
                        apertures=tuple(apertures), tie_rods=rods,
                        pockets=not args.no_pockets, geometry=geo, name=args.name)
    if args.plan_only:
        print(json.dumps(plan_opm_plates(spec).report(), indent=2))
        return
    plan = generate(spec, out_dir=args.out_dir, stl=not args.no_stl,
                    assembly=not args.no_stack)
    rep = plan.report()
    print(layout.to_ascii())
    print(json.dumps({k: rep[k] for k in ("plate_size_mm", "layers", "top_offset_z_mm",
                                          "mass_g", "hardware", "warnings")}, indent=2))
    for k, v in plan.files.items():
        print(f"  {k:10s} {v}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        _cli()
    else:                                   # no args: the released FLIM 488 pair
        plan = generate(released_3x8_1x1())
        print(json.dumps(plan.report()["hardware"], indent=2))
