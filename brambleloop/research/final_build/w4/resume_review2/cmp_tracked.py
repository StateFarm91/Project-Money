"""Usage (from brambleloop/): git show b0133916:brambleloop/src/brambleloop/ops/release_record.py > /tmp/base.py; python3 cmp_tracked.py /tmp/base.py"""
import json, sys, importlib.util
from pathlib import Path
sys.path.insert(0, "src")
from brambleloop.ops import release_record as new
spec = importlib.util.spec_from_file_location("rr_base", sys.argv[1]); old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
rd = Path("release")
for p in sorted(rd.glob("RELEASE_*.json")):
    rec = json.loads(p.read_text())
    a, b = old.check_record(rec, rd), new.check_record(rec, rd)
    print(p.name[:20], "same" if a == b else "DIFF", len(a), len(b), [x for x in b if x not in a][:1])
print("verify_build new:", new.verify_build(Path(".").resolve())["ok"] if hasattr(new,"verify_build") else "n/a")
