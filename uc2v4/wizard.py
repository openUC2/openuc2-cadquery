"""A tiny standalone wizard to generate inserts and download the files.

`uc2cad wizard` (or ``python -m uc2v4.wizard``) starts a local web server and
opens the browser. Pick **Lens holder** or **Beamsplitter cube**, fill in a
handful of numbers, and the page hands you a ZIP of the printable STEP/STL
files plus the plan JSON -- generated on the fly by the same CadQuery code the
library and CLI use.

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


def _worker(token: str, kind: str, form: dict) -> None:
    try:
        runner = _run_lens if kind == "lens" else _run_beamsplitter
        files, plan, stem = runner(form)
        with _LOCK:
            _JOBS[token] = {"status": "done", "zip": _zip_dir(files),
                            "plan": plan, "stem": stem}
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
</style></head><body>
<h1>openUC2 insert wizard</h1>
<p class="hint">Enter the numbers, generate, and download the printable files.
Positions for the lens are measured from the centre of the cube.</p>
<div class="tabs">
 <button id="tab-lens" class="on" onclick="show('lens')">Lens holder</button>
 <button id="tab-bs" onclick="show('bs')">Beamsplitter cube</button>
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

<button class="go" onclick="gen()">Generate &amp; download</button>
<div id="out"></div>

<script>
let kind='lens';
function show(k){kind=k;
 document.getElementById('tab-lens').className=k=='lens'?'on':'';
 document.getElementById('tab-bs').className=k=='bs'?'on':'';
 document.getElementById('panel-lens').className='panel'+(k=='lens'?' on':'');
 document.getElementById('panel-bs').className='panel'+(k=='bs'?' on':'');}
function collect(){const p=document.getElementById('panel-'+kind);
 const d=new URLSearchParams(); p.querySelectorAll('input,select').forEach(e=>{if(e.name)d.append(e.name,e.value);});
 d.append('kind', kind=='lens'?'lens':'beamsplitter'); return d;}
async function gen(){const out=document.getElementById('out');out.style.display='block';
 out.textContent='Generating... (a few seconds)';
 let r=await fetch('/generate',{method:'POST',body:collect()});
 let j=await r.json(); if(j.error){out.textContent='Error: '+j.error;return;}
 let tok=j.token, status;
 for(let i=0;i<600;i++){await new Promise(s=>setTimeout(s,500));
  let s=await(await fetch('/status?token='+tok)).json(); status=s;
  if(s.status!='running')break; out.textContent='Generating... '+(i/2|0)+'s';}
 if(status.status=='error'){out.textContent='Could not generate this part:\\n'+status.error;return;}
 out.textContent='Done. Downloading ZIP...\\n\\n'+JSON.stringify(status.plan,null,1);
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
            out.update({k: job[k] for k in ("plan", "stem", "error") if k in job})
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
