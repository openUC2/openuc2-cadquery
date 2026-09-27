"""A tiny standalone wizard to generate inserts and plates and download the files.

`uc2cad wizard` (or ``python -m uc2v4.wizard``) starts a local web server and
opens the browser. Pick **Lens holder**, **Beamsplitter cube** or **OPM
plates** (click the module's cells on a grid), fill in a handful of numbers,
and the page hands you a ZIP of the STEP/STL files plus the plan JSON --
generated on the fly by the same CadQuery code the library and CLI use.

It is deliberately dependency-free (Python's ``http.server`` only), so it runs
anywhere the generators run. Generation happens in a worker thread; the page
polls until the ZIP is ready.
"""

from __future__ import annotations

import io
import json
import threading
import traceback
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Jobs: token -> {"status": "running|done|error", "zip": bytes, "plan": dict,
#                 "error": str, "stem": str}
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# generation (runs in a worker thread)
# ---------------------------------------------------------------------------

def _zip_dir(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _export_bytes(part, kind: str) -> bytes:
    import tempfile
    from pathlib import Path

    import cadquery as cq

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"part.{kind}"
        if kind == "stl":
            cq.exporters.export(part, str(path), tolerance=0.02)
        else:
            cq.exporters.export(part, str(path))
        return path.read_bytes()


def _run_lens(form: dict) -> tuple[dict[str, bytes], dict, str]:
    from .lens_cartridge import CartridgeParams, Lens, Pose, build_cartridge, plan_cartridge

    def f(name, default=0.0):
        v = form.get(name, [""])[0].strip()
        return float(v) if v else default

    inf = float("inf")

    def r(name):
        v = form.get(name, [""])[0].strip().lower()
        return inf if v in ("", "inf", "flat", "plano") else float(v)

    lens = Lens(diameter_mm=f("diameter"), center_thickness_mm=f("thickness"),
                r1_mm=r("r1"), r2_mm=r("r2"),
                reference=form.get("reference", ["center"])[0])
    pose = Pose(x_mm=f("x"), y_mm=f("y"), z_mm=f("z"),
                rx_deg=f("rx"), ry_deg=f("ry"), rz_deg=f("rz"))
    params = CartridgeParams(
        snap_to_notch=form.get("snap", ["on"])[0] != "off",
        alignment_pins=0 if form.get("pins", ["on"])[0] == "off" else 2)
    plan = plan_cartridge(lens, pose, params=params)
    front, back = build_cartridge(plan)
    stem = "lens_cartridge"
    files = {
        f"{stem}_front.step": _export_bytes(front, "step"),
        f"{stem}_front.stl": _export_bytes(front, "stl"),
        f"{stem}_back.step": _export_bytes(back, "step"),
        f"{stem}_back.stl": _export_bytes(back, "stl"),
        f"{stem}_plan.json": json.dumps(plan.report(), indent=2).encode(),
    }
    return files, plan.report(), stem


def _run_beamsplitter(form: dict) -> tuple[dict[str, bytes], dict, str]:
    from .beamsplitter_insert import (
        BeamsplitterParams,
        Plate,
        build_beamsplitter_insert,
        plan_beamsplitter,
    )

    def optic(prefix):
        def g(k):
            v = form.get(f"{prefix}_{k}", [""])[0].strip()
            return float(v) if v else None
        thick, diam, w, h = g("thick"), g("diam"), g("w"), g("h")
        if not thick or (diam is None and w is None):
            return None
        if diam is not None:
            return Plate(thickness_mm=thick, diameter_mm=diam)
        return Plate(thickness_mm=thick, outline_mm=(w, h if h is not None else w))

    def f(name, default):
        v = form.get(name, [""])[0].strip()
        return float(v) if v else default

    params = BeamsplitterParams(
        excitation=optic("exc"), emission=optic("emi"), dichroic=optic("dic"),
        fold_deg=f("fold", 45.0), beam_diameter_mm=f("beam", 20.0),
        thickness_mm=(f("thickness", 0.0) or None),
        pin_style=form.get("pins", ["dowel"])[0])
    plan = plan_beamsplitter(params)
    lower, upper = build_beamsplitter_insert(plan=plan)
    stem = "beamsplitter_insert"
    files = {
        f"{stem}_lower.step": _export_bytes(lower, "step"),
        f"{stem}_lower.stl": _export_bytes(lower, "stl"),
        f"{stem}_upper.step": _export_bytes(upper, "step"),
        f"{stem}_upper.stl": _export_bytes(upper, "stl"),
        f"{stem}_plan.json": json.dumps(plan.report(), indent=2).encode(),
    }
    return files, plan.report(), stem


def _run_plates(form: dict) -> tuple[dict[str, bytes], dict, str]:
    import re
    import tempfile
    from dataclasses import replace
    from pathlib import Path

    from .opm_plates import OpmPlateSpec, PlateGeometry, generate, layout_and_ports_from_ascii

    def f(name, default):
        v = form.get(name, [""])[0].strip()
        return float(v) if v else default

    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", form.get("name", [""])[0].strip()) or "opm_plates"
    layout, ports = layout_and_ports_from_ascii(form.get("ascii", [""])[0], name=name)
    geo = replace(PlateGeometry(), pitch_mm=(f("pitch_x", 50.0), f("pitch_y", 50.1)),
                  m3_hole_d_mm=f("m3", 2.46))
    spec = OpmPlateSpec(layout=layout, layers=int(f("layers", 2)), ports=ports,
                        tie_rods=form.get("rods", ["auto"])[0],
                        pockets=form.get("pockets", ["on"])[0] != "off",
                        geometry=geo, name=name)
    with tempfile.TemporaryDirectory() as d:
        plan = generate(spec, out_dir=d, stem=name)
        files = {p.name: p.read_bytes() for p in plan.files.values()}
    rep = plan.report()
    summary = {k: rep[k] for k in ("plate_size_mm", "layers", "top_offset_z_mm", "mass_g",
                                   "hardware", "warnings") if k in rep}
    summary["layout"] = rep["layout"]["ascii"]
    summary["tie_rods"] = [f"{t['cell']} {t['corner']}" for t in rep["tie_rods"]]
    summary["ports"] = [p["cell"] for p in rep["ports"]]
    return files, summary, name


_RUNNERS = {"lens": _run_lens, "beamsplitter": _run_beamsplitter, "plates": _run_plates}


def _worker(token: str, kind: str, form: dict) -> None:
    try:
        files, plan, stem = _RUNNERS.get(kind, _run_lens)(form)
        preview = next((data for name, data in files.items() if name.endswith(".png")), None)
        with _LOCK:
            _JOBS[token] = {"status": "done", "zip": _zip_dir(files),
                            "plan": plan, "stem": stem}
            if preview:
                import base64
                _JOBS[token]["preview"] = ("data:image/png;base64,"
                                           + base64.b64encode(preview).decode())
    except Exception as exc:                # a bad parameter set, usually
        with _LOCK:
            _JOBS[token] = {"status": "error", "error": str(exc),
                            "trace": traceback.format_exc()}


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>openUC2 insert wizard</title>
<style>
 body{font:15px/1.5 system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#12303d}
 h1{font-size:22px} h2{font-size:17px;margin-top:0}
 .tabs{display:flex;gap:8px;margin:16px 0}
 .tabs button{flex:1;padding:10px;border:1px solid #cbd5db;background:#eef3f6;border-radius:8px;cursor:pointer;font:inherit}
 .tabs button.on{background:#1f6b8c;color:#fff;border-color:#1f6b8c}
 fieldset{border:1px solid #cbd5db;border-radius:8px;margin:12px 0;padding:12px}
 legend{padding:0 6px;color:#1f6b8c;font-weight:600}
 label{display:inline-block;min-width:150px}
 input,select{font:inherit;padding:5px 7px;border:1px solid #cbd5db;border-radius:6px;width:110px}
 .row{margin:6px 0}
 .hint{color:#5b6b73;font-size:13px}
 button.go{background:#1f6b8c;color:#fff;border:0;border-radius:8px;padding:11px 20px;font:inherit;cursor:pointer;margin-top:8px}
 #out{margin-top:16px;padding:12px;border-radius:8px;background:#eef3f6;white-space:pre-wrap;display:none}
 .panel{display:none} .panel.on{display:block}
 #grid{display:grid;grid-template-columns:repeat(12,26px);gap:2px;margin:8px 0;user-select:none}
 #grid div{width:26px;height:26px;box-sizing:border-box;border:1px solid #cbd5db;border-radius:4px;background:#fff;cursor:pointer;font:600 12px/24px system-ui;text-align:center;color:#fff}
 #grid div.c{background:#1f6b8c;border-color:#1f6b8c}
 #grid div.e{background:#d99a3d;border-color:#d99a3d}
 textarea{font:13px/1.25 ui-monospace,monospace;width:220px;border:1px solid #cbd5db;border-radius:6px;padding:6px}
 #preview{max-width:100%;margin-top:12px;display:none;border-radius:8px;border:1px solid #cbd5db}
</style></head><body>
<h1>openUC2 insert &amp; plate wizard</h1>
<p class="hint">Enter the numbers, generate, and download the files.
Positions for the lens are measured from the centre of the cube.</p>
<div class="tabs">
 <button id="tab-lens" class="on" onclick="show('lens')">Lens holder</button>
 <button id="tab-bs" onclick="show('bs')">Beamsplitter cube</button>
 <button id="tab-pl" onclick="show('pl')">OPM plates</button>
</div>

<div id="panel-lens" class="panel on">
 <fieldset><legend>Lens</legend>
  <div class="row"><label>Diameter (mm)</label><input name="diameter" value="25.4"></div>
  <div class="row"><label>Centre thickness (mm)</label><input name="thickness" value="3.5"></div>
  <div class="row"><label>R1 (mm)</label><input name="r1" value="51.5">
      <span class="hint">+ = convex to source; blank/inf = flat</span></div>
  <div class="row"><label>R2 (mm)</label><input name="r2" value="-51.5"></div>
  <div class="row"><label>Reference</label>
   <select name="reference"><option>center</option><option>front_vertex</option><option>back_vertex</option></select></div>
 </fieldset>
 <fieldset><legend>Position from cube centre</legend>
  <div class="row"><label>x, y, z (mm)</label>
   <input name="x" value="0"><input name="y" value="0"><input name="z" value="0"></div>
  <div class="row"><label>tilt rx, ry, rz (deg)</label>
   <input name="rx" value="0"><input name="ry" value="0"><input name="rz" value="0"></div>
  <div class="row"><label>Snap to notch</label>
   <select name="snap"><option value="on">yes (locking master)</option><option value="off">no (sliding master)</option></select></div>
  <div class="row"><label>Alignment pins</label>
   <select name="pins"><option value="on">yes</option><option value="off">no</option></select></div>
 </fieldset>
</div>

<div id="panel-bs" class="panel">
 <p class="hint">Each optic is included only if you give its thickness. Leave an optic blank to make its port a plain bore (dichroic blank = none).</p>
 <fieldset><legend>Excitation filter (+X)</legend>
  <div class="row"><label>Diameter (mm)</label><input name="exc_diam" value="25.4">
   <span class="hint">round; or use width/height below</span></div>
  <div class="row"><label>Width x height (mm)</label><input name="exc_w"><input name="exc_h"></div>
  <div class="row"><label>Thickness (mm)</label><input name="exc_thick" value="4"></div>
 </fieldset>
 <fieldset><legend>Emission filter (+Y)</legend>
  <div class="row"><label>Diameter (mm)</label><input name="emi_diam" value="25.4"></div>
  <div class="row"><label>Width x height (mm)</label><input name="emi_w"><input name="emi_h"></div>
  <div class="row"><label>Thickness (mm)</label><input name="emi_thick" value="4"></div>
 </fieldset>
 <fieldset><legend>Dichroic (45&deg;)</legend>
  <div class="row"><label>Diameter (mm)</label><input name="dic_diam">
   <span class="hint">round; or width/height for a square/rectangle</span></div>
  <div class="row"><label>Width x height (mm)</label><input name="dic_w" value="25"><input name="dic_h" value="25"></div>
  <div class="row"><label>Thickness (mm)</label><input name="dic_thick" value="1"></div>
 </fieldset>
 <fieldset><legend>Cube</legend>
  <div class="row"><label>Beam bore (mm)</label><input name="beam" value="20"></div>
  <div class="row"><label>Fold (deg)</label><input name="fold" value="45"></div>
  <div class="row"><label>Stack height (mm)</label><input name="thickness">
   <span class="hint">blank = auto</span></div>
  <div class="row"><label>Alignment pins</label>
   <select name="pins"><option value="dowel">dowel (bought pin)</option><option value="printed">printed boss/socket</option></select></div>
 </fieldset>
</div>

<div id="panel-pl" class="panel">
 <p class="hint">Top and base plate of an optical module, seen from above. Click cells:
 <b>#</b> core cube cells (tie rods go through their outside corners), <b>+</b> extra puzzle
 units hanging off any side (no rods), <b>P</b> an M37x0.5 retaining-ring port in the top plate.</p>
 <fieldset><legend>Layout</legend>
  <div class="row"><label>Start from</label>
   <select id="preset" onchange="preset(this.value)" style="width:280px">
    <option value="flim">3x8 + 1x1 (FLIM 488, PRT-1051/1052)</option>
    <option value="3x3">3x3</option>
    <option value="bf">3x3 + 1x2 (PRT-1047/1048)</option>
    <option value="clear">empty grid</option></select></div>
  <div class="row"><label>Click paints</label>
   <select id="paint" style="width:280px">
    <option value="#">core cube cell (#)</option>
    <option value="+">extra puzzle unit (+)</option>
    <option value="P">toggle M37 port (P)</option>
    <option value=".">erase</option></select></div>
  <div id="grid"></div>
  <textarea name="ascii" id="ascii" rows="6" readonly></textarea>
 </fieldset>
 <fieldset><legend>Stack</legend>
  <div class="row"><label>Name</label><input name="name" value="opm_plates" style="width:220px"></div>
  <div class="row"><label>Cube layers</label><input name="layers" value="2"></div>
  <div class="row"><label>Tie rods</label>
   <select name="rods" style="width:220px"><option value="auto">outside corners of the # cells</option>
    <option value="outline">every outside corner</option><option value="none">none</option></select></div>
  <div class="row"><label>38 mm cell pockets</label>
   <select name="pockets"><option value="on">yes</option><option value="off">no</option></select></div>
  <div class="row"><label>Pitch x, y (mm)</label><input name="pitch_x" value="50"><input name="pitch_y" value="50.1"></div>
  <div class="row"><label>M3 holes (mm)</label><input name="m3" value="2.46">
   <span class="hint">2.46 = tapped M3 (aluminium); 3.2 = clearance</span></div>
 </fieldset>
</div>

<button class="go" onclick="gen()">Generate &amp; download</button>
<div id="out"></div>
<img id="preview" alt="layout preview">

<script>
let kind='lens';
const TABS={lens:'lens',bs:'beamsplitter',pl:'plates'};
function show(k){kind=k;
 for(const t in TABS){document.getElementById('tab-'+t).className=k==t?'on':'';
  document.getElementById('panel-'+t).className='panel'+(k==t?' on':'');}}
function collect(){const p=document.getElementById('panel-'+kind);
 const d=new URLSearchParams(); p.querySelectorAll('input,select,textarea').forEach(e=>{if(e.name)d.append(e.name,e.value);});
 d.append('kind', TABS[kind]); return d;}
// --- plate layout grid: G[row][col], row 0 at the bottom (plan view) ---
const GC=12, GR=12; let G=[];
function blank(){G=[];for(let r=0;r<GR;r++)G.push(Array(GC).fill('.'));}
function put(c,r,ch){if(r>=0&&r<GR&&c>=0&&c<GC)G[r][c]=ch;}
function preset(v){blank();
 if(v=='3x3'){for(let c=1;c<4;c++)for(let r=1;r<4;r++)put(c,r,'#');}
 if(v=='flim'){for(let c=2;c<5;c++)for(let r=1;r<9;r++)put(c,r,'#');put(1,1,'+');put(3,8,'P');}
 if(v=='bf'){for(let c=1;c<4;c++)for(let r=3;r<6;r++)put(c,r,'#');put(2,1,'#');put(2,2,'#');}
 draw();}
function paint(c,r){const m=document.getElementById('paint').value, ch=G[r][c];
 G[r][c]= m=='P' ? {'#':'P','P':'#','+':'p','p':'+','.':'P'}[ch] : m; draw();}
function art(){let rows=[];for(let r=GR-1;r>=0;r--)rows.push(G[r].join(''));
 const used=rows.map(s=>/[^.]/.test(s)); const a=used.indexOf(true), b=used.lastIndexOf(true);
 if(a<0)return ''; rows=rows.slice(a,b+1); let c0=GC,c1=-1;
 rows.forEach(s=>{for(let i=0;i<s.length;i++)if(s[i]!='.'){c0=Math.min(c0,i);c1=Math.max(c1,i);}});
 return rows.map(s=>s.slice(c0,c1+1)).join('\\n');}
function draw(){const g=document.getElementById('grid'); g.innerHTML='';
 for(let r=GR-1;r>=0;r--)for(let c=0;c<GC;c++){const ch=G[r][c], d=document.createElement('div');
  d.className='#P'.includes(ch)?'c':'+p'.includes(ch)?'e':''; d.textContent='Pp'.includes(ch)?'P':'';
  d.onclick=()=>paint(c,r); g.appendChild(d);}
 document.getElementById('ascii').value=art();}
preset('flim');
async function gen(){const out=document.getElementById('out');out.style.display='block';
 document.getElementById('preview').style.display='none';
 out.textContent='Generating... (a few seconds)';
 let r=await fetch('/generate',{method:'POST',body:collect()});
 let j=await r.json(); if(j.error){out.textContent='Error: '+j.error;return;}
 let tok=j.token, status;
 for(let i=0;i<600;i++){await new Promise(s=>setTimeout(s,500));
  let s=await(await fetch('/status?token='+tok)).json(); status=s;
  if(s.status!='running')break; out.textContent='Generating... '+(i/2|0)+'s';}
 if(status.status=='error'){out.textContent='Could not generate this part:\\n'+status.error;return;}
 out.textContent='Done. Downloading ZIP...\\n\\n'+JSON.stringify(status.plan,null,1);
 if(status.preview){const im=document.getElementById('preview');im.src=status.preview;im.style.display='block';}
 let a=document.createElement('a'); a.href='/download?token='+tok;
 a.download=status.stem+'.zip'; document.body.appendChild(a); a.click(); a.remove();}
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):            # keep the console quiet
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if u.path == "/status":
            token = parse_qs(u.query).get("token", [""])[0]
            with _LOCK:
                job = _JOBS.get(token)
            if not job:
                return self._send(404, b'{"status":"unknown"}')
            out = {"status": job["status"]}
            out.update({k: job[k] for k in ("plan", "stem", "error", "preview") if k in job})
            return self._send(200, json.dumps(out).encode())
        if u.path == "/download":
            token = parse_qs(u.query).get("token", [""])[0]
            with _LOCK:
                job = _JOBS.get(token)
            if not job or job.get("status") != "done":
                return self._send(404, b'{"error":"not ready"}')
            return self._send(200, job["zip"], "application/zip",
                              {"Content-Disposition":
                               f'attachment; filename="{job["stem"]}.zip"'})
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if urlparse(self.path).path != "/generate":
            return self._send(404, b'{"error":"not found"}')
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode())
        kind = form.get("kind", ["lens"])[0]
        token = f"job{len(_JOBS)}_{threading.get_ident()}"
        with _LOCK:
            _JOBS[token] = {"status": "running"}
        threading.Thread(target=_worker, args=(token, kind, form), daemon=True).start()
        return self._send(200, json.dumps({"token": token}).encode())


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Browser wizard for openUC2 inserts.")
    ap.add_argument("--port", type=int, default=8137)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"openUC2 insert wizard running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
