# openUC2 CadQuery Insert Generator (v4-style)

Programmatic generation of an **openUC2 cube insert** and **component cutouts** using **CadQuery**.

> **New: `uc2v4/` — exact parametric reconstructions of the molded V4 inserts.**
> Built from the Inventor master models (COM extraction, see
> [`extracted/README.md`](extracted/README.md)) and verified against the
> released STEP geometry:
>
> *Square-insert family* (`build_uc2v4.py`):
>
> - `uc2v4.build_master_insert()` → PRT - 2123 - MASLCK - V04 - B
>   (4 mm master-insert plate: springs, corner ribs, 82° cone opening,
>   8×45° nose grooves, self-mating screw pattern)
> - `uc2v4.build_lens_insert()` → PRT - 2027 - INSLEND43F-50 - V04
>   (17 mm lens insert: parametric `lens_diam`, pocket/seat/aperture,
>   2-turn pitch-1.7 clamping thread for the pre-screw ring)
>
> *Round-holder family* (`build_mirror_holder.py`):
>
> - `uc2v4.round_holder.build_base_holder()` → the reusable blank: the conic
>   disk whose 8 noses are the exact positives of the master insert's
>   grooves, so it seats on 45° indexing
> - `uc2v4.round_holder.build_mirror_holder()` → PRT - 2111 - MASINSMIRHOLUPP - C
>   (obround beam aperture + sandwich screw counterbores)
>
> ```bash
> uv run --with cadquery --with trimesh --with rtree --with scipy python build_uc2v4.py
> ```
> writes STEP/STL into `generated/` and prints the mesh-deviation report
> against `extracted/*.step`. Design write-up: [`DOCS-insert-v4-design.md`](DOCS-insert-v4-design.md).
> Both families are available to optikit-core as standalone T3 generators
> (`openuc2.tpl.square_insert_v4`, `openuc2.tpl.round_holder_v4`).

> **Automatic lens cartridges — `uc2v4/lens_cartridge.py`.**
> Give it a lens and a target pose measured from the cube centre; it snaps to
> the cube's notch grid (7 notches, 5.0 mm pitch, measured from
> `PRT - 1003 - CUBHLF111`), hands the residual offset and tilt to the printed
> parts, and writes the **front and back** round inserts that clamp the lens
> and drop into the molded master inserts:
>
> ```bash
> uv run --with cadquery python uc2v4/lens_cartridge.py --diameter 25.4 --thickness 3.5 --r1 51.5 --r2 -51.5 -x 3.0 -y -2.0 -z 6.1 --extension-front 1.5 --extension-back 1.5
> ```
>
> Each run also writes a `*_layout.png` schematic of the cube, the notch grid,
> the molded/printed sandwich and the lens, and engraves an identifying label
> on each outward face.
>
> `check_lens_cartridge.py` verifies a generated pair (one solid per half, no
> overlap, zero lens-to-holder collision, snug pocket, pose reproduced,
> envelope respected, **and the cone rings facing the joint** — the halves are
> not symmetric and a mirrored build passes every other check).

> **Beamsplitter / fluorescence-filter cubes — `uc2v4/beamsplitter_insert.py`.**
> A printable two-part **clamshell** (modelled on PRT-2074 / PRT-2075) that
> carries an **excitation filter**, an **emission filter** and a **45° dichroic**
> through one cube. Each optic is independently a round disc or a rectangular
> plate, with its own thickness; the excitation reflects off the dichroic to
> the sample port, the emission passes straight through:
>
> ```bash
> uv run --with cadquery python uc2v4/beamsplitter_insert.py            # the reference set
> uc2cad beamsplitter --exc-diam 25.4 --exc-thick 4 \
>                     --emi-diam 25.4 --emi-thick 4 \
>                     --dic-w 25 --dic-thick 1 --beam 18                 # or via the CLI
> ```
>
> It writes the **lower and upper** halves (STEP + STL) plus the plan JSON.
> `check_inserts.py` verifies each build (one solid per half, no overlap, every
> optic drops into its seat and lifts out of the split plane, all beam legs
> bored, pins registered). Design write-up:
> [`DOCS-beamsplitter-insert.md`](DOCS-beamsplitter-insert.md).

> **Optical-module plates — `uc2v4/opm_plates.py`.** The two 5 mm aluminium
> plates that sandwich an OPM, for **any layout**: a core rectangle such as
> `3x8` or `3x3` plus extra puzzle units on any side (`3x8+1x1@-1,0`), or a
> layout drawn as ASCII art. Built from the master `MAS - 1003 - Base plates
> Al - V04` and the released pairs (PRT-1051/1052 FLIM 488, 1053/1054, 1026/1027,
> 1047/1048): 50.0 × 50.1 mm cells with four M3 holes and a Ø38 pocket each,
> R1.5/R10.2 corners, the outward-face chamfer, tie rods at the core's corners
> (every ≤ 3 cells along long edges — the released rule), counterbores on the
> top, sleeve-nut U-slot recesses underneath, optional M37×0.5 ports:
>
> ```bash
> uv run --with cadquery --with matplotlib python build_opm_plates.py   # edit the layouts in there
> uc2cad plates --layout 3x8+1x1@-1,0 --port 1,7                       # or via the CLI
> ```
>
> Each module writes the top and base plate (STEP + STL), the assembled stack,
> a plan JSON (cells, tie rods, ports, hardware such as `8 x ISO 4762 M3x115`)
> and a layout diagram. `check_opm_plates.py` reproduces the tie rods of all five
> released plate families and matches PRT-1052 feature for feature (all 149
> cylindrical features, same 203 faces, volume −0.012 %). Design write-up:
> [`DOCS-opm-plates.md`](DOCS-opm-plates.md).

