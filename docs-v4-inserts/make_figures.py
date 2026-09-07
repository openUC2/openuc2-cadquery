"""Figures for the user-facing "Module inserts V4" documentation page.

Plain matplotlib diagrams, deliberately schematic: the audience is people
assembling openUC2 hardware, not people opening CAD. Run:

    uv run --with matplotlib python make_figures.py

Writes into ./img/. Numbers come from the measured geometry (see
../DOCS-insert-v4-design.md), but the drawings exaggerate small features
where that helps readability — they are explanatory, not to scale.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle  # noqa: E402

OUT = Path(__file__).parent / "img"
OUT.mkdir(parents=True, exist_ok=True)

CUBE = "#1f6b8c"
CAVITY = "#ffffff"
LOCKING = "#8e44ad"        # master insert WITH nudges
SLIDING = "#d35400"        # master insert WITHOUT nudges
PRINTED = "#b0bec5"
STAMP = "#e8a87c"
GLASS = "#a8d5e5"
INK = "#12303d"
NOTE = "#c0392b"

GRID = 50.0
HALF = GRID / 2.0
CLEAR = 24.7               # inner cavity half-width
NOTCHES = [-15, -10, -5, 0, 5, 10, 15]


def _label(ax, text, xy, xytext, colour=INK, size=11, ha="left"):
    ax.annotate(text, xy=xy, xytext=xytext, fontsize=size, color=colour, ha=ha,
                va="center",
                arrowprops=dict(arrowstyle="-|>", color=colour, lw=1.2,
                                shrinkA=0, shrinkB=3))


def _cube_section(ax, notch_marks=True):
    """Cube cross-section: outer shell, cavity, and the notch teeth."""
    ax.add_patch(Rectangle((-HALF, -HALF), GRID, GRID, facecolor=CUBE,
                           edgecolor=INK, lw=1.6))
    ax.add_patch(Rectangle((-CLEAR, -CLEAR), 2 * CLEAR, 2 * CLEAR,
                           facecolor=CAVITY, edgecolor=INK, lw=1.0))
    if notch_marks:
        for zn in NOTCHES:
            for s in (+1, -1):
                ax.add_patch(Polygon(
                    [(zn - 1.1, s * CLEAR), (zn + 1.1, s * CLEAR),
                     (zn, s * (CLEAR - 2.4))],
                    facecolor=CAVITY, edgecolor=INK, lw=0.9))


def _tidy(ax, xlim, ylim, title=None):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=13, pad=12)


# ---------------------------------------------------------------------------
# 1 — the three layers
# ---------------------------------------------------------------------------

def fig_overview():
    fig, ax = plt.subplots(figsize=(11, 7.4), facecolor="white")
    _cube_section(ax)

    j, t = 3.0, 4.0                       # joint plane and master thickness
    r_wide, r_narrow = 20.05, 19.18
    for sz, colour in ((-1, LOCKING), (+1, SLIDING)):
        z_in, z_out = j, j + sz * t
        for s in (+1, -1):
            ax.add_patch(Polygon([(z_in, s * r_wide), (z_out, s * r_narrow),
                                  (z_out, s * CLEAR), (z_in, s * CLEAR)],
                                 facecolor=colour, edgecolor=INK, lw=1.0))
    for sz in (+1, -1):
        z_out = j + sz * t
        for s in (+1, -1):
            ax.add_patch(Polygon([(j, 0), (j, s * r_wide), (z_out, s * r_narrow),
                                  (z_out, 0)], facecolor=PRINTED, edgecolor=INK,
                                 lw=1.0))
    lens = []
    for i in range(61):
        y = -12.7 + 25.4 * i / 60
        lens.append((j - 2.5 + (51.5 - math.sqrt(51.5**2 - y * y)), y))
    for i in range(61):
        y = 12.7 - 25.4 * i / 60
        lens.append((j + 2.5 - (51.5 - math.sqrt(51.5**2 - y * y)), y))
    ax.add_patch(Polygon(lens, facecolor=GLASS, edgecolor="#2c7ea1", lw=1.4))

    _label(ax, "the CUBE\n50 mm, injection molded\nteeth inside the walls",
           (-HALF, 8), (-56, 26))
    _label(ax, "MASTER INSERTS\ninjection molded, two of them\nscrewed face to face",
           (j + 2, 22), (14, 40))
    _label(ax, "ROUND INSERTS, 3D printed\nthe only custom part",
           (j + 3, 12), (30, 4))
    _label(ax, "your optic", (j, 0), (-56, -20))

    _tidy(ax, (-64, 76), (-34, 50),
          "Three layers: the cube and the master inserts are always the same,\n"
          "only the small round insert changes with your optic")
    fig.tight_layout()
    fig.savefig(OUT / "01-overview.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2 — the notch ladder
# ---------------------------------------------------------------------------

def fig_notches():
    fig, ax = plt.subplots(figsize=(11, 6.0), facecolor="white")
    _cube_section(ax)
    for zn in NOTCHES:
        ax.plot([zn, zn], [-CLEAR + 2.4, CLEAR - 2.4], color=NOTE, lw=1.0,
                ls=":", zorder=1)
        ax.annotate(f"{zn}", (zn, -CLEAR - 2.0), ha="center", va="top",
                    fontsize=9.5, color=NOTE)
    ax.annotate("", xy=(-15, 30), xytext=(-10, 30),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.4))
    ax.annotate("5 mm", (-12.5, 31.5), ha="center", va="bottom", fontsize=11)
    ax.annotate("7 locking positions, 5 mm apart, measured from the cube centre",
                (0, -CLEAR - 7.5), ha="center", va="top", fontsize=12, color=NOTE)
    ax.annotate("", xy=(28, 0), xytext=(12, 0),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.6))
    ax.annotate("light travels this way", (30, 0), fontsize=11, va="center")
    _tidy(ax, (-34, 62), (-42, 40),
          "Inside the cube: a ladder of teeth along the beam direction")
    fig.tight_layout()
    fig.savefig(OUT / "02-notches.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3 — with and without nudges
# ---------------------------------------------------------------------------

def fig_variants():
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), facecolor="white")

    for ax, nudge in zip(axes, (True, False)):
        colour = LOCKING if nudge else SLIDING
        ax.add_patch(Rectangle((-16, 7), 32, 6, facecolor=CUBE, edgecolor=INK,
                               lw=1.4))
        for zn in (-10, 0, 10):                  # teeth pointing down
            ax.add_patch(Polygon([(zn - 1.6, 7), (zn + 1.6, 7), (zn, 4.2)],
                                 facecolor="white", edgecolor=INK, lw=1.1))
        ax.add_patch(Rectangle((-9, -6), 18, 10, facecolor=colour,
                               edgecolor=INK, lw=1.4))
        if nudge:
            ax.add_patch(Polygon([(-1.9, 4), (1.9, 4), (0, 6.6)],
                                 facecolor=colour, edgecolor=INK, lw=1.4))
            ax.annotate("nudge sits in a tooth", (0, 13.6),
                        ha="center", va="bottom", fontsize=11.5, color=NOTE)
            ax.annotate("fixed, repeatable positions\n— 5 mm steps",
                        (0, -9), ha="center", va="top", fontsize=12)
        else:
            for dz in (-1, 1):
                ax.annotate("", xy=(dz * 14, -1), xytext=(dz * 9.5, -1),
                            arrowprops=dict(arrowstyle="-|>", color=NOTE, lw=1.8))
            ax.annotate("no nudge — slides freely", (0, 13.6),
                        ha="center", va="bottom", fontsize=11.5, color=NOTE)
            ax.annotate("any position along the beam\n— e.g. to refocus",
                        (0, -9), ha="center", va="top", fontsize=12)
        _tidy(ax, (-19, 19), (-16, 13),
              "WITH nudges (locking)" if nudge else "WITHOUT nudges (sliding)")

    fig.suptitle("The master insert comes in two flavours", fontsize=13.5, y=1.0)
    fig.tight_layout()
    fig.savefig(OUT / "03-variants.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 4 — the sandwich, exploded
# ---------------------------------------------------------------------------

def fig_sandwich():
    fig, ax = plt.subplots(figsize=(12.5, 5.4), facecolor="white")
    r_wide, r_narrow, t = 20.05, 19.18, 4.0
    gap = 9.0
    items = [
        (-2 * gap - 2 * t, t, +1, LOCKING, "master insert\n(molded)", -34.0),
        (-gap - t, t, +1, PRINTED, "round insert\n(printed)", -27.0),
        (0.0, 0.0, 0, GLASS, "your optic", -34.0),
        (gap, t, -1, PRINTED, "round insert\n(printed)", -27.0),
        (2 * gap + t, t, -1, SLIDING, "master insert\n(molded)", -34.0),
    ]
    for z0, width, cone, colour, name, y_lab in items:
        if width == 0.0:
            lens = []
            for i in range(41):
                y = -12.7 + 25.4 * i / 40
                lens.append((-2.2 + (51.5 - math.sqrt(51.5**2 - y * y)), y))
            for i in range(41):
                y = 12.7 - 25.4 * i / 40
                lens.append((2.2 - (51.5 - math.sqrt(51.5**2 - y * y)), y))
            ax.add_patch(Polygon(lens, facecolor=colour, edgecolor="#2c7ea1", lw=1.3))
        else:
            z1 = z0 + width
            ri, ro = (r_wide, r_narrow) if cone > 0 else (r_narrow, r_wide)
            inner = 0.0 if colour is PRINTED else 15.5
            for s in (+1, -1):
                ax.add_patch(Polygon([(z0, s * inner), (z0, s * ri),
                                      (z1, s * ro), (z1, s * inner)],
                                     facecolor=colour, edgecolor=INK, lw=1.1))
        z_mid = z0 + width / 2.0
        ax.annotate(name, (z_mid, y_lab), ha="center", va="top", fontsize=11)
        ax.plot([z_mid, z_mid], [-21.5, y_lab + 1.0], color=INK, lw=0.7, ls=":")

    ax.annotate("", xy=(2 * gap + 2 * t + 4, 24), xytext=(-2 * gap - 2 * t - 4, 24),
                arrowprops=dict(arrowstyle="<->", color=NOTE, lw=1.4, ls=":"))
    ax.annotate("two screws pull the whole stack together",
                (0, 25.5), ha="center", va="bottom", fontsize=11.5, color=NOTE)
    _tidy(ax, (-50, 50), (-42, 32),
          "The sandwich: the optic is clamped between two printed inserts,\n"
          "which are held by the two molded master inserts")
    fig.tight_layout()
    fig.savefig(OUT / "04-sandwich.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5 — one disk, any optic
# ---------------------------------------------------------------------------

def fig_universal():
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.2), facecolor="white")
    titles = ["the blank disk", "small lens", "big lens, off-centre", "45° mirror"]
    for ax, title, kind in zip(axes, titles, ("blank", "small", "big", "mirror")):
        ax.add_patch(Circle((0, 0), 20.05, facecolor=PRINTED, edgecolor=INK, lw=1.3))
        for k in range(8):
            a = math.radians(22.5 + k * 45)
            ax.add_patch(Circle((20.05 * math.cos(a), 20.05 * math.sin(a)), 0.85,
                                facecolor="#90a4ae", edgecolor=INK, lw=0.7))
        if kind == "small":
            ax.add_patch(Circle((0, 0), 6.35, facecolor=GLASS,
                                edgecolor="#2c7ea1", lw=1.3))
        elif kind == "big":
            ax.add_patch(Circle((3.5, -2.0), 12.7, facecolor=GLASS,
                                edgecolor="#2c7ea1", lw=1.3))
            ax.plot([0, 3.5], [0, -2.0], color=NOTE, lw=1.6)
            ax.plot([0], [0], "+", color=INK, ms=9)
        elif kind == "mirror":
            ax.add_patch(Rectangle((-5, -7), 10, 14, facecolor=GLASS,
                                   edgecolor="#2c7ea1", lw=1.3))
            ax.add_patch(Circle((0, 7), 5, facecolor=GLASS, edgecolor="#2c7ea1",
                                lw=1.3))
            ax.add_patch(Circle((0, -7), 5, facecolor=GLASS, edgecolor="#2c7ea1",
                                lw=1.3))
        _tidy(ax, (-23, 23), (-23, 23), title)
    fig.suptitle("Always the same outside, anything you like inside — "
                 "the ring of 8 nubs lets it click in every 45°",
                 fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "05-universal.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 6 — coarse plus fine
# ---------------------------------------------------------------------------

def fig_coarse_fine():
    fig, ax = plt.subplots(figsize=(11.5, 6.2), facecolor="white")
    _cube_section(ax)
    target = 6.1
    ax.plot([target, target], [-CLEAR, CLEAR], color=NOTE, lw=2.0)
    ax.annotate("where you want the optic\n(z = +6.1 mm)", (target, CLEAR + 1.5),
                ha="center", va="bottom", fontsize=11.5, color=NOTE)
    ax.plot([5, 5], [-CLEAR, CLEAR], color=INK, lw=1.4, ls="--")
    ax.annotate("nearest tooth\n(+5 mm)", (5, -CLEAR - 2.0), ha="right", va="top",
                fontsize=11)
    ax.annotate("", xy=(target, -18), xytext=(5, -18),
                arrowprops=dict(arrowstyle="<->", color=NOTE, lw=1.6))
    ax.annotate("the leftover 1.1 mm is built\ninto the printed insert",
                (30, -18), fontsize=11.5, color=NOTE, va="center")
    ax.annotate("", xy=(-6, 12), xytext=(-6, 0),
                arrowprops=dict(arrowstyle="<->", color=NOTE, lw=1.6))
    ax.annotate("sideways offsets are\nbuilt in the same way", (-62, 6),
                fontsize=11.5, color=NOTE, va="center", ha="left")
    _tidy(ax, (-64, 74), (-40, 42),
          "Coarse + fine: the cube gives 5 mm steps, the printed insert\n"
          "makes up the difference — so any position is reachable")
    fig.tight_layout()
    fig.savefig(OUT / "06-coarse-fine.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 7 — seat and stamp
# ---------------------------------------------------------------------------

def fig_seat_stamp():
    """Schematic, and knowingly exaggerated: the aperture is drawn much
    smaller than life so the wall that traps the lens is actually visible."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), facecolor="white")
    h, ap, outer = 12.7, 7.0, 20.0        # lens, aperture, insert half-height
    x_lens, x_neck = -10.0, -6.0

    for ax, good in zip(axes, (False, True)):
        for s in (+1, -1):
            # seat half: outer wall, always there
            ax.add_patch(Rectangle((-17, s * h), 17, s * (outer - h),
                                   facecolor=PRINTED, edgecolor=INK, lw=1.2))
            # the neck between the lens and the joint plane
            if good:                       # bored open to the full lens width
                ax.add_patch(Rectangle((-17, s * h), 0.01, 0.01, facecolor="none",
                                       edgecolor="none"))
            else:                          # solid: this is what traps the lens
                ax.add_patch(Rectangle((x_neck, s * ap), -x_neck, s * (h - ap),
                                       facecolor=PRINTED, edgecolor=INK, lw=1.2))
            # back wall the lens seats against
            ax.add_patch(Rectangle((-17, s * ap), 17 + x_lens - 2.2, s * (h - ap),
                                   facecolor=PRINTED, edgecolor=INK, lw=1.2))
            # the other half
            ax.add_patch(Rectangle((0, s * ap), 17, s * (outer - ap),
                                   facecolor=PRINTED, edgecolor=INK, lw=1.2))
            if good:                       # stamp reaching across the joint
                ax.add_patch(Rectangle((x_neck + 1.0, s * ap), -x_neck - 1.0,
                                       s * (h - ap - 0.6), facecolor=STAMP,
                                       edgecolor=INK, lw=1.2, hatch="///"))

        lens = []
        for i in range(41):
            y = -h + 2 * h * i / 40
            lens.append((x_lens - 2.2 + (51.5 - math.sqrt(51.5**2 - y * y)), y))
        for i in range(41):
            y = h - 2 * h * i / 40
            lens.append((x_lens + 2.2 - (51.5 - math.sqrt(51.5**2 - y * y)), y))
        ax.add_patch(Polygon(lens, facecolor=GLASS, edgecolor="#2c7ea1", lw=1.3,
                             zorder=4))

        if good:
            ax.annotate("", xy=(x_lens + 3.5, 0), xytext=(6, 0),
                        arrowprops=dict(arrowstyle="-|>", color=NOTE, lw=2.0))
            ax.annotate("the half holding the lens is bored open to the\n"
                        "full lens width, so the lens simply drops in;\n"
                        "the other half grows a ring that pushes it home",
                        (0, -outer - 3.5), ha="center", va="top", fontsize=11.5)
        else:
            ax.annotate("this wall boxes the lens in — there is\n"
                        "no way to get it into the pocket",
                        (0, -outer - 3.5), ha="center", va="top", fontsize=11.5,
                        color=NOTE)
            ax.annotate("", xy=(x_neck - 0.6, 9.9), xytext=(9, 17),
                        arrowprops=dict(arrowstyle="-|>", color=NOTE, lw=1.4))
        ax.plot([0, 0], [-outer - 1, outer + 1], color=INK, lw=1.0, ls=":")
        ax.annotate("joint", (0, outer + 1.5), ha="center", va="bottom",
                    fontsize=10, color=INK)
        _tidy(ax, (-19, 19), (-34, 27),
              "Won't work" if not good else "Works: open bore + push ring")
    fig.suptitle("When the optic ends up deep inside one half", fontsize=13.5, y=1.0)
    fig.tight_layout()
    fig.savefig(OUT / "07-seat-stamp.svg", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    for fn in (fig_overview, fig_notches, fig_variants, fig_sandwich,
               fig_universal, fig_coarse_fine, fig_seat_stamp):
        fn()
        print("wrote", fn.__name__)
    print("figures in", OUT)
