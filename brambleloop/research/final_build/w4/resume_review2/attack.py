"""RESUME_REVIEW2 independent attack harness. Run from brambleloop/: python3 attack.py"""
import hashlib, json, os, re, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT.parent / "ops"))
import deploy_guard as dg
from brambleloop.ops import release_record as rr
MB = sys.argv[1]
WORK = Path(tempfile.mkdtemp(prefix="rr2-"))
KN = ("SUITES","REQUIRE_CLEAN","THEN_FULL","ALLOW_PARALLEL","SUITE_RECORD_DIR","JOBS","RESUME",
      "SHARD","CHECKPOINT","CHECKPOINT_TOOL","TMP_LEAK_STRICT","PYTHONPATH","SUITE_RUNKEY_DIR")
BASE_ENV = {k: v for k, v in os.environ.items() if k not in KN}
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a); OUT.append(s); print(s, flush=True)
def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
        "user.email=t@example.invalid", *a], capture_output=True, text=True, check=True).stdout.strip()
def sandbox(name, runner_src=None):
    repo = WORK / name; (repo / "tests").mkdir(parents=True); (repo / "scripts").mkdir()
    (repo / "run_tests.sh").write_bytes(runner_src or (ROOT / "run_tests.sh").read_bytes())
    for f in ("suite_checkpoint.py", "suite_final_segment.txt"):
        if (ROOT / "scripts" / f).exists(): shutil.copy(ROOT / "scripts" / f, repo / "scripts" / f)
    (repo / "tests" / "test_gate.py").write_text(
        'import os, time\ng=os.environ.get("GATE_FILE")\n'
        'if g:\n    open(g+".started","w").close()\n    e=time.time()+60\n'
        '    while not os.path.exists(g) and time.time()<e: time.sleep(0.05)\n'
        'print("OK   test_gated")\n')
    for i in range(100):
        (repo / "tests" / f"test_z{i:03d}.py").write_text(f'print("OK   test_z{i}")\n')
    (repo / ".gitignore").write_text("artifacts/\n__pycache__/\n")
    git(repo, "init", "-q"); git(repo, "add", "-A"); git(repo, "commit", "-qm", "s")
    return repo
def env(repo, **o):
    return {**BASE_ENV, "PY": sys.executable, "JOBS": "4", "SUITE_REGISTRY": "0",
            "SUITE_RUNKEY_DIR": str(repo.parent / f"{repo.name}-keys"), **o}
def rd(repo): return repo / "artifacts" / "suite_runs"
def run(repo, **o):
    return subprocess.run(["nice", "-n", "19", "bash", str(repo / "run_tests.sh")], cwd=repo,
                          env=env(repo, **o), capture_output=True, text=True, timeout=600)
def newest(repo, before=()):
    recs = sorted(p for p in rd(repo).glob("*.json") if p.stem not in before)
    return recs[-1].stem
def evaluate(label, repo, rid):
    """Every gate, against the run record + log as they now stand on disk."""
    d = rd(repo); rec = json.loads((d / f"{rid}.json").read_text())
    log = (d / f"{rid}.log").read_text(errors="replace")
    sha = rec.get("git_sha")
    picked = dg.latest_suite(d, sha=sha, eligible_only=True)
    picked = picked if picked and picked.get("run_id") == rec.get("run_id") else None
    lc = dg._log_confirms(rec, repo) if picked else "not picked"
    prov = dg.resume_provenance(rec, d)
    record_ok = picked is not None and lc is None and not prov
    # tracked copies, as record_release would write them, then both tracked-record checks
    rel = repo / "release"; shutil.rmtree(rel, ignore_errors=True); (rel / "suite_runs").mkdir(parents=True)
    rb = (d / f"{rid}.json").read_bytes(); lb = dg.summary_log(dg.portable_log(log.encode(), repo))
    (rel / "suite_runs" / "r.json").write_bytes(rb); (rel / "suite_runs" / "r.log").write_bytes(lb)
    R = {"sha": sha, "release_eligible": True,
         "suite_record": {"path": "suite_runs/r.json", "sha256": hashlib.sha256(rb).hexdigest()},
         "suite_log": {"path": "suite_runs/r.log", "sha256": hashlib.sha256(lb).hexdigest()}}
    boot = rr.check_record(R, rel, checkpoint_root=d)
    boot_container = rr.check_record(R, rel, checkpoint_root=WORK / "absent")
    files = {"r.json": rb, "r.log": lb}
    push = dg._record_problems(R, lambda p: files.get(p.split("/")[-1]), d)
    res = dict(record_release=record_ok, boot_guard=not boot, boot_in_container=not boot_container,
               deploy_check=not push)
    passes = [k for k, v in res.items() if v]
    say(f"  {label:58} {'PASSES ' + ','.join(passes) if passes else 'refused everywhere'}")
    return res