> **dvOPM camera, launch and sample parts — `uc2v4/opm_camera_adapter.py`,
> `uc2v4/opm_launch_holder.py`, `uc2v4/opm_sample_holder.py`.** The printed parts of the
> direct-view OPM on a 5x4 plate. Its detection stays in openUC2 cubes: the fold mirror and the
> reversed telecentric lens use the CAD-new modules ASS-2020 and ASS-3011 turned inside their
> cubes, and the only new detection part is the **camera adapter** — a double base-holder disc
> captured between a MASLCK and a MASINS like any printed round insert, with a bracket, a spine
> and a 4 mm plate that holds the Alvium bare board at the sensor tilt (50 deg) in the cube; the
> sensor looks through a window, four M2 hold the board from behind. The **launch holder**
> carries the RMS-threaded 4x objective, the LJ1878L1 cylinder lens (side slot + sliding key)
> and the f = 8 fibre collimator (side-slid fork clip); the arc-rail bracket's two concentric
> slots pivot it about the sheet's entry point, and the bracket hangs from the launch stage's
> slide when the slide stands above the holder. The **sample arm** is one flat slab on the
> sample stage's slide with the dish ring. Every dimension comes from the layout model in
> `openuc2-opmsimulator/opm_layout.py` (`opm_layout.json`):
>
> ```bash
> uc2cad opm-camera ../openuc2-opmsimulator/opm_layout.json      # camera adapter -> generated/opm_detection
> uc2cad opm-launch ../openuc2-opmsimulator/opm_layout.json      # holder, key, clip, bracket -> generated/opm_launch
> uc2cad opm-sample ../openuc2-opmsimulator/opm_layout.json      # sample arm + dish -> generated/opm_launch
> uv run --with cadquery python check_opm_launch_holder.py ../openuc2-opmsimulator/opm_layout.json
> ```
>
> The camera cube as built (adapter, inserts, board) is checked in openuc2-opmsimulator
> (`check_opm_detection_cubes.py`); `check_opm_launch_holder.py` verifies the thread, the seats
> and retainers, the clamp screws and that every medium's screw position lies in the bracket's
> slots. The plan JSON's `params` block also drives
> `openuc2-opmsimulator/build_opm_holder_ipt.py`, which rebuilds the launch holder as a **native
> parametric Inventor part** (35 user parameters, coil-cut RMS thread);
> `check_opm_holder_native.py <its .stp> generated/opm_launch` samples that part against the
> CadQuery reference. The beam-path solids (`generated/opm_launch/opm_beam_*.step`) come from
> `openuc2-opmsimulator/opm_beam_solids.py`. `uc2v4/opm_detection_holder.py` and
> `check_opm_detection_holder.py` are the superseded one-piece detection holder (2026-10-02).
> Pipeline write-up: `openuc2-opmsimulator/OPM_CAD_README.md`.

