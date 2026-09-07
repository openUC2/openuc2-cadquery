#!/usr/bin/env python
"""Check the uc2v4 master-insert model against the released STEP files.

    python tools/validate_master_inserts.py \\
        "PRT - 2100 - MASINS - V04.stp" "PRT - 2123 - MASLCK - V04.stp"

Builds both variants and compares each with its STEP: bounding box, volume
(the model omits the R0.5 rim fillets, so a few mm³ are expected) and the
locking rib — the ledge levels in the ±X ears at mid-height, where PRT-2123
carries a crest 0.8586 mm above the 16.9 mm shoulder and PRT-2100 does not.
Exit code 1 on any mismatch, so it can gate a release of the model.
"""

from __future__ import annotations

import argparse
import sys

import cadquery as cq

from uc2v4.master_insert import MasterInsertParams, build_master_insert

SHOULDER = 16.9
RIB_CREST = SHOULDER + 0.8586


def ledge_levels(solid) -> set[float]:
    """|y| of every vertex on the ear ledges near mid-height (the rib lives there)."""
    return {round(abs(v.Y), 3) for v in solid.Vertices()
            if 18.0 < abs(v.X) < 24.3 and abs(v.Z) < 1.2}


def describe(solid) -> dict:
    bb = solid.BoundingBox()
    return {
        "bbox": (round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)),
        "volume": round(solid.Volume(), 1),
        "rib": any(abs(level - RIB_CREST) < 0.01 for level in ledge_levels(solid)),
    }


def compare(label: str, step_path: str, rib: bool) -> list[str]:
    step = cq.importers.importStep(step_path).solids().vals()
    released = describe(step[0] if len(step) == 1 else cq.Compound.makeCompound(step))
    model = describe(build_master_insert(MasterInsertParams(corner_rib=rib)).val())
    print(f"{label}: released {released}")
    print(f"{' ' * len(label)}  model    {model}")
    problems = []
    if any(abs(a - b) > 0.05 for a, b in zip(released["bbox"], model["bbox"])):
        problems.append(f"{label}: bounding boxes differ")
    if abs(released["volume"] - model["volume"]) > 0.01 * released["volume"]:
        problems.append(f"{label}: volumes differ by more than 1%")
    if released["rib"] != rib:
        problems.append(f"{label}: the STEP {'has' if released['rib'] else 'lacks'} "
                        f"the locking rib, the model {'has' if rib else 'lacks'} it")
    if model["rib"] != rib:
        problems.append(f"{label}: the model does not carry the rib it was asked for")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("masins", help="PRT - 2100 - MASINS (smooth, sliding)")
    ap.add_argument("maslck", help="PRT - 2123 - MASLCK (locking rib)")
    args = ap.parse_args(argv)
    problems = compare("MASINS 2100 (rib off)", args.masins, rib=False)
    problems += compare("MASLCK 2123 (rib on) ", args.maslck, rib=True)
    for p in problems:
        print("MISMATCH:", p, file=sys.stderr)
    print("OK — both variants match the released parts" if not problems else
          f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
