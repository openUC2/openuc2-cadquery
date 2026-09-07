"""Parametric CadQuery models of the openUC2 V4 injection-molded inserts.

Every dimension in this package was extracted from the Inventor master models
through the COM API (see PyInventor/inventor_part_probe.py and the JSON dumps
in ../extracted/):

- MAS - 2003 - Master Insert - B.ipt   -> master_insert.py  (PRT-2123 MASLCK)
- MAS - 2013 - Square Inserts - V04.ipt -> lens_insert.py   (PRT-2027 INSLEND)

Coordinate convention (same as the Inventor originals and the rest of the
openuc2-cadquery repo): optical axis = Z through (0, 0), insert mid-plane at
z = 0, units mm.
"""

from .interface import (
    GRID_MM,
    MasterInsertInterface,
    SquareInsertInterface,
    SpringTemplate,
)
from .lens_insert import LensInsertParams, build_lens_insert
from .lens_cartridge import (
    CartridgeParams,
    CartridgePlan,
    CubeInterface,
    Lens,
    Pose,
    build_cartridge,
    generate_lens_holder,
    plan_cartridge,
)
from .master_insert import MasterInsertParams, build_master_insert

__all__ = [
    "GRID_MM",
    "Lens",
    "Pose",
    "CubeInterface",
    "CartridgeParams",
    "CartridgePlan",
    "plan_cartridge",
    "build_cartridge",
    "generate_lens_holder",
    "SquareInsertInterface",
    "MasterInsertInterface",
    "SpringTemplate",
    "LensInsertParams",
    "build_lens_insert",
    "MasterInsertParams",
    "build_master_insert",
]
