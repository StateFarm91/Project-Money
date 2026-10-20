import json, sys
a = json.load(open(sys.argv[1]))["schema"]; b = json.load(open(sys.argv[2]))["schema"]
print("added tables:", sorted(set(b) - set(a)))
print("removed tables:", sorted(set(a) - set(b)))
chg = {t: {"added": sorted(set(b[t]) - set(a[t])), "removed": sorted(set(a[t]) - set(b[t])),
           "altered": sorted(c for c in set(a[t]) & set(b[t]) if a[t][c] != b[t][c])}
       for t in set(a) & set(b)}
chg = {t: v for t, v in chg.items() if any(v.values())}
print("changed existing tables:", json.dumps(chg, indent=1) if chg else "none")
