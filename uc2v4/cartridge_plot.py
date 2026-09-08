"""Schematic matplotlib view of a lens cartridge inside its openUC2 cube.

Deliberately a diagram, not a render: it shows *where things are* — the notch
grid, which notch was chosen, how the two molded master inserts sandwich the
two printed halves, and how far the lens sits from the notch — so the plan
can be sanity-checked at a glance before anything is printed.

    from cartridge_plot import plot_plan
    plot_plan(plan, "generated/cartridge_layout.png")

Only matplotlib is needed; no CadQuery geometry is evaluated.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle        # noqa: E402

CUBE = "#1f6b8c"
CAVITY = "#ffffff"
MASTER_NOTCHED = "#8e44ad"      # purple, as in the Inventor assembly
MASTER_PLAIN = "#d35400"        # orange
PRINTED = "#b0bec5"
STAMP = "#e8a87c"
GLASS = "#a8d5e5"
INK = "#12303d"


def _lens_outline(lens, n: int = 60):
    """(offset-from-axis, axial) points tracing the lens cross-section."""
    h = lens.half_width
    zv1, zv2 = lens.vertices()
    pts_top, pts_bot = [], []
    for i in range(n + 1):
        y = -h + 2.0 * h * i / n
        pts_top.append((zv1 + lens.front.sag(abs(y)), y))
        pts_bot.append((zv2 + lens.back.sag(abs(y)), y))
    return pts_top + pts_bot[::-1]


def _rot(points, deg, cz, cy):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cz + (z - cz) * ca - (y - cy) * sa,
             cy + (z - cz) * sa + (y - cy) * ca) for z, y in points]


def plot_plan(plan, out_path: str | Path, show_axis_labels: bool = True):
    """Render the side and front views of *plan* to *out_path*."""
    cube = plan.cube
    p = plan.params
    lens = plan.lens
    dx, dy, dz = plan.residual_mm
    t = p.master_thickness_mm
    half = cube.grid_mm / 2.0
    clear = 24.7                      # inner cavity half width (insert envelope)

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.5, 6.4), facecolor="white")

    # ---------------- side view: optical axis horizontal ----------------
    ax.add_patch(Rectangle((-half, -half), cube.grid_mm, cube.grid_mm,
                           facecolor=CUBE, edgecolor=INK, lw=1.5))
    ax.add_patch(Rectangle((-clear, -clear), 2 * clear, 2 * clear,
                           facecolor=CAVITY, edgecolor="#7fbf3f", lw=1.2))

    # notch grid on both inner walls
    for zn in cube.notch_positions():
        for sign in (+1, -1):
            w = 0.94                                   # measured 1.88 mm wide
            ax.add_patch(Polygon([(zn - w, sign * clear), (zn + w, sign * clear),
                                  (zn, sign * (clear - 2.1))],
                                 facecolor=CAVITY, edgecolor=INK, lw=0.8))
    if plan.notch_index >= 0:
        ax.axvline(plan.notch_z_mm, color="#c0392b", lw=1.1, ls="--", zorder=1)
        ax.annotate(f"notch {plan.notch_index} @ {plan.notch_z_mm:+.0f} mm",
                    (plan.notch_z_mm, half + 0.8), color="#c0392b",
                    ha="center", va="bottom", fontsize=9)

    j = plan.joint_z_mm
    seat = p.seat()
    r_wide, r_narrow = seat.max_radius, seat.top_face_radius

    # Molded master inserts. Cut through the axis, their material is the ring
    # from the Ø40 cone out to the insert envelope; the cone narrows *outward*.
    notched_back = plan.notched_half != "front"
    for sign_z, colour in ((-1, MASTER_NOTCHED if notched_back else MASTER_PLAIN),
                           (+1, MASTER_PLAIN if notched_back else MASTER_NOTCHED)):
        z_in, z_out = j, j + sign_z * t
        for s in (+1, -1):
            ax.add_patch(Polygon([(z_in, s * r_wide), (z_out, s * r_narrow),
                                  (z_out, s * clear), (z_in, s * clear)],
                                 facecolor=colour, edgecolor=INK, lw=0.9))

    # Printed halves: wide cone ring on the joint, narrowing outward.
    # The resolved extensions live on the plan; the params may still say None.
    for sign, ext in ((+1, plan.extension_front_mm), (-1, plan.extension_back_mm)):
        z_knee = j + sign * t
        z_out = j + sign * (t + ext)
        for s in (+1, -1):
            pts = [(j, 0.0), (j, s * r_wide), (z_knee, s * r_narrow)]
            if ext > 1e-9:
                pts += [(z_out, s * r_narrow)]
            pts += [(z_out, 0.0)]
            ax.add_patch(Polygon(pts, facecolor=PRINTED, edgecolor=INK, lw=0.9,
                                 alpha=0.95, zorder=2))
    ax.plot([j, j], [-r_wide, r_wide], color=INK, lw=1.4, zorder=3)

    # Insertion channel + stamp, when the lens is trapped in one half.
    if plan.seat_half is not None:
        h = lens.semi_diameter + p.fit_clearance_mm
        rim_lo, rim_hi = plan.rim_z_mm
        z_a, z_b = ((j, j + rim_lo) if plan.seat_half == "front"
                    else (j + rim_hi, j))
        for s in (+1, -1):
            ax.add_patch(Rectangle((min(z_a, z_b), 0.0), abs(z_b - z_a), s * h,
                                   facecolor="white", edgecolor="#c0392b",
                                   lw=1.0, ls="--", zorder=3))
        r_st = h - p.stamp_wall_clearance_mm
        r_ap = plan.clear_aperture_mm / 2.0
        for s in (+1, -1):
            ax.add_patch(Rectangle((min(z_a, z_b), s * r_ap), abs(z_b - z_a),
                                   s * (r_st - r_ap), facecolor=STAMP,
                                   edgecolor=INK, lw=0.9, hatch="///", zorder=4))

    outline = _lens_outline(lens)
    outline = _rot(outline, plan.pose.ry_deg, 0.0, 0.0)
    outline = [(z + plan.pose.z_mm, y + plan.pose.y_mm) for z, y in outline]
    ax.add_patch(Polygon(outline, facecolor=GLASS, edgecolor="#2c7ea1", lw=1.3,
                         zorder=5))

    ax.plot([-half, half], [plan.pose.y_mm] * 2, color="#c0392b", lw=0.8,
            ls=":", zorder=5)
    ax.set_xlim(-half - 4, half + 10)
    ax.set_ylim(-half - 10, half + 4)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("side view — optical axis (z) horizontal", fontsize=11)
    if show_axis_labels:
        ax.annotate("", xy=(half + 8, -half - 6), xytext=(half - 2, -half - 6),
                    arrowprops=dict(arrowstyle="->", color=INK))
        ax.annotate("z", (half + 9, -half - 6), fontsize=10, va="center")

    handles = [
        Rectangle((0, 0), 1, 1, facecolor=MASTER_NOTCHED, edgecolor=INK,
                  label="master insert, notched (molded)"),
        Rectangle((0, 0), 1, 1, facecolor=MASTER_PLAIN, edgecolor=INK,
                  label="master insert, smooth (molded)"),
        Rectangle((0, 0), 1, 1, facecolor=PRINTED, edgecolor=INK,
                  label="printed halves — wide cone ring on the joint"),
        Rectangle((0, 0), 1, 1, facecolor=GLASS, edgecolor="#2c7ea1", label="lens"),
    ]
    if plan.seat_half is not None:
        other = "back" if plan.seat_half == "front" else "front"
        handles += [
            Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#c0392b", ls="--",
                      label=f"{plan.seat_half} half bored open to Ø lens"),
            Rectangle((0, 0), 1, 1, facecolor=STAMP, edgecolor=INK, hatch="///",
                      label=f"stamp from the {other} half"),
        ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02),
              frameon=False, fontsize=8.5, ncol=2)

    # ---------------- front view: looking down the optical axis ----------------
    ax2.add_patch(Rectangle((-half, -half), cube.grid_mm, cube.grid_mm,
                            facecolor=CUBE, edgecolor=INK, lw=1.5))
    ax2.add_patch(Rectangle((-clear, -clear), 2 * clear, 2 * clear,
                            facecolor=CAVITY, edgecolor="#7fbf3f", lw=1.2))
    ax2.add_patch(Circle((0, 0), r_wide, facecolor=PRINTED, edgecolor=INK, lw=1.0))
    for k in range(seat.nose_count):
        a = math.radians(seat.nose_phase_deg + k * 360.0 / seat.nose_count)
        ax2.add_patch(Circle((r_wide * math.cos(a), r_wide * math.sin(a)), 0.8,
                             facecolor="#90a4ae", edgecolor=INK, lw=0.6))
    ax2.add_patch(Circle((dx, dy), lens.semi_diameter, facecolor=GLASS,
                         edgecolor="#2c7ea1", lw=1.3))
    ax2.add_patch(Circle((dx, dy), plan.clear_aperture_mm / 2.0, facecolor="white",
                         edgecolor="#2c7ea1", lw=1.0, ls="--"))
    ax2.plot([0, dx], [0, dy], color="#c0392b", lw=1.6, zorder=6)
    ax2.plot([0], [0], "+", color=INK, ms=11, zorder=6)
    ax2.annotate(f"offset ({dx:+.2f}, {dy:+.2f}) mm", (0, -half - 1.5),
                 ha="center", va="top", fontsize=9, color="#c0392b")
    ax2.annotate("8 noses, 45° indexing", (0, half + 1.5), ha="center",
                 va="bottom", fontsize=8.5, color=INK)
    ax2.set_xlim(-half - 4, half + 4)
    ax2.set_ylim(-half - 4, half + 4)
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title("front view — transverse offset and clear aperture", fontsize=11)

    notch_txt = ("free slide (smooth master)" if plan.notch_index < 0
                 else f"notch {plan.notch_index} at z={plan.notch_z_mm:+.1f} mm, "
                      f"tongue on the {plan.notched_half} half")
    fig.suptitle(
        f"Ø{lens.diameter_mm:g} mm lens, CT {lens.center_thickness_mm:g} mm  →  "
        f"target ({plan.pose.x_mm:+.2f}, {plan.pose.y_mm:+.2f}, {plan.pose.z_mm:+.2f}) mm "
        f"from cube centre\n{notch_txt};  joint plane z={plan.joint_z_mm:+.1f} mm;  "
        f"printed parts absorb ({dx:+.2f}, {dy:+.2f}, {dz:+.2f}) mm",
        fontsize=11)

    if plan.warnings:
        fig.text(0.5, 0.015, "  •  ".join(plan.warnings), ha="center",
                 fontsize=8.5, color="#c0392b", wrap=True)

    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
