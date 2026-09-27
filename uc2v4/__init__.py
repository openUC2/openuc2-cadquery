"""Parametric CadQuery models of the openUC2 V4 injection-molded inserts.

Every dimension in this package was extracted from the Inventor master models
through the COM API (see PyInventor/inventor_part_probe.py and the JSON dumps
in ../extracted/):

- MAS - 2003 - Master Insert - B.ipt   -> master_insert.py  (PRT-2123 MASLCK)
- MAS - 2013 - Square Inserts - V04.ipt -> lens_insert.py   (PRT-2027 INSLEND)
- MAS - 1003 - Base plates Al - V04.ipt -> opm_plates.py    (PRT-1051/1052 OPM plates)

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
from .filter_cube import FilterCubeParams, RoundFilter, build_filter_cube, plan_filter_cube
from .beamsplitter_insert import (
    BeamsplitterParams,
    BeamsplitterPlan,
    build_beamsplitter_insert,
    plan_beamsplitter,
)
from .fold_insert import FoldInsertParams, FoldPlan, Plate, build_fold_insert, plan_fold_insert
from .lens_insert import LensInsertParams, build_lens_insert
from .sm1_adapter import (
    SM1_MAJOR_DIAM_MM,
    SM1_PITCH_MM,
    SM1AdapterParams,
    SM1Plan,
    build_sm1_adapter,
    plan_sm1_adapter,
)
from .lens_cartridge import (
    CartridgeParams,
    CartridgePlan,
    CubeInterface,
    Lens,
    Pose,
    Surface,
    build_cartridge,
    generate_lens_holder,
    plan_cartridge,
)
from .master_insert import MasterInsertParams, build_master_insert
from .opm_plates import (
    Aperture,
    CustomHole,
    OpmPlatePlan,
    OpmPlateSpec,
    PlateGeometry,
    PlateLayout,
    Port,
    TieRod,
    build_opm_plates,
    plan_opm_plates,
)

__all__ = [
    "PlateLayout",
    "PlateGeometry",
    "OpmPlateSpec",
    "OpmPlatePlan",
    "Port",
    "Aperture",
    "CustomHole",
    "TieRod",
    "plan_opm_plates",
    "build_opm_plates",
    "GRID_MM",
    "Lens",
    "Surface",
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
    "Plate",
    "FoldInsertParams",
    "FoldPlan",
    "plan_fold_insert",
    "build_fold_insert",
    "BeamsplitterParams",
    "FilterCubeParams",
    "RoundFilter",
    "build_filter_cube",
    "plan_filter_cube",
    "BeamsplitterPlan",
    "plan_beamsplitter",
    "build_beamsplitter_insert",
    "SM1AdapterParams",
    "SM1Plan",
    "plan_sm1_adapter",
    "build_sm1_adapter",
    "SM1_MAJOR_DIAM_MM",
    "SM1_PITCH_MM",
    "MasterInsertParams",
    "build_master_insert",
]
