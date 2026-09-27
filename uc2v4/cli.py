"""`uc2cad` — the package's command line.

One executable, one subcommand per part family. Each subcommand's flags are
owned by its module (``lens_cartridge._cli`` today), so `uc2cad
lens-cartridge --help` is the same interface the module always had as a
script.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: uc2cad <command> [options]\n\n"
            "commands:\n"
            "  lens-cartridge   printable front/back pair holding a lens at an\n"
            "                   arbitrary pose inside a V4 cube (--help for flags)\n"
            "  beamsplitter     printable clamshell holding an excitation filter,\n"
            "                   emission filter and 45 deg dichroic (--help for flags)\n"
            "  plates           top + base plate of an optical module (OPM) for any\n"
            "                   layout, e.g. --layout 3x8+1x1@-1,0 (--help for flags)\n"
            "  wizard           open the browser wizard to enter parameters and\n"
            "                   download parts (lens, beamsplitter or OPM plates)\n"
            "  master-insert    the molded PRT-2123 master insert, as STEP\n"
            "  lens-insert      the molded PRT-2027 square lens insert, as STEP\n"
        )
        return 0

    command, rest = argv[0], argv[1:]
    if command == "lens-cartridge":
        from .lens_cartridge import _cli

        _cli(rest)
        return 0
    if command == "beamsplitter":
        from .beamsplitter_insert import _cli

        _cli(rest)
        return 0
    if command == "plates":
        from .opm_plates import _cli

        _cli(rest)
        return 0
    if command == "wizard":
        from .wizard import main as wizard_main

        return wizard_main(rest)
    if command in ("master-insert", "lens-insert"):
        import cadquery as cq

        out = "uc2v4_master_insert.step" if command == "master-insert" \
            else "uc2v4_lens_insert.step"
        for arg in rest:
            if arg.startswith("--out="):
                out = arg.split("=", 1)[1]
        if command == "master-insert":
            from .master_insert import build_master_insert

            part = build_master_insert()
        else:
            from .lens_insert import build_lens_insert

            part = build_lens_insert()
        cq.exporters.export(part, out)
        print(out)
        return 0

    print(f"uc2cad: unknown command {command!r} (try --help)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
