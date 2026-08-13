"""Slice a STEP solid with axis-aligned planes and dump the exact section
edges (lines / circular arcs with true coordinates) as JSON.

The STEP b-rep is exact, so the numbers read off here are authoritative for
verifying a CadQuery reconstruction against the Inventor original.

Usage:  uv run --with cadquery python inspect_step_sections.py part.step out.json
"""

from __future__ import annotations

import json
import sys

import cadquery as cq
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def section_edges(shape, origin, normal):
    pln = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
    sec = BRepAlgoAPI_Section(shape, pln)
    sec.Build()
    result = sec.Shape()
    edges = []
    exp = TopExp_Explorer(result, TopAbs_EDGE)
    while exp.More():
        edge = TopoDS.Edge_s(exp.Current())
        ad = BRepAdaptor_Curve(edge)
        t0, t1 = ad.FirstParameter(), ad.LastParameter()
        p0, p1 = ad.Value(t0), ad.Value(t1)
        item = {
            "s": [round(p0.X(), 6), round(p0.Y(), 6), round(p0.Z(), 6)],
            "e": [round(p1.X(), 6), round(p1.Y(), 6), round(p1.Z(), 6)],
        }
        if ad.GetType() == GeomAbs_Line:
            item["kind"] = "line"
        elif ad.GetType() == GeomAbs_Circle:
            c = ad.Circle()
            loc = c.Location()
            item["kind"] = "arc"
            item["c"] = [round(loc.X(), 6), round(loc.Y(), 6), round(loc.Z(), 6)]
            item["r"] = round(c.Radius(), 6)
        else:
            item["kind"] = str(ad.GetType())
            # sample a midpoint for context
            pm = ad.Value((t0 + t1) / 2.0)
            item["mid"] = [round(pm.X(), 6), round(pm.Y(), 6), round(pm.Z(), 6)]
        edges.append(item)
        exp.Next()
    return edges


def main():
    step_path, out_path = sys.argv[1], sys.argv[2]
    wp = cq.importers.importStep(step_path)
    solids = wp.solids().vals()
    solid = solids[0]
    for s in solids[1:]:
        solid = solid.fuse(s)
    shape = solid.wrapped

    bb = wp.val().BoundingBox()
    data = {
        "file": step_path,
        "volume_mm3": round(solid.Volume(), 3),
        "area_mm2": round(solid.Area(), 3),
        "bbox": [[round(bb.xmin, 4), round(bb.ymin, 4), round(bb.zmin, 4)],
                 [round(bb.xmax, 4), round(bb.ymax, 4), round(bb.zmax, 4)]],
        "sections": {
            "y0": section_edges(shape, (0, 0, 0), (0, 1, 0)),
            "z0": section_edges(shape, (0, 0, 0), (0, 0, 1)),
            "x0": section_edges(shape, (0, 0, 0), (1, 0, 0)),
        },
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    print("volume", data["volume_mm3"], "bbox", data["bbox"])
    print("wrote", out_path)


if __name__ == "__main__":
    main()
