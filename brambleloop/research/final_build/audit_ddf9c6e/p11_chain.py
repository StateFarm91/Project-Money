from _h import *
from sqlalchemy import text, select
from brambleloop.finance.accounting import ledger, controller, close, profitability, views
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
print("baseline chain ok:", ledger.verify_chain(db)["ok"])
def raw(sql, **p):
    with db.session() as s: s.execute(text(sql), p)
tests = {
 "entry.product_slug reassign": "update acct_journal_entries set product_slug='other-product' where id=(select min(id) from acct_journal_entries where product_slug!='')",
 "entry.department rewrite": "update acct_journal_entries set department='x' where id=1",
 "entry.channel rewrite": "update acct_journal_entries set channel='x' where id=1",
 "entry.detail rewrite": "update acct_journal_entries set detail='{}' where id=1",
 "entry.source_period rewrite": "update acct_journal_entries set source_period='1999-01' where id=1",
 "entry.posted_at rewrite": "update acct_journal_entries set posted_at='2000-01-01' where id=1",
 "entry.reverses_id rewrite": "update acct_journal_entries set reverses_id=1 where id=2",
 "posting.memo rewrite": "update acct_postings set memo='hacked' where id=1",
 "posting.currency rewrite": "update acct_postings set currency='USD' where id=1",
 "posting.amount_original rewrite": "update acct_postings set amount_original=999 where id=1",
}
for name, sql in tests.items():
    raw(sql); ok = ledger.verify_chain(db)["ok"]; print(f"{name:34s} chain_ok={ok}")
# tail truncation
with db.session() as s:
    last = s.execute(text("select max(id) from acct_journal_entries")).scalar()
    s.execute(text("delete from acct_postings where entry_id=:i"),{"i":last}); s.execute(text("delete from acct_journal_entries where id=:i"),{"i":last})
print("tail entry deleted: chain_ok", ledger.verify_chain(db)["ok"])
