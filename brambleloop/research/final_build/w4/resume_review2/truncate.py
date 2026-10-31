"""RESUME_REVIEW2 R-B1: chain truncation re-opens retry-until-green (no key needed)."""
import json, os, re, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path.cwd(); WORK = Path(tempfile.mkdtemp(prefix="rr2t-"))
KN = ("SUITES","SUITE_RECORD_DIR","JOBS","RESUME","SHARD","CHECKPOINT","CHECKPOINT_TOOL","TMP_LEAK_STRICT","PYTHONPATH","SUITE_RUNKEY_DIR")
def git(repo, *a): subprocess.run(["git","-C",str(repo),"-c","user.name=t","-c","user.email=t@e.invalid",*a],check=True,capture_output=True)
def sandbox(name):
    repo = WORK/name; (repo/"tests").mkdir(parents=True); (repo/"scripts").mkdir()
    shutil.copy(ROOT/"run_tests.sh", repo/"run_tests.sh")
    for f in ("suite_checkpoint.py","suite_final_segment.txt"): shutil.copy(ROOT/"scripts"/f, repo/"scripts"/f)
    (repo/"tests"/"test_flaky.py").write_text('import os,sys\np=os.environ["COUNT_DIR"]+"/flaky"\nn=len(open(p).read()) if os.path.exists(p) else 0\nopen(p,"a").write("x")\nif n==0:\n    print("FAIL test_flaky first execution"); sys.exit(1)\nprint("OK   test_flaky")\n')
    (repo/"tests"/"test_gate.py").write_text('import os,time\ng=os.environ["GATE_FILE"]\nopen(g+".started","w").close()\ne=time.time()+60\nwhile not os.path.exists(g) and time.time()<e: time.sleep(0.05)\nprint("OK   test_gated")\n')
    (repo/".gitignore").write_text("artifacts/\n__pycache__/\n"); git(repo,"init","-q"); git(repo,"add","-A"); git(repo,"commit","-qm","s")
    (WORK/f"{name}-st").mkdir(); return repo
def env(repo, **o):
    e={k:v for k,v in os.environ.items() if k not in KN}
    return {**e,"PY":sys.executable,"JOBS":"2","SUITE_REGISTRY":"0","COUNT_DIR":str(WORK/f"{repo.name}-st"),
            "GATE_FILE":str(WORK/f"{repo.name}-st"/"gate"),"SUITE_RUNKEY_DIR":str(WORK/f"{repo.name}-keys"),**o}
def rd(repo): return repo/"artifacts"/"suite_runs"
def run(repo, **o): return subprocess.run(["nice","-n","19","bash",str(repo/"run_tests.sh")],cwd=repo,env=env(repo,**o),capture_output=True,text=True,timeout=300)
def flaky_runs(repo): return len((WORK/f"{repo.name}-st"/"flaky").read_text())
def killed(repo):
    g = WORK/f"{repo.name}-st"/"gate"
    p = subprocess.Popen(["bash",str(repo/"run_tests.sh")],cwd=repo,env=env(repo,SUITES="test_flaky,test_gate",CHECKPOINT="1"),
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    t=time.time()+60
    while time.time()<t:
        ds=[d for d in rd(repo).iterdir() if d.is_dir() and d.name!="locks"] if rd(repo).is_dir() else []
        if ds and Path(str(g)+".started").exists():
            m=json.loads((ds[0]/"manifest.json").read_text())
            if any(e["kind"]=="result" and "flaky" in e["suite"] for e in m["chain"]): break
        time.sleep(0.05)
    os.killpg(p.pid, signal.SIGKILL); p.wait(); g.write_text("open"); return ds[0].name
def truncate(repo, rid):
    mp = rd(repo)/rid/"manifest.json"; m=json.loads(mp.read_text())
    before=[(e["kind"],e.get("suite"),e.get("status")) for e in m["chain"]]
    m["chain"]=[e for e in m["chain"][:1]]          # keep only the 'begin' entry: a valid prefix
    mp.write_text(json.dumps(m, sort_keys=True, separators=(",",":")))
    return before
def show(tag, repo, rid, r):
    rec=json.loads((rd(repo)/f"{rid}.json").read_text())
    print(f"{tag}: exit {r.returncode}; record status {rec['status']}, failing_suites {rec['failing_suites']}, "
          f"flaky executions {flaky_runs(repo)}, suite_results {[(s['suite'][6:],s['status'],s['segment']) for s in rec.get('suite_results',[])]}")
    for l in r.stderr.splitlines()[-3:]: print("   stderr:", l[:200])
# control: F2 holds on an untouched checkpoint
repo=sandbox("ctl"); rid=killed(repo); show("CONTROL  killed after flaky FAILED, plain RESUME", repo, rid, run(repo,SUITES="test_flaky,test_gate",RESUME=rid,CHECKPOINT="1"))
# attack 1: interrupted run, truncate the chain (no key, no record/log edit)
repo=sandbox("a1"); rid=killed(repo); b=truncate(repo,rid); print("ATTACK 1 chain before truncation:", b)
show("ATTACK 1 truncated chain to its 'begin' entry, RESUME", repo, rid, run(repo,SUITES="test_flaky,test_gate",RESUME=rid,CHECKPOINT="1"))
# attack 2: a COMPLETED failed run (P07): truncate + 2 unauthenticated edits (record status, log EXIT line)
repo=sandbox("a2"); (WORK/"a2-st"/"gate").write_text("open")
r=run(repo,SUITES="test_flaky,test_gate",CHECKPOINT="1"); rid=sorted(p.stem for p in rd(repo).glob("*.json"))[-1]
show("ATTACK 2 run 1 (uninterrupted, completed)", repo, rid, r)
r=run(repo,SUITES="test_flaky,test_gate",RESUME=rid,CHECKPOINT="1"); print("ATTACK 2 plain RESUME of the completed run: exit", r.returncode, r.stderr.strip().splitlines()[-1][:160])
truncate(repo,rid); rp=rd(repo)/f"{rid}.json"; rec=json.loads(rp.read_text()); rec["status"]="interrupted"; rp.write_text(json.dumps(rec))
lp=rd(repo)/f"{rid}.log"; lp.write_text(re.sub(r"(?m)^EXIT \d+\n","",lp.read_text()))
show("ATTACK 2 truncated chain + record status 'interrupted' + EXIT line removed, RESUME", repo, rid, run(repo,SUITES="test_flaky,test_gate",RESUME=rid,CHECKPOINT="1"))
print("orphaned segment-1 attempt files left in place:", sorted(p.name for p in (rd(repo)/rid).glob("*.s1.json")))
