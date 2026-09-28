"""C-74 regression controls and platform-qualified closure counts. No app edits."""
import argparse,dataclasses,json,os,socket,sys
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--deps",required=True);ap.add_argument("--source-root");ap.add_argument("--source-sha",default="4edacff1f8b445a84749464dc1d7271e6c71173e");ap.add_argument("--suffix",default="");args=ap.parse_args()
if args.source_root:ROOT=Path(args.source_root).resolve()
sys.path[:0]=[str(Path(args.deps).resolve()),str(ROOT/"src")]
def offline(*a,**k):raise RuntimeError("Network refused")
socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline
from brambleloop.build2 import closure as C,requirements as R,reachability as reach
ids=[39,61,64,104,116,147,165,208,210,211,243,244,245,250,277,278,281,294,295,304]
checks=[]
for mode,values in [("unchecked",None),("closed",{g.key:False for g in C.executor.GATES}),("open",{g.key:True for g in C.executor.GATES})]:
    for i in ids:
        row=dataclasses.replace(R.get(i),status=R.PARTIAL,parked_on="")
        got=C.classify(row,gate_open=values)
        checks.append({"test":f"P01_{i}_{mode}","pass":got["state"]==C.OPEN,"actual":got["state"]})
# Isolate the matrix decision from the current unresolved rows: zero OPEN must
# not disguise absent/failed live reads. This changes no registry file.
with patch.object(R,"load",return_value=[]):
    got=C.matrix()
    checks.append({"test":"P03_no_database","pass":not got["closed_out"] and got["closeout_indeterminate"]})
    with patch.object(C.executor,"gate_states",side_effect=RuntimeError("synthetic unreadable gate")):
        got=C.matrix(db=object())
        checks.append({"test":"P03_gate_read_error","pass":not got["closed_out"] and got["closeout_indeterminate"]})
    with patch.object(C.executor,"gate_states",return_value={g.key:{"open":False} for g in C.executor.GATES}):
        got=C.matrix(db=object())
        checks.append({"test":"P03_live_read_control","pass":got["closed_out"] and not got["closeout_indeterminate"]})
assert all(x["pass"] for x in checks)
native=C.matrix()
original=reach._rel_of
native_label=original("brambleloop.runtime.worker")
# Diagnostic only. Match POSIX path labels while retaining actual source and
# every gate/proof rule. Do not present this as an unmodified Windows suite pass.
reach._rel_of=lambda mod:original(mod).replace("\\","/")
reach.clear_cache()
try:
    posix=C.matrix()
    paths={"commerce/orders_ingest.py":reach.reached("commerce/orders_ingest.py"),
           "commerce/kill_table.py":reach.reached("commerce/kill_table.py")}
finally:
    reach._rel_of=original;reach.clear_cache()
def compact(m):
    return {k:m[k] for k in ["total","counts","closed_out","closeout_indeterminate","gates_checked_live"]}
out={"base":args.source_sha,"checks":checks,
     "native_windows":compact(native),"native_worker_path_label":native_label,
     "posix_path_diagnostic":compact(posix),"diagnostic_reachability":paths,
     "limitation":"Only in-memory _rel_of separator normalization in diagnostic. No live production gate reads; no requirement status changed.",
     "paid_spend":0}
(HERE/("out/closure_checks"+args.suffix+".json")).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8",newline="\n")
print(json.dumps({"checks_passed":len(checks),"native":out["native_windows"],"posix_diagnostic":out["posix_path_diagnostic"]}))
