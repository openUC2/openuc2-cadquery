"""Define optical-module (OPM) plate layouts here and export both plates of each.

    uv run --with cadquery --with matplotlib python build_opm_plates.py             # all
    uv run --with cadquery --with matplotlib python build_opm_plates.py flim_488    # one

Every module writes into ``generated/opm_plates/<name>/``:

- ``<name>_top.step/.stl`` and ``<name>_base.step/.stl`` -- the two plates,
  both in the common plate frame (cell (0,0) at the origin, z -35..-30);
- ``<name>_stack.step`` -- base and top plate placed as in the assembly;
- ``<name>_plan.json`` -- cells, tie rods, ports, hardware list, mass;
- ``<name>_layout.png`` -- plan view of both plates.

A layout is a core rectangle plus extra puzzle units on any side:

- ``"3x8"`` -- 3 columns (x, 50.0 mm pitch) by 8 rows (y, 50.1 mm pitch);
- ``"3x8+1x1@-1,0"`` -- plus one extra unit whose cell is (-1, 0), i.e. left
  of the core's first cell; ``+WxH@c,r`` adds a W x H block with its lower-left
  cell at (c, r), ``-WxH@c,r`` removes one;
- or ASCII art (top line = far end, as seen from above): ``#`` core cell,
  ``+`` extra unit, ``P`` a core cell with an M37 port in the top plate.

Tie rods (M3, through the cube corners) go to the outside corners of the core
cells -- plus intermediates so no more than 3 cells separate two rods -- the
rule of the released plates. See DOCS-opm-plates.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

from uc2v4.opm_plates import (
    Aperture,
    OpmPlateSpec,
    PlateLayout,
    Port,
    generate,
    layout_and_ports_from_ascii,
)

OUT = Path(__file__).parent / "generated" / "opm_plates"

# A free-form module drawn as text: 3x3 core with an M37 port in the far
# middle cell, one extra unit either side of the middle row, one below.
CUSTOM = """
.#P#.
+###+
.###.
..+..
"""
custom_layout, custom_ports = layout_and_ports_from_ascii(CUSTOM, name="custom")

MODULES: dict[str, OpmPlateSpec] = {
    # The released FLIM 488 pair, PRT-1051 base / PRT-1052 top: 3x8 core, one
    # extra unit left of the first cell, M37x0.5 retaining-ring port far end.
    "flim_488": OpmPlateSpec(
        layout=PlateLayout.parse("3x8+1x1@-1,0"),
        ports=(Port(cell=(1, 7)),)),

    # PRT-1047/1048: 3x3 core with a 1x2 leg under the middle column; the leg
    # carries rods too ("outline"), the top plate a plain 35 mm port.
    "brightfield_3x3+1x2": OpmPlateSpec(
        layout=PlateLayout.parse("3x3@0,3+1x2@1,1"),
        tie_rods="outline",
        apertures=(Aperture(cell=(1, 5), d_mm=35.0, chamfer_mm=1.0),)),

    # A plain 3x3, one cube layer high.
    "plain_3x3_1layer": OpmPlateSpec(layout=PlateLayout.parse("3x3"), layers=1),

    "custom": OpmPlateSpec(layout=custom_layout, ports=custom_ports),
}


def main(names: list[str]) -> None:
    unknown = [n for n in names if n not in MODULES]
    if unknown:
        sys.exit(f"unknown module(s) {unknown}; known: {sorted(MODULES)}")
    for name in names or MODULES:
        spec = MODULES[name]
        plan = generate(spec, out_dir=OUT / name, stem=name)
        rep = plan.report()
        print(f"== {name}")
        print("   " + "\n   ".join(spec.layout.to_ascii().splitlines()))
        print(f"   plates {rep['plate_size_mm'][0]:g} x {rep['plate_size_mm'][1]:g} mm, "
              f"top {rep['mass_g']['top']:g} g / base {rep['mass_g']['base']:g} g, "
              f"{len(rep['tie_rods'])} rods ({rep['hardware']['tie_rod_screw']}), "
              f"{len(rep['ports'])} port(s)")
        print(f"   -> {OUT / name}")


if __name__ == "__main__":
    main(sys.argv[1:])
