"""Row-by-row: every row of every table in <ref_db> must exist in <db> (by primary key) with
identical values in every <ref_db> column. usage: rowdiff.py <ref_db> <db>"""
import json
import sys

import psycopg2

ref_db, db = sys.argv[1:3]
ca = psycopg2.connect(host="127.0.0.1", port=55433, user="postgres", dbname=ref_db)
cb = psycopg2.connect(host="127.0.0.1", port=55433, user="postgres", dbname=db)
a, b = ca.cursor(), cb.cursor()
a.execute("select tablename from pg_tables where schemaname='public' order by 1")
tables = [r[0] for r in a.fetchall()]
out = {"tables": len(tables), "rows_compared": 0, "missing_rows": {}, "changed_rows": {},
       "changed_columns": {}}
for t in tables:
    a.execute("""select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid
                 and a.attnum = any(i.indkey) where i.indrelid=%s::regclass and i.indisprimary
                 order by a.attnum""", (f'"{t}"',))
    pk = [r[0] for r in a.fetchall()]
    a.execute("select column_name from information_schema.columns where table_schema='public' "
              "and table_name=%s order by ordinal_position", (t,))
    cols = [r[0] for r in a.fetchall()]
    sel = ", ".join(f'"{c}"::text' for c in cols)
    key = [cols.index(k) for k in pk] or list(range(len(cols)))
    a.execute(f'select {sel} from "{t}"')
    b.execute(f'select {sel} from "{t}"')
    rb = {tuple(r[i] for i in key): r for r in b.fetchall()}
    for r in a.fetchall():
        out["rows_compared"] += 1
        k = tuple(r[i] for i in key)
        other = rb.get(k)
        if other is None:
            out["missing_rows"][t] = out["missing_rows"].get(t, 0) + 1
        elif other != r:
            out["changed_rows"][t] = out["changed_rows"].get(t, 0) + 1
            for c, x, y in zip(cols, r, other):
                if x != y:
                    out["changed_columns"].setdefault(t, set()).add(c)
out["changed_columns"] = {k: sorted(v) for k, v in out["changed_columns"].items()}
print(json.dumps(out, indent=1))