def forge(repo, rid, *, bit=False, keys=False, reason=False, dir_=False, rename=None, log=False):
    d = rd(repo); rec = json.loads((d / f"{rid}.json").read_text()); lg = (d / f"{rid}.log").read_text()
    if bit:
        rec["release_eligible"] = True; rec["status"] = "passed"
    if keys:
        for k in dg.RESUME_PROVENANCE_KEYS: rec.pop(k, None)
    if reason: rec.pop("release_eligible_reason", None)
    if dir_: shutil.rmtree(d / rid, ignore_errors=True)
    if log: lg = "".join(l for l in lg.splitlines(True) if not re.match(r"(CHECKPOINT|RESUME)\b", l))
    if rename:
        lg = lg.replace(rid, rename); rec = json.loads(json.dumps(rec).replace(rid, rename))
        (d / f"{rid}.json").unlink(); (d / f"{rid}.log").unlink(); rid = rename
    (d / f"{rid}.json").write_text(json.dumps(rec, indent=2, sort_keys=True)); (d / f"{rid}.log").write_text(lg)
    return rid
def snapshot(repo):
    s = WORK / (repo.name + "-snap"); shutil.rmtree(s, ignore_errors=True); shutil.copytree(rd(repo), s); return s
def restore(repo, s):
    shutil.rmtree(rd(repo)); shutil.copytree(s, rd(repo))

# ---------------------------------------------------------------- 2. regression: plain full run
say("== REGRESSION: plain uninterrupted full run, base runner vs RESUMEFIX runner")
base_src = subprocess.run(["git", "show", f"{MB}:brambleloop/run_tests.sh"], capture_output=True, check=True).stdout
norm = lambda s: re.sub(r"\d{8}T\d{6}Z-\d+|\d{4}-\d\d-\d\dT[\d:.]+Z?|/tmp/[^\s\"]+|rr2-\w+|\b\d+(\.\d+)?s\b|DURATION: \d+|\"duration_s\": \d+|\"pid\": \d+|\"hostname\": \"[^\"]*\"|[0-9a-f]{40}", "X", s)
outs = {}
for tag, src in (("base", base_src), ("fix", None)):
    repo = sandbox(f"plain-{tag}", src); r = run(repo); rid = newest(repo)
    rec = json.loads((rd(repo) / f"{rid}.json").read_text())
    outs[tag] = (r.returncode, norm(r.stdout), norm((rd(repo) / f"{rid}.log").read_text()),
                 {k: norm(json.dumps(v)) for k, v in rec.items()}, sorted(p.name for p in rd(repo).iterdir() if p.name != rid + ".json" and p.name != rid + ".log"))
    say(f"  {tag}: exit {r.returncode}, status {rec['status']}, release_eligible {rec['release_eligible']}, scope {rec['scope']}")
    if tag == "fix": evaluate("fix plain run (must PASS all four)", repo, rid); plain_fix = (repo, rid)
    else: evaluate("base plain run, evaluated by fixed guards", repo, rid)
b, f = outs["base"], outs["fix"]
say("  exit equal:", b[0] == f[0], "| stdout equal:", b[1] == f[1], "| log equal:", b[2] == f[2],
    "| record keys equal:", sorted(b[3]) == sorted(f[3]), "| record values equal:", b[3] == f[3],
    "| record-dir entries:", b[4], f[4])
if b[3] != f[3]: say("  record diffs:", {k: (b[3].get(k), f[3].get(k)) for k in set(b[3]) | set(f[3]) if b[3].get(k) != f[3].get(k)})
if b[2] != f[2]:
    import difflib; say("  log diff:\n" + "".join(list(difflib.unified_diff(b[2].splitlines(True), f[2].splitlines(True)))[:40]))
if b[1] != f[1]:
    import difflib; say("  stdout diff:\n" + "".join(list(difflib.unified_diff(b[1].splitlines(True), f[1].splitlines(True)))[:40]))

