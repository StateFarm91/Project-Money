"""Index the existing 75 findings against pinned integrated source; no source edits."""
import ast,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
BASE="4edacff1f8b445a84749464dc1d7271e6c71173e"
AUDIT="e6c397656d42406d9da338264f15bb36fadab5cf"
def git(*args):return subprocess.check_output(["git",*args],cwd=REPO)
def symbols(text,name):
    if not name:return []
    try:tree=ast.parse(text)
    except SyntaxError:return []
    target=name.split(".")[-1]
    return [n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==target]
def main():
    findings=json.loads(git("show",AUDIT+":brambleloop/research/codex_b2_integration_pack/FINDINGS.json"))["findings"]
    tree={}
    for line in git("ls-tree","-r",BASE).decode().splitlines():
        meta,p=line.split("\t",1);tree[p]=meta.split()[2]
    records=[]
    for f in findings:
        affected=[]
        for a in f["affected"]:
            p=a["path"];oid=tree.get(p);entry={"path":p,"symbol":a["symbol"],"exists_at_head":bool(oid),"blob":oid}
            if oid:
                raw=git("cat-file","blob",oid);text=raw.decode("utf-8","replace")
                matches=symbols(text,a["symbol"]) if p.endswith(".py") else []
                entry["symbol_found"]=bool(matches)
                entry["lines"]=[{"start":n.lineno,"end":n.end_lineno} for n in matches]
                entry["sha256"]=hashlib.sha256(raw).hexdigest()
                entry["url"]="https://github.com/StateFarm91/Project-Money/blob/"+BASE+"/"+p+(("#L"+str(matches[0].lineno)) if matches else "")
            affected.append(entry)
        records.append({"id":f["id"],"cluster":f["cluster"],"title":f["title"],"requirements":f["requirements"],
          "claude_defects":f["claude_defects"],"prior_classification":f["classification"],
          "existing_behavior":f["existing_behavior"],"required_behavior":f["required_behavior"],"affected":affected})
    out=HERE/"out";out.mkdir(exist_ok=True)
    result={"base":BASE,"prior_audit":AUDIT,"records":records}
    (out/"source_index.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    print("Indexed",len(records),"findings; missing affected paths:",sorted({a["path"] for r in records for a in r["affected"] if not a["exists_at_head"]}))
if __name__=="__main__":main()
