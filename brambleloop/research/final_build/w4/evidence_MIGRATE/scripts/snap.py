"""Snapshot a DB: schema (columns/types/nullability/defaults, indexes, constraints) and, per
table, row count plus an md5 over every row restricted to a given column set.

usage: snap.py <dbname> <out.json> [<ref_snapshot.json>]
With a reference snapshot, the content hash is computed over the reference's columns for each
reference table, so an additive migration (new columns) still compares like for like.
"""
import hashlib
import json
import sys

import psycopg2

db, out = sys.argv[1], sys.argv[2]
ref = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
c = psycopg2.connect(host="127.0.0.1", port=55433, user="postgres", dbname=db)
cur = c.cursor()
cur.execute("""select table_name, column_name, data_type, coalesce(character_maximum_length,0),
                      is_nullable, coalesce(column_default,'')
               from information_schema.columns where table_schema='public'
               order by table_name, ordinal_position""")
cols = {}
for t, col, typ, ln, nul, dflt in cur.fetchall():
    cols.setdefault(t, {})[col] = [typ, ln, nul, dflt]
cur.execute("select tablename, indexname, indexdef from pg_indexes where schemaname='public'")
idx = {f"{t}.{i}": d for t, i, d in cur.fetchall()}
cur.execute("""select conrelid::regclass::text, conname, pg_get_constraintdef(oid)
               from pg_constraint where connamespace='public'::regnamespace""")
cons = {f"{t}.{n}": d for t, n, d in cur.fetchall()}
data = {}
for t in sorted(cols):
    use = sorted(ref["columns"][t]) if ref and t in ref["columns"] else sorted(cols[t])
    sel = ", ".join(f'"{x}"' for x in use)
    cur.execute(f'select count(*) from "{t}"')
    n = cur.fetchone()[0]
    cur.execute(f'select md5(coalesce(string_agg(r::text, chr(10) order by r::text), \'\')) '
                f'from (select {sel} from "{t}") r')
    data[t] = {"rows": n, "md5": cur.fetchone()[0], "hashed_columns": len(use)}
json.dump({"db": db, "columns": cols, "indexes": idx, "constraints": cons, "data": data},
          open(out, "w"), indent=1, sort_keys=True)
print(f"{db}: {len(cols)} tables, {sum(d['rows'] for d in data.values())} rows, "
      f"{sum(len(v) for v in cols.values())} columns, {len(idx)} indexes, {len(cons)} constraints")
