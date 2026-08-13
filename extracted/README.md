# Extracted ground truth (Inventor -> JSON/STEP)

Everything in this folder was pulled out of the original Autodesk Inventor
CAD through the COM automation interface by
[`PyInventor/inventor_part_probe.py`](../../PyInventor/inventor_part_probe.py):

```bash
python inventor_part_probe.py "PART.ipt" --out-dir extracted --step
```

The probe dumps, per part: iProperties, all parameters (model/user/reference,
converted to mm/deg), the ordered feature tree with per-feature parameters,
extrude/revolve **profile paths** (exact sketch curves), sketches (entities,
dimension constraints with expressions, text boxes), work features, and the
final b-rep inventory (faces with exact plane/cylinder/cone/sphere/torus
data, vertices, mass properties). `--step` additionally saves a STEP copy.

## Files

| file | role |
| --- | --- |
| `PRT_-_2027_-_INSLEND43F-50_-_V04.{json,step}` | released lens insert (derived part) |
| `PRT_-_2123_-_MASLCK_-_V04_-_B.{json,step}` | released master lock (derived part) |
| `MAS_-_2013_-_Square_Inserts_-_V04.json` | master model: square-insert family (5 bodies) |
| `MAS_-_2003_-_Master_Insert_-_B.json` | master model: master insert + base holder |
| `inspect_step_sections.py` | exact section-edge dump of a STEP (verification oracle) |
| `*_sections.json` | y=0 / z=0 / x=0 section edges of the released STEPs |

## What the extraction established

- Both released parts are **derived parts**: the real parametric recipe
  lives in the MAS master models (Inventor master-model workflow).
  `INSLEND43F-50` derives from body *Insert for Lenses* of MAS-2013
  (user parameters `LensDiam`, `ThreadPitch`, `LensThicknessPos/Edge/Neg`);
  `MASLCK` derives from body *Master Insert* of MAS-2003
  (`InsertDiam`, `OffsetDiameterBaseHolder`).
- The common square-insert interface is parametrized in the masters as
  `Grid - 0.6` (envelope 49.4), `CubeClearWidth - 0.1|0.2` (shoulder
  33.9|33.8), `CubeClearDiagonalV04 - 0.2|0.4` (corner flats 53.54|53.34)
  and `OuterChamfer` (0.4).
- The Inventor-written STEP files silently break OpenCascade booleans
  (tolerance abuse) - use mesh-domain comparison, and expect a few open
  triangles in their tessellation (e.g. around the MASLCK pilot-hole
  relief cones).

The parametric CadQuery reconstruction that consumes these numbers is the
[`uc2v4`](../uc2v4/) package; `python build_uc2v4.py` rebuilds and
re-verifies both parts against the STEPs in here.
