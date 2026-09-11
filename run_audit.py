#!/usr/bin/env python3
"""Esegue l'audit riproducibile e salva le evidenze in audit/runtime/."""
from __future__ import annotations
import json, os, platform, shutil, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"audit"/"runtime"; OUT.mkdir(parents=True,exist_ok=True)
ENV={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0"}

def run(name,args):
    t=time.perf_counter();p=subprocess.run(args,cwd=ROOT,env=ENV,text=True,capture_output=True)
    rec={"name":name,"args":args,"returncode":p.returncode,"seconds":time.perf_counter()-t,
         "stdout":p.stdout,"stderr":p.stderr}
    (OUT/f"{name}.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False))
    print(f"[{name}]", "PASS" if p.returncode==0 else "FAIL")
    return rec

for f in (ROOT/"data").glob("audit_*.msgpack"):f.unlink()
results=[]
results.append(run("compile",[sys.executable,"-m","compileall","-q","-f","."]))
results.append(run("tests",[sys.executable,"-m","pytest","-q"]))
base=[sys.executable,"main.py","--agents","50","--ticks","600","--fast","--no-mayor"]
results.append(run("simulation_a",base+["--log","data/audit_a.msgpack"]))
results.append(run("simulation_b",base+["--log","data/audit_b.msgpack"]))
results.append(run("determinism",[sys.executable,"check_determinism.py","data/audit_a.msgpack","data/audit_b.msgpack"]))
results.append(run("inspect",[sys.executable,"inspect_replay.py","data/audit_a.msgpack"]))
summary={"python":sys.version,"platform":platform.platform(),"passed":all(x["returncode"]==0 for x in results),
         "results":[{"name":x["name"],"returncode":x["returncode"],"seconds":x["seconds"]} for x in results]}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(json.dumps(summary,indent=2,ensure_ascii=False))
raise SystemExit(0 if summary["passed"] else 1)
