"""Read-only integrity check of saved evidence, not a new certification run."""
import ast,hashlib,json,re,subprocess
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
def read(name):return json.loads((HERE/name).read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=read("artifact_manifest.json")
for name,digest in manifest["sha256"].items():
    assert sha(REPO/name)==digest,("changed package bytes",name)
recon=read("RECONCILIATION.json");rows=recon["findings"]
allowed={"FIXED","STILL PRESENT","CHANGED — REAUDIT REQUIRED","BLOCKED FROM DETERMINING"}
assert len(rows)==len({r["id"] for r in rows})==75
assert all(r["status"] in allowed for r in rows)
assert dict(Counter(r["status"] for r in rows))==recon["counts"]
for r in rows:
    for evidence in r["evidence"]:assert (HERE/evidence).is_file(),evidence
receipt=read("out/receipt_adversarial_2e66b3a_v2.json")
assert (receipt["ran"],receipt["failures"],receipt["errors"])==(11,9,0)
assert receipt["script_sha256"]==sha(HERE/"test_receipt_adversarial.py")
closure=read("out/closure_checks_2e66b3a.json")
assert len(closure["checks"])==63 and all(c["pass"] for c in closure["checks"])
for key in ("native_windows","posix_path_diagnostic"):
    m=closure[key]
    assert sum(m["counts"].values())==m["total"]==320
    assert not m["closed_out"] and m["closeout_indeterminate"] and not m["gates_checked_live"]
growth=read("out/growth_followups_2e66b3a_claim.json")
o=growth["band_observations"]
assert (o["before"],o["after"],o["customer_priority"])==(25,5,10)
assert o["claimed_job_type"]=="chain.rebuild" and o["claimed_job_id"]!=o["waiting_customer_job_id"]
assert growth["results"][0]["status"]=="FAIL"
route=read("out/growth_followups_2e66b3a.json")
assert next(r for r in route["results"] if r["test"].startswith("existing_growth"))["status"]=="PASS"
for row in read("out/focused_suites.json")["results"]:
    assert sha(HERE/"out"/(row["suite"]+".log"))==row["output_sha256"]
delta=read("out/delta_2198861.json")
assert delta["new_head"]==recon["claude_head"]
assert all(f["unchanged"] for f in delta["critical_file_equality"]) and delta["queue_claim_unchanged"]
sync=read("out/remote_sync.json")
assert len(sync["critical_source_equality"])==11 and all(r["identical"] for r in sync["critical_source_equality"])
for p in HERE.glob("*.py"):ast.parse(p.read_text(encoding="utf-8"))
for p in HERE.glob("*.md"):
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
        if "://" not in target:assert (p.parent/target.split("#")[0]).exists(),(p.name,target)
changed=subprocess.check_output(["git","diff","--name-only","4edacff"],cwd=REPO,text=True).splitlines()
assert all(p=="CODEX_SCOPE.md" or p.startswith("brambleloop/research/codex_build2_assist_01/") for p in changed),changed
print(json.dumps({"package_files_checked":len(manifest["sha256"]),"reconciliation_counts":recon["counts"],
    "receipt_failures_preserved":9,"closure_controls":63,"priority_effect_reproduced":True,
    "app_source_changes":0,"paid_spend":0}))
