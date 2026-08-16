# openUC2 V4 module inserts — design description & measured interface spec

*Prepared for docs.openuc2.com (extends https://docs.openuc2.com/dev/hw/module-inserts/v4/).
Every number below was extracted from the Inventor master models through the
COM API and cross-checked against exact STEP sections of the released,
injection-molded parts. Sources: `MAS - 2003 - Master Insert - B.ipt`,
`MAS - 2013 - Square Inserts - V04.ipt`, released parts PRT-2123 (MASLCK)
and PRT-2027 (INSLEND43F-50).*

## 1. System concept

The openUC2 toolbox is built on a **50 mm cube grid** (`Grid = 50 mm`).
Hollow injection-molded cubes snap onto baseplates; **square inserts** slide
into the cubes and carry the optics. Because cubes, baseplates and the
generic inserts are injection molded, the mechanical interface is highly
reproducible — every custom holder only has to match the insert interface,
not the cube itself. Custom holders are then either 3D-printed inner parts
clamped by molded inserts, or (with the parametric CAD below) complete
insert-shaped parts.

## 2. The square-insert interface (common to all V4 inserts)

Top view: a square envelope with stepped corners and four flexure springs.

| feature | value | Inventor parameter |
| --- | --- | --- |
| envelope (square) | 49.4 × 49.4 mm | `Grid − 0.6` |
| shoulder width (slides in the cube tracks) | 33.9 mm (lens inserts) / 33.8 mm (master insert) | `CubeClearWidth − 0.1 / − 0.2` |
| 45° corner flats, across corners | 53.54 mm / 53.34 mm | `CubeClearDiagonalV04 − 0.2 / − 0.4` |
| corner-edge fillet | r 0.4 / r 0.5 | — |
| outer chamfer on all top/bottom outline edges | 0.4 × 45° | `OuterChamfer` |
| plate thickness | 4.0 mm (master insert), 17 mm (lens insert), variant-specific | `HightMasterInsert`, `d167`, … |

**Corner steps.** Each corner is cut back to the 45° flat (clears the cube's
corner posts) with a ledge back to the shoulder plane. On the master insert
the two ledges on the ±X sides additionally carry a **raised rib** (crest
0.8586 mm proud of the ledge, flat over z ±0.14, 45° flanks ending at
z ±1.0, plan end rounded r 0.5): it rides in the center groove of the cube
track and gives the 4 mm plate its lateral seating.

**Flexure springs.** Two per side on two opposite sides (±Y), molded into
the plate by a slot cut. Each spring is a ~7°-tapered finger whose tip
carries a rounded hook nose (r 0.5). In the **sliding** variants the nose
tip stays ≈ 0.1 mm below the 49.4 envelope: the springs only preload the
insert against the cube track so it can be repositioned continuously along
the optical axis (focusing). The **locking** variants add a tongue bump
(a suppressed feature pair in the master model) that engages one of the
**7 notches** molded into each cube side, giving discrete, repeatable
positions perpendicular to the optical axis.

## 3. The master insert (MAS-2003 → PRT-2100 MASINS / PRT-2123 MASLCK)

A 4 mm plate on the interface above, with a conic center opening:

- **Cone**: Ø40.0 at the bottom face → Ø38.876 at the top face
  (`InsertDiam = 40`, wall at **82°** to the face), both rims chamfered
  0.2 mm equal-leg.
- **8 nose grooves** ("teeth") every **45°** (phase 22.5°): each groove is
  the full revolution of a Ø1.6 cylinder about an axis parallel to the cone
  wall, inset 0.3 mm perpendicular from it, ending in an **R 1.3 spherical
  pocket** at the top face (the visible dimples). Groove rims are blended
  r 0.5.
- **Base holder** (the round carrier all round inserts derive from): the
  complementary conic disk, offset **+0.05 mm** (`OffsetDiameterBaseHolder`)
  for snap interference, with 8 matching noses — see §5. Result: any round
  insert clicks into the master insert in **45° indexed orientations**, or is
  held purely by friction between the teeth.
- **Self-mating screw pattern**: at (±21.4, ±13.6) each half carries one
  diagonal pair of Ø1.9 thread-forming pilot holes (3.5 deep from the top,
  45° relief cone breaking through the bottom) and one diagonal pair of
  Ø2.8 clearance holes with Ø5.0 × 2.0 head counterbores. Two *identical*
  halves screwed face-to-face therefore clamp an optic between them —
  one mold, no left/right parts (screws: TP 2.5 × 6 Torx).

## 4. The square lens insert (MAS-2013 → PRT-2027 INSLEND family)

A 17 mm tall block on the same interface whose interior is the lens cavity
(all Ø parametric in `LensDiam`, INSLEND43F-50 shown):

| z (mid-plane = 0) | feature |
| --- | --- |
| +8.5 … +8.1 | top face, 0.4 chamfer into the bore |
| +8.1 … +2.9 | internal clamping thread: root Ø`LensDiam+2.2` (45.2), crest Ø`LensDiam+0.8` (43.8), **pitch 1.7 mm** (`ThreadPitch`), 2 turns, 45° trapezoidal flanks |
| +2.9 … +2.0 | 45° lead-in cone |
| +2.0 … −6.3 | lens pocket Ø`LensDiam+0.4` (43.4) |
| −6.3 | lens seat shoulder |
| −6.7 … −8.1 | clear aperture Ø`LensDiam−4` (39.0), chamfered both ends |

The **knurled pre-screw ring** (Ø49.6 = `LensDiam+6.6`, height
`3·ThreadPitch+0.8`, 12-flute knurl) screws into the thread and clamps the
lens onto the seat — lens exchange without tools, preload without glue.
The naming encodes the optic: `INSLEND43F-50` = insert, lens end,
Ø43 mm, f = 50 mm.

## 5. The round base holder (MAS-2003 body *Base holder*)

Everything round that goes into a cube — mirror holders, laser holders, the
MASINS\* family — is the **base holder** disk plus its own pocketing. It is
the negative counterpart of the master insert's cone and grooves:

| feature | value |
| --- | --- |
| widest radius (at the band's bottom plane) | 20.0505 mm = Ø40/2 + 0.05/cos 8° |
| wall | **82°** to the face (8° from the axis), same cone as the master insert |
| interface band height | 4.0 mm — exactly the master insert's thickness |
| blend to the top face | r 0.35 (top face radius 19.1841 mm) |
| noses | 8 at 22.5° + k·45°, Ø1.6 |

`OffsetDiameterBaseHolder = 0.05 mm` is a **face** offset, not a radial one,
so on the 82° wall it becomes 0.050491 mm radially — that is the snap
interference against the master insert's cone.

**The nose is the groove.** The nose and the master insert's groove are
generated from the *same* line: an axis parallel to the cone wall, inset
0.3 mm perpendicular to it, swept with the same Ø1.6 circle. The master
insert subtracts it (ending in an R1.3 spherical pocket), the base holder
adds it (ending in a cap that is a 1.0 mm circle revolved about the axis
0.1 mm off-center, blended to the shank with r 0.2). The nose axis bottom is
placed exactly so its tilted flat end is tangent to the band's bottom plane,
which is what lets the tooth bottom out cleanly. Both parts therefore mate
along a nominal line contact and index every 45°.

## 6. The 45° mirror holder (MAS-2007 → PRT-2111 MASINSMIRHOLUPP)

The base holder plus a 0.4 mm skirt below the band (so the disk stands
proud of the master insert), and:

- an **obround beam aperture**, lobes Ø10 at (6, ±2), i.e. 10 × 14 mm
  clear, sitting 6 mm off the optical axis — a 45° fold mirror's footprint
  is an ellipse, so the opening is elongated and offset on the reflected
  side. Chamfered 0.4 × 45° at both faces.
- **two sandwich screws** at (−7.2, ±13.6): Ø2.9 clearance with Ø5.0 × 2.0
  counterbores. Upper and lower holder halves screw together and clamp the
  mirror (Ø24 × 3 mm on a Ø22 adhesive pad, per `MirrorDiam` /
  `AdhesivePadDiam` in the master).

Note the master model's fixed-mirror branch is **rolled back** (its live
bodies are the kinematic-mount variant), so the released part's b-rep — not
the master's current feature state — is the authority for these numbers.

## 7. Parametric CAD layer (this repo + optikit-core)

- `uc2v4/` (CadQuery). Square-insert family: `build_master_insert()` and
  `build_lens_insert()` reproduce PRT-2123 / PRT-2027; round family:
  `build_base_holder()` (the reusable blank) and `build_mirror_holder()`
  reproduce the PRT-2111 lineage. Verified against the released STEPs by
  `build_uc2v4.py` and `build_mirror_holder.py`. Everything is a dataclass
  parameter: grid, shoulder, thickness, springs on/off, notch/nose count and
  phase, hole pattern, `lens_diam`, thread, aperture shape…
- `optikit-core` T3 generators, so optikit can emit correct-interface
  holders directly into cube slots:
  `openuc2.tpl.square_insert_v4` (lens block) and
  `openuc2.tpl.round_holder_v4` (round base holder + parametric aperture).

Measured agreement with the Inventor originals (mesh deviation, both
directions, excluding the engraved labels):

| part | volume Δ | p99 | max |
| --- | --- | --- | --- |
| PRT-2123 MASLCK | +0.14 % | 0.05–0.10 mm | 0.35 mm |
| PRT-2027 INSLEND43F-50 | +0.51 % | 0.18 mm | 0.74 mm |
| PRT-2111 MASINSMIRHOLUPP | +0.82 % | 0.045 mm | 0.05 mm |

(the volume deltas are essentially the omitted engraving: for PRT-2111,
+39.1 mm³ against 36.0 mm³ of engraved recess.)

### Deliberate omissions of the CAD reconstruction

- engraved label text (0.2 mm deep top-face labels on the master insert,
  0.7 mm deep labels on the lens insert and the mirror holder),
- r 0.5 blend fillets around the notch grooves and the 0.2 chamfer wrap at
  their rims; the r 0.1 nose-root fillet on the base holder (this is the
  entire 0.05 mm residual on PRT-2111),
- thread run-out feathering at the two coil ends,
- sub-0.1 mm blend nuances where the corner rib meets the side face.

None of these affect the cube-facing interface or the optic seating.