# ---------------------------------------------------------------- 1. gating: every mode, every forgery
say("== GATING: checkpoint / shard / resumed runs, and forgeries")
def ckpt_runs():
    repo = sandbox("ck"); r = run(repo, CHECKPOINT="1"); yield "CHECKPOINT=1 complete", repo, newest(repo), r
    repo = sandbox("sh"); r = run(repo, SHARD="0/1"); yield "SHARD=0/1 complete", repo, newest(repo), r
    repo = sandbox("rs"); gate = repo.parent / "rs-gate"
    e = env(repo, CHECKPOINT="1", GATE_FILE=str(gate))
    p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], cwd=repo, env=e, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    t = time.time() + 120
    while not Path(str(gate) + ".started").exists() and time.time() < t: time.sleep(0.05)
    time.sleep(1); os.killpg(p.pid, signal.SIGKILL); p.wait(); gate.write_text("open")
    rid = newest(repo); r = run(repo, RESUME=rid, GATE_FILE=str(gate), CHECKPOINT="1")
    yield "CHECKPOINT=1 killed, then RESUME", repo, rid, r
for label, repo, rid, r in ckpt_runs():
    rec = json.loads((rd(repo) / f"{rid}.json").read_text())
    say(f" {label}: exit {r.returncode} status {rec['status']} eligible {rec['release_eligible']} "
        f"keys {[k for k in dg.RESUME_PROVENANCE_KEYS if k in rec]} scope {rec['scope']}"
        + (f" STDERR {r.stderr[-300:]!r}" if r.returncode else ""))
    snap = snapshot(repo)
    variants = [("as written", {}), ("forged bit", dict(bit=True)),
                ("forged bit + provenance keys deleted", dict(bit=True, keys=True, reason=True)),
                ("... + checkpoint dir deleted", dict(bit=True, keys=True, reason=True, dir_=True)),
                ("... + run id renamed (dir kept)", dict(bit=True, keys=True, reason=True, rename="20991231T000000Z-1")),
                ("forged bit + keys deleted + log edited (dir kept)", dict(bit=True, keys=True, reason=True, log=True)),
                ("forged bit + dir deleted + log edited (keys kept)", dict(bit=True, dir_=True, log=True)),
                ("ALL: keys, dir, log, rename (= forging a plain run)", dict(bit=True, keys=True, reason=True, dir_=True, log=True, rename="20991231T000000Z-2"))]
    for vl, kw in variants:
        restore(repo, snap); nrid = forge(repo, rid, **kw); evaluate(vl, repo, nrid)
    restore(repo, snap)

# ---------------------------------------------------------------- kill at every step boundary
say("== KILL at every checkpoint step (SIGKILL to the process group when the tool is entered/left)")
wrap = WORK / "killtool.py"
wrap.write_text("import os, signal, subprocess, sys\n"
  "real=os.environ['REAL_TOOL']; kf=os.environ['KILL_FILE']; at=open(kf).read() if os.path.exists(kf) else ''; step=sys.argv[1]\n"
  "if at==step+':before': os.killpg(os.getpgid(0), signal.SIGKILL)\n"
  "r=subprocess.run([sys.executable, real, *sys.argv[1:]])\n"
  "if at==step+':after': os.killpg(os.getpgid(0), signal.SIGKILL)\n"
  "sys.exit(r.returncode)\n")
for at in [f"{s}:{w}" for s in ("plan","begin","start","finish","restore","finalize","seal") for w in ("before","after")]:
    repo = sandbox("k-" + at.replace(":", "-"))
    kf = repo.parent / (repo.name + "-killat"); kf.write_text(at)
    kenv = dict(CHECKPOINT="1", CHECKPOINT_TOOL=str(wrap), REAL_TOOL=str(repo / "scripts/suite_checkpoint.py"), KILL_FILE=str(kf))
    e = env(repo, **kenv)
    p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], cwd=repo, env=e, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    try: p.wait(timeout=300)
    except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); p.wait()
    recs = list(rd(repo).glob("*.json")) if rd(repo).is_dir() else []
    if not recs: say(f"  {at:16} no record written"); continue
    rid = recs[0].stem; rec = json.loads(recs[0].read_text())
    snap = snapshot(repo)
    a = evaluate(f"{at} as left (status {rec['status']}, eligible {rec['release_eligible']})", repo, rid)
    restore(repo, snap); forge(repo, rid, bit=True); evaluate(f"{at} + forged bit", repo, rid)
    kf.write_text(""); r2 = run(repo, RESUME=rid, **kenv)
    rec2 = json.loads((rd(repo) / f"{rid}.json").read_text())
    say(f"  {at:16} then RESUME: exit {r2.returncode}, status {rec2['status']}, eligible {rec2['release_eligible']}" + (f" ({r2.stderr.strip().splitlines()[-1][:160]})" if r2.returncode and r2.stderr.strip() else ""))
    evaluate(f"{at} after RESUME", repo, rid)
Path(sys.argv[2]).write_text("\n".join(OUT) + "\n")
