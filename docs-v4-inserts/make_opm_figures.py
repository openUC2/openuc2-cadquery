"""Figures for DOCS-opm-plates.md (the OPM top/base plate generator).

    uv run --with cadquery --with matplotlib python docs-v4-inserts/make_opm_figures.py

Writes into ./img/: a shaded 3D view of the FLIM 488 plate pair in its stack
position, and the plan views of two layouts straight from the generator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
import numpy as np                                                 # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from uc2v4 import opm_plates as op                                 # noqa: E402

OUT = HERE / "img"
OUT.mkdir(parents=True, exist_ok=True)


def _mesh(shape, dz=0.0):
    verts, tris = shape.tessellate(0.05, 0.3)
    v = np.array([p.toTuple() for p in verts])
    v[:, 2] += dz
    return v, np.array(tris)


def _shaded(v, t, rgb, light=(-0.4, -0.6, 1.0)):
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    lv = np.array(light) / np.linalg.norm(light)
    k = 0.45 + 0.55 * np.abs(n @ lv)       # two-sided: the tessellation winding varies
    return tri, np.clip(np.outer(k, rgb), 0, 1)


def fig_stack(spec: op.OpmPlateSpec, path: Path):
    plan = op.plan_opm_plates(spec)
    parts = op.build_opm_plates(plan)
    fig = plt.figure(figsize=(8, 7.2))
    ax = fig.add_subplot(projection="3d")
    for which, dz, rgb in (("base", 0.0, (0.55, 0.58, 0.62)),
                           ("top", plan.top_offset_z_mm, (0.70, 0.73, 0.77))):
        v, t = _mesh(parts[which].val(), dz)
        tri, col = _shaded(v, t, rgb)
        ax.add_collection3d(Poly3DCollection(tri, facecolors=col, edgecolors="none"))
    g = plan.geometry
    z0, z1 = g.z_bottom - 6, plan.top_offset_z_mm + g.z_top + 3   # rods + sleeve nut
    rods = [[(x, y, z0), (x, y, z1)] for _, (x, y), _ in plan.tie_rods]
    ax.add_collection3d(Line3DCollection(rods, colors="#b3261e", linewidths=2.2))
    # ghost cubes of the first layer, for scale
    edges = []
    for (x, y) in plan.centres.values():
        for zz in (-25.0, 25.0):
            c = [(x - 25, y - 25, zz), (x + 25, y - 25, zz), (x + 25, y + 25, zz),
                 (x - 25, y + 25, zz), (x - 25, y - 25, zz)]
            edges += [[c[i], c[i + 1]] for i in range(4)]
        edges += [[(x + sx * 25, y + sy * 25, -25), (x + sx * 25, y + sy * 25, 25)]
                  for sx in (-1, 1) for sy in (-1, 1)]
    ax.add_collection3d(Line3DCollection(edges, colors="#1f6b8c", linewidths=0.4, alpha=0.35))
    x0, y0, x1, y1 = plan.extent()
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_zlim(z0, z1)
    ax.set_box_aspect((x1 - x0, y1 - y0, z1 - z0), zoom=1.0)
    ax.view_init(elev=24, azim=-58)
    ax.set_axis_off()
    ax.set_title(f"{spec.layout.label()}: base plate, top plate (+{plan.top_offset_z_mm:g} mm), "
                 f"{len(plan.tie_rods)} tie rods\n(first cube layer ghosted for scale)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    flim = op.released_3x8_1x1()
    fig_stack(flim, OUT / "opm-plates-stack.png")
    op.plot_plates(op.plan_opm_plates(flim), OUT / "opm-plates-flim488.png")
    custom, ports = op.layout_and_ports_from_ascii(".#P#.\n+###+\n.###.\n..+..",
                                                   name="custom 3x3 + 4 extra units")
    op.plot_plates(op.plan_opm_plates(op.OpmPlateSpec(layout=custom, ports=ports)),
                   OUT / "opm-plates-custom.png")
    print("wrote", *sorted(p.name for p in OUT.glob("opm-plates-*.png")))


if __name__ == "__main__":
    main()
