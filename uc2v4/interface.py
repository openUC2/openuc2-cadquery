"""The openUC2 V4 square-insert planform (top-view outline).

All coordinates were extracted from the Inventor masters via COM and
cross-checked against exact z=0 STEP sections of the released parts:

- MAS - 2003 - Master Insert - B  (-> PRT - 2123 - MASLCK - V04 - B)
- MAS - 2013 - Square Inserts     (-> PRT - 2027 - INSLEND43F-50 - V04)

Naming (Inventor parameter names in parentheses):

- ``grid`` (Grid, 50 mm): the openUC2 cube pitch. The insert envelope is
  ``grid - 0.6`` = 49.4 mm square.
- ``shoulder_half`` (InsertWidth/2): half width of the flat "shoulder" region
  that slides in the cube's internal tracks. 16.9 mm for the master insert
  (CubeClearWidth - 0.2), 16.95 mm for the square inserts (- 0.1).
- ``corner_across`` (CubeClearDiagonalV04 - 0.4|0.2): across-corners width of
  the 45-degree corner flats that clear the cube's corner posts.
- Four flexure springs (two per +-Y side) are cut free from the plate; each
  carries a rounded hook nose. In the sliding variants the nose tip stays
  ~0.1 mm below the 49.4 envelope and only provides friction; the (currently
  suppressed) "tongue" master feature adds the positive-locking bumps.

The spring outline is stored as an exact segment template (line/arc chain,
CCW), anchored to the outer edge and the shoulder plane, because its
molded shape is fixed tooling geometry - reproduced verbatim, shifted rigidly
if the caller changes ``edge_half``/``shoulder_half``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

GRID_MM = 50.0

# ---------------------------------------------------------------------------
# segment primitives: ("L", (x, y)) line-to, ("A", (cx, cy), r, (x, y)) arc-to
# ---------------------------------------------------------------------------

Seg = tuple


def _arc_mid(start, seg):
    """Mid point of a minor arc from *start* to seg end around seg center."""
    (cx, cy), r, (ex, ey) = seg[1], seg[2], seg[3]
    sx, sy = start
    v1 = ((sx - cx) / r, (sy - cy) / r)
    v2 = ((ex - cx) / r, (ey - cy) / r)
    bx, by = v1[0] + v2[0], v1[1] + v2[1]
    n = math.hypot(bx, by)
    if n < 1e-9:  # 180 deg arc would be ambiguous; none occur in the outline
        raise ValueError("ambiguous 180 deg arc in outline template")
    return (cx + r * bx / n, cy + r * by / n)


def _mirror_x(segs, start):
    """Mirror a segment run across the YZ plane, reversing its direction.

    *start* is the (implicit) start point of the original run. The mirrored
    run goes from mirror(end-of-run) to mirror(start).
    """
    pts = [start] + [s[-1] for s in segs]  # P0 .. Pn
    out = []
    for i in range(len(segs) - 1, -1, -1):
        s = segs[i]
        tgt = pts[i]  # start point of original segment i
        if s[0] == "L":
            out.append(("L", (-tgt[0], tgt[1])))
        else:
            (cx, cy), r = s[1], s[2]
            out.append(("A", (-cx, cy), r, (-tgt[0], tgt[1])))
    return out


def _rot180(segs):
    out = []
    for s in segs:
        if s[0] == "L":
            out.append(("L", (-s[1][0], -s[1][1])))
        else:
            out.append(("A", (-s[1][0], -s[1][1]), s[2], (-s[3][0], -s[3][1])))
    return out


def _shift(segs, dx, dy):
    out = []
    for s in segs:
        if s[0] == "L":
            out.append(("L", (s[1][0] + dx, s[1][1] + dy)))
        else:
            out.append(("A", (s[1][0] + dx, s[1][1] + dy), s[2],
                        (s[3][0] + dx, s[3][1] + dy)))
    return out


# ---------------------------------------------------------------------------
# spring templates (exact, from the z=0 sections of the released parts)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpringTemplate:
    """Exact CCW outline run of one spring cut (right-hand instance, +Y edge).

    Runs from the end of the corner diagonal at (wall_x, y) to the start of
    the straight top edge. Coordinates are absolute for the default 49.4
    envelope; they are shifted rigidly when edge/shoulder change.
    """

    edge_half0: float          # envelope half width the template was traced at
    shoulder_half0: float      # shoulder half width it was traced at
    top_edge_x: float          # |x| where the straight top edge begins
    segments: tuple            # Seg chain, starting after the corner diagonal

    def run(self, edge_half: float, shoulder_half: float):
        return _shift(list(self.segments),
                      shoulder_half - self.shoulder_half0,
                      edge_half - self.edge_half0)


# PRT - 2123 - MASLCK - V04 - B (master insert, sliding): slot lobes r=1.0
MASTER_SPRING = SpringTemplate(
    edge_half0=24.7,
    shoulder_half0=16.9,
    top_edge_x=12.8481,
    segments=(
        ("L", (16.9, 23.1356)),
        ("A", (17.1, 23.1356), 0.2, (16.981, 23.2964)),
        ("L", (17.1508, 23.422)),
        ("A", (16.8534, 23.8239), 0.5, (17.3525, 23.7934)),
        ("L", (17.3687, 24.0597)),
        ("A", (16.8697, 24.0903), 0.5, (16.9002, 24.5893)),   # nose tip
        ("L", (16.3715, 24.6217)),
        ("A", (16.341, 24.1226), 0.5, (15.8447, 24.1835)),    # valley
        ("L", (15.4303, 20.8085)),                            # finger, 7 deg
        ("A", (16.4229, 20.6866), 1.0, (15.5289, 20.2385)),
        ("A", (14.6349, 19.7904), 1.0, (13.8158, 19.2168)),   # slot end lobe
        ("L", (13.529, 19.6264)),
        ("A", (14.3481, 20.2), 1.0, (13.3481, 20.2)),
        ("L", (13.3481, 24.2)),
        ("A", (12.8481, 24.2), 0.5, (12.8481, 24.7)),
    ),
)

# PRT - 2027 - INSLEND43F-50 - V04 (square insert family): slot lobes r=0.75
SQUARE_SPRING = SpringTemplate(
    edge_half0=24.7,
    shoulder_half0=16.95,
    top_edge_x=13.4,
    segments=(
        ("L", (16.95, 23.181)),
        ("A", (17.15, 23.181), 0.2, (17.031, 23.3418)),
        ("L", (17.1394, 23.422)),
        ("A", (16.842, 23.8239), 0.5, (17.3411, 23.7934)),
        ("L", (17.3574, 24.0597)),
        ("A", (16.8583, 24.0903), 0.5, (16.8888, 24.5893)),   # nose tip
        ("L", (16.3602, 24.6217)),
        ("A", (16.3296, 24.1226), 0.5, (15.8334, 24.1835)),   # valley
        ("L", (15.4745, 21.2612)),                            # finger, 7 deg
        ("A", (16.4671, 21.1394), 1.0, (15.5926, 20.6543)),
        ("A", (14.9368, 20.2904), 0.75, (14.3224, 19.8602)),  # slot end lobe
        ("L", (14.0356, 20.2698)),
        ("A", (14.65, 20.7), 0.75, (13.9, 20.7)),
        ("L", (13.9, 24.2)),
        ("A", (13.4, 24.2), 0.5, (13.4, 24.7)),
    ),
)


# ---------------------------------------------------------------------------
# interface parameter sets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SquareInsertInterface:
    """Common outline of the square-insert family (MAS-2013 lineage)."""

    grid: float = GRID_MM
    outer_clearance: float = 0.6           # envelope = grid - clearance
    shoulder_half: float = 16.95           # InsertWidth/2 = 33.9/2
    corner_across: float = 53.54           # CubeClearDiagonalV04 - 0.2
    corner_fillet: float = 0.4             # vertical corner-edge fillet
    outer_chamfer: float = 0.4             # OuterChamfer, top+bottom outline
    springs: SpringTemplate | None = SQUARE_SPRING

    @property
    def edge_half(self) -> float:
        return (self.grid - self.outer_clearance) / 2.0

    @property
    def diag_sum(self) -> float:
        """x + y = diag_sum is the 45 deg corner-flat line."""
        return self.corner_across / math.sqrt(2.0)

    def corner_run(self):
        """CCW +x/+y corner segments: edge -> corner flat -> shoulder wall.

        Returns (segments, edge_end_y) where edge_end_y is the |y| at which
        the straight side edge (x = edge_half) ends and the corner begins.
        """
        e, w, r = self.edge_half, self.shoulder_half, self.corner_fillet
        return [
            ("A", (e - r, w - r), r, (e - r, w)),
            ("L", (self.diag_sum - w, w)),
            ("L", (w, self.diag_sum - w)),
        ], w - r

    def outline_wire(self) -> cq.Workplane:
        return _build_outline(self)


@dataclass(frozen=True)
class MasterInsertInterface(SquareInsertInterface):
    """Outline of the master insert (MAS-2003 lineage).

    Tighter shoulder/corner clearances and a larger (0.5) vertical fillet on
    the corner-ledge edges. The mid-height V-groove that relieves the cube's
    notch-rib band is a 3D feature and lives in master_insert.py.
    """

    shoulder_half: float = 16.9            # InsertWidth/2 = 33.8/2
    corner_across: float = 53.34           # CubeClearDiagonalV04 - 0.4
    corner_fillet: float = 0.5
    springs: SpringTemplate | None = MASTER_SPRING


# ---------------------------------------------------------------------------
# outline assembly
# ---------------------------------------------------------------------------

def _emit(wp, segs, start):
    prev = start
    for s in segs:
        if s[0] == "L":
            if math.hypot(s[1][0] - prev[0], s[1][1] - prev[1]) > 1e-9:
                wp = wp.lineTo(*s[1])
            prev = s[1]
        else:
            mid = _arc_mid(prev, s)
            wp = wp.threePointArc(mid, s[3])
            prev = s[3]
    return wp, prev


def _build_outline(iface: SquareInsertInterface) -> cq.Workplane:
    """Closed planform wire on the XY plane (CCW)."""
    e = iface.edge_half
    w = iface.shoulder_half

    corner, edge_end_y = iface.corner_run()
    corner_start = (e, edge_end_y)
    diag_end = (w, iface.diag_sum - w)
    if iface.springs is not None:
        spring = iface.springs.run(e, w)
        top_x = iface.springs.top_edge_x + (w - iface.springs.shoulder_half0)
    else:
        # No springs: the shoulder wall runs straight up to the top edge.
        spring = [("L", (w, e))]
        top_x = w

    # +Y half, CCW from (e, edge_end_y):
    half = []
    half += corner                                  # to (w, diag_sum - w)
    half += spring                                  # to (top_x, e)
    half += [("L", (-top_x, e))]                    # top edge
    half += _mirror_x(spring, diag_end)             # to (-w, diag_sum - w)
    half += _mirror_x(corner, corner_start)         # to (-e, edge_end_y)
    half += [("L", (-e, -edge_end_y))]              # left edge

    full = half + _rot180(half)

    wp = cq.Workplane("XY").moveTo(*corner_start)
    wp, _ = _emit(wp, full[:-1], corner_start)
    return wp.close()


def base_plate(iface: SquareInsertInterface, thickness: float) -> cq.Workplane:
    """Extruded insert plate, mid-plane z=0, with the outer chamfer applied.

    OCC's chamfer operation cannot handle the tangent-continuous spring
    outline, so the 45 deg chamfer band is built explicitly: a ruled loft
    between the outline and its inward offset, glued onto a shortened core
    extrusion. ``kind="intersection"`` miters the offset corners, which is
    exactly what a chamfer does there.
    """
    ch = iface.outer_chamfer
    t2 = thickness / 2.0
    wp = iface.outline_wire()
    if ch <= 0:
        return wp.extrude(t2, both=True).clean()

    wire = wp.wires().val()
    off = wire.offset2D(-ch, kind="intersection")[0]

    def at(w, z):
        return w.moved(cq.Location(cq.Vector(0, 0, z)))

    core = wp.extrude(t2 - ch, both=True)
    top = cq.Solid.makeLoft([at(wire, t2 - ch), at(off, t2)], ruled=True)
    bottom = cq.Solid.makeLoft([at(wire, -(t2 - ch)), at(off, -t2)], ruled=True)
    plate = core.union(cq.Workplane("XY").add(top)).union(
        cq.Workplane("XY").add(bottom))
    return plate.clean()
