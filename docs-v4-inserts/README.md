# Documentation page: Module inserts (V4)

A user-facing page for
<https://docs.openuc2.com/dev/hw/module-inserts/v4/>, written for people
assembling openUC2 hardware rather than for people opening CAD.

## Contents

| file | what it is |
| --- | --- |
| `module-inserts-v4.md` | the page itself, Markdown with Docusaurus front matter |
| `img/*.png` | the figures it references |
| `make_figures.py` | regenerates figures 01–07 |

## Dropping it into the docs site

Copy `module-inserts-v4.md` to the page's location and `img/` alongside it.
The page uses relative image paths (`./img/01-overview.png`), which is what
Docusaurus expects when the images sit next to the Markdown file. If the site
keeps images in `static/img/` instead, adjust the seven paths accordingly.

## Regenerating the figures

```bash
uv run --with matplotlib python make_figures.py
```

Figures 01–07 are schematic matplotlib drawings — deliberately not to scale.
Small features (the teeth, the cone taper, the wall that traps a lens) are
exaggerated where that makes the point readable; the dimensions quoted in the
text are the real measured ones. Figure 08 is a render of an actually
generated pair of inserts, produced from the STLs that
`uc2v4/lens_cartridge.py` writes.

## Where the numbers come from

Everything quoted on the page was measured out of the Inventor originals via
the COM API rather than taken from drawings — see
[`../DOCS-insert-v4-design.md`](../DOCS-insert-v4-design.md) for the engineer-facing
version with the full derivation, and [`../extracted/README.md`](../extracted/README.md)
for the raw dumps.

Two statements on the page are *inferred* rather than directly measured, and
are worth confirming before the page goes public:

- that a sandwich is always **two** master inserts, one toothed and one
  smooth (this follows from the self-mating screw pattern and the assembly,
  but "both toothed" has not been ruled out);
- the exact phase of the tooth grid relative to the sandwich — the page only
  says the teeth are 5 mm apart, which is measured and safe, and deliberately
  avoids the finer claim.
