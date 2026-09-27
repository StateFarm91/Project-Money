"""Offline Git evidence coverage. Reads committed blobs, never providers or live databases."""
import collections, hashlib, io, json, re, subprocess
import numpy as np
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BASE="0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56"
CLAUDE="4edacff1f8b445a84749464dc1d7271e6c71173e"
PREAUDIT="49e5b0a1e289906a7c89dd386c6733ed0c2a63cc"
def git(*args):
    return subprocess.check_output(["git",*args],cwd=REPO)
def core(p):
    return bool(re.search(r"(^|/)(visual/|VISUAL[^/]*|YARN_SLIP_RESEARCH\.md$|(?:pbr|topology|wave5|yarn)[^/]*\.(?:png|svg)$)",p,re.I)
        or re.search(r"brambleloop/research/(?:d|e[1-5]|bench[12]|v1grad)/",p)
        or re.search(r"/(?:cir|gateway)/",p)
        or re.search(r"/tests/(?:test_.*(?:visual|stitch|drape|render|milestone|fabric|topology|gateway|model_freeze|photoreal|reference_pack)|regressions/.*stitch)",p))
kw=re.compile(r"(?:\bvisual\b|photograph\w*|Visual V1|Product.Truth|Milestone D|VISUAL_(?:WAVE|E[1-5]|BENCH|V1)|(?:bench1|bench2|v1grad|photoreal|canonical.model|yarn.slid|yarn.slip|visual\.gallery|visual\.parity|model_bearing_render))",re.I)
text_ext={".md",".py",".json",".txt",".log",".mbox",".diff",".patch",".toml",".yaml",".yml"}
prior=json.loads((HERE.parent/"out/source_inventory.json").read_text(encoding="utf-8"))
prior_paths={"brambleloop/"+r["path"] for r in prior}
durable="\n".join(git("show",PREAUDIT+":brambleloop/research/visual_v2/"+n).decode("utf-8") for n in ["CURRENT_STATE.md","DECISIONS.md","EXPERIMENTS.md","VISUAL_V2_ARCHITECTURE.md"])
refs={line.split()[1]:line.split()[0] for line in git("for-each-ref","--format=%(objectname) %(refname)","refs/remotes/origin").decode().splitlines() if not line.endswith("/visual-v2-rnd")}
refs.update({"audit/base":BASE,"audit/visual-v2-pre-audit":PREAUDIT})
trees={}
for ref,rev in refs.items():
    records=[]
    for line in git("ls-tree","-r",rev).decode().splitlines():
        meta,p=line.split("\t",1)
        if "/visual_v2/" in p:continue
        records.append((p,meta.split()[2]))
    trees[ref]=records
objects={oid for records in trees.values() for p,oid in records if core(p) or Path(p).suffix.lower() in text_ext}
proc=subprocess.Popen(["git","cat-file","--batch"],cwd=REPO,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
blobs={}
for oid in sorted(objects):
    proc.stdin.write((oid+"\n").encode());proc.stdin.flush()
    header=proc.stdout.readline().decode().split();size=int(header[2])
    blobs[oid]=proc.stdout.read(size);assert proc.stdout.read(1)==b"\n"
proc.stdin.close();proc.wait()
records={}
for ref,entries in trees.items():
    for p,oid in entries:
        data=blobs.get(oid,b"")
        matches=[]
        if Path(p).suffix.lower() in text_ext:
            matches=[(i,s.strip()[:220]) for i,s in enumerate(data.decode("utf-8","replace").splitlines(),1) if kw.search(s)]
        direct=core(p) or p in prior_paths
        if not direct and not matches:continue
        key=(p,oid)
        if key not in records:
            records[key]={"path":p,"git_blob":oid,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                "class":"experimental_or_instrument" if direct else "integration_or_context",
                "prior_inventory":p in prior_paths,"filename_named_in_durable_state":Path(p).name in durable,
                "matching_lines":matches[:16],"refs":[]}
        records[key]["refs"].append(ref)
new_tip=dict(trees["refs/remotes/origin/claude/visual-investigation"])
old=dict(trees["audit/base"])
changed=[r["path"] for r in records.values() if "refs/remotes/origin/claude/visual-investigation" in r["refs"] and old.get(r["path"])!=r["git_blob"]]
core_runs=[p for p in set(old)|set(new_tip) if re.search(r"brambleloop/research/(?:d|e[1-5]|bench[12]|v1grad)/",p) and old.get(p)!=new_tip.get(p)]
# History indexes intermediate/deleted sources. It is NOT a claim each old revision was read.
history=[]
rev=None
for line in git("log","--all","--format=COMMIT:%H","--name-only","--","brambleloop").decode().splitlines():
    if line.startswith("COMMIT:"):rev=line[7:];continue
    if line and "/visual_v2/" not in line and (core(line) or line.endswith(("BUILD_STATE.md","DECISION_LOG.md"))):
        history.append({"commit":rev,"path":line})
historical_only=[]
for p in sorted({r["path"] for r in history}-{r["path"] for r in records.values()}):
    commits=[r["commit"] for r in history if r["path"]==p]
    for rev in commits:
        line=git("ls-tree",rev,"--",p).decode().strip()
        if not line:continue
        oid=line.split()[2];data=git("cat-file","blob",oid)
        r={"path":p,"commit":rev,"git_blob":oid,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        if p.endswith(".npy"):
            arr=np.load(io.BytesIO(data),allow_pickle=False)
            r.update(shape=list(arr.shape),dtype=str(arr.dtype),finite=int(np.isfinite(arr).sum()),nan=int(np.isnan(arr).sum()))
        historical_only.append(r);break
result={"schema":1,"base":BASE,"claude_tip":CLAUDE,"refs":refs,
 "scope":"Every tracked path at fetched remote tips plus base and pre-audit HEAD; keyword scan of text blobs; Visual-path historical change index. Historical index is discovery, not semantic ingestion of every revision. External/uncommitted files and expired URLs are unavailable.",
 "previous_inventory_entries":len(prior),"unique_paths":len({r["path"] for r in records.values()}),
 "versions":len(records),"selected_text_scan_pattern":kw.pattern,"core_classifier":core.__doc__,
 "core_experiment_paths_changed_since_base":sorted(set(core_runs)),
 "claude_selected_paths_changed_since_base":sorted(set(changed)),
 "records":sorted(records.values(),key=lambda r:(r["path"],r["git_blob"])),
 "history_only_recovered":historical_only,"history":history}
assert refs["refs/remotes/origin/claude/visual-investigation"]==CLAUDE
assert not core_runs,"New central experiment evidence needs investigation."
(HERE/"inventory.json").write_text(json.dumps(result,indent=2,ensure_ascii=True)+"\n",newline="\n")
counts=collections.Counter(r["class"] for r in records.values())
absent=sorted({r["path"] for r in records.values() if not r["prior_inventory"] and r["class"]=="experimental_or_instrument"})
print(json.dumps({"paths":result["unique_paths"],"versions":len(records),"classes":counts,"history_entries":len(history),"core_experiment_changes":len(core_runs),"absent_core_paths":absent,"claude_changed_count":len(set(changed)),"history_only_recovered":historical_only},indent=2))