> **Holders for turning an optical design into cubes (2026-10-03).** The geometry behind
> optikit-core's generators (`generators/*_v4.py` there), each with a `plan_*` that checks
> without building and a `check_*.py` here that verifies the parts against what they hold:
>
> | module | holds | check |
> |---|---|---|
> | `round_clamp.py` | a cylinder body up to Ø34 mm (laser module, fibre collimator, tube) between two master inserts, one set screw | `check_round_clamp.py` |
> | `kinematic_adapter.py` | any round or rectangular optic in the ½-inch kinematic mount ZJB-0.5-3, on a plate or a wedge | `check_kinematic_adapter.py` |
> | `bolt_cradle.py` | a device by the holes in one face: an insert across the beam, or a pedestal on a plate | `check_bolt_cradle.py` |
> | `focus_cartridge.py` | a lens in a barrel that slides ±1 mm in a round clamp, set-screw lock | `check_focus_cartridge.py` |
> | `off_grid_plate.py` | a plate in the puzzle layer over a list of cells: kinematic pedestal, saddle, cradle, lens wall; docking poses | `check_off_grid_plate.py` |
> | `cube_pocket.py` | a beamsplitter cube at the centre of a cell, in the fluorescence clamshell | `check_cube_pocket.py` |
> | `slide_slot.py` | a microscope slide across the beam, stop, coverslip pocket | `check_slide_slot.py` |
> | `sample_vessel.py` | a vial or a cuvette upright across the beam, windows, light-tight cap | `check_sample_vessel.py` |
> | `cell_cover.py` | a light-tight cover over a list of cells with an interlock switch housing | `check_cell_cover.py` |
>
> `lens_cartridge.snap_joint` places every master-insert pair, and its joint plane stays within
> ±13 mm of the cube centre (`CubeInterface.joint_limit_mm`; further out the outer insert sits
> on the cube's end frames). optikit-core pins v0.6.0 and needs a new tag for these.

> **Browser wizard — `uc2cad wizard`.** No command line needed: run it and a
> page opens where you enter the numbers for a **lens holder** or a
> **beamsplitter cube**, or click an **OPM plate layout** together on a grid,
> and download a ZIP of the files. It uses only the Python standard library
> (plus CadQuery), so it runs anywhere the generators do:
>
> ```bash
> uv run --with cadquery python -m uc2v4.wizard        # opens http://127.0.0.1:8137/
> ```

> The scripts below predate the extraction and approximate the outline from
> drawings — still useful as simple starting points, but `uc2v4/` is the
> measured reference.

![](./IMAGES/insert.png)

*Python-generated generic insert that can e.g. host a lens or something*

Goal:
- Create a reusable **insert “blank”** (outer geometry + optional tabs/wings + threaded holes).
- Create separate **component STEP cutters** (lens pockets, motor clearances, etc.).
- **Import any STEP cutter**, apply an **affine transform**, and **subtract** it from the insert to produce a printable/custom holder.

Coordinate system:
- **Optical axis = Z-axis**
- Optical axis passes through **(0, 0)** in the XY-plane
- All shapes are built around the origin by default


## Files

### 1) `uc2_component_cut_step.py`
Creates a **negative volume** (“cutter”) as a STEP file.

Typical use:
- Generate a lens pocket as a cylinder + optional seat + optional set-screw holes.
- Export as `component_cut.step` (and optionally `component_cut.stl`).

You can create multiple cutters, e.g.:
- `lens_25mm_cut.step`
- `motor_clearance_cut.step`
- `laser_mount_cut.step`

These STEP cutters are then consumed by the insert builder.

### 2) `uc2_insert_builder.py`
Creates the **insert body** and subtracts one or more imported STEP cutters.

What it generates:
- Outer insert outline (octagon-like profile from the technical drawing)
- Optional side tabs (or “wings” depending on the version you use)
- Optional center bore (or you do center bore via cutter STEP)
- Optional threaded/tapping holes
- Subtraction of imported cutters after applying affine transforms
- Exports `uc2_insert.step` and `uc2_insert.stl`


## Install

Create an environment and install CadQuery:

```bash
pip install cadquery
```

If your Python environment is already set up (e.g. `mambaforge`), install into that environment.

## Quick start

### Step 1: Create a cutter STEP (example lens pocket)

```bash
python uc2_component_cut_step.py
```

This writes:

* `component_cut.step`
* `component_cut.stl` (optional)

### Step 2: Build the insert and subtract the cutter

Edit `uc2_insert_builder.py` and add the cutter to `CUTTERS`, then run:

```bash
python uc2_insert_builder.py
```

This writes:

* `uc2_insert.step`
* `uc2_insert.stl`

## How cutters work

A cutter is any **solid STEP** you want to subtract from the insert.

Typical workflow:

1. Generate a cutter STEP in a dedicated script (preferred, reproducible)
2. Add it to `CUTTERS` list in `uc2_insert_builder.py`
3. Assign an affine transform for positioning/orientation
4. Boolean subtract (`insert.cut(cutter)`)

This supports:

* Lens holders (coaxial to optical axis)
* Motor pockets (offset + rotated)
* LED/laser holders
* Cable channels / clearance volumes
* Any imported CAD STEP solid

## Affine transforms

Each cutter can be positioned and rotated with:

* Translation: `tx, ty, tz` (mm)
* Rotation: `rx, ry, rz` (degrees, applied about origin, in order X → Y → Z)

Example: shift 2 mm in X, rotate 15° around optical axis:

```python
CUTTERS = [
    ("component_cut.step", Affine(tx=2.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=15.0)),
]
```

Tip:

* If you want a lens centered on the optical axis, keep `(tx, ty) = (0, 0)`.

## Parameters you typically adjust

In `uc2_insert_builder.py`:

* `OUTER_HALF`, `SHOULDER_HALF` : insert outline
* `INSERT_THICKNESS`            : extrusion thickness
* `ADD_SIDE_TABS`, tab dimensions
* `ADD_THREAD_HOLES` and hole geometry
* `CUTTERS` list and each cutter transform

In `uc2_component_cut_step.py`:

* Lens diameter + clearance
* Seat diameter + depth
* Set screw count, diameter, radius

## License / contributions

This approach is meant to support openUC2’s open insert ecosystem:

* Generate inserts reproducibly
* Share scripts + parameters
* Allow others to remix and extend

If you create a useful cutter for a common component (lens size, motor, LED), publish it with:

* source script
* generated STEP
* a short usage snippet (recommended transform and parameters)

