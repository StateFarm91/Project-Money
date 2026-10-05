import ast, json, pathlib, subprocess, sys, types
base=pathlib.Path(r'C:\Users\Jacob McKenna\Documents\Codex\2026-09-27\visual-v2-independent-architecture-r-d')
repo=base/'final-draft-durability-01'
sys.path[:0]=[str(base/'runtime-build2'),str(base/'final-build-integration-01/brambleloop/src')]
def source(path):
 return subprocess.check_output(['git','show','e087dd4:brambleloop/src/brambleloop/'+path],cwd=repo,text=True)
import brambleloop.intel.coverage as coverage
exec(compile(source('intel/coverage.py'),'e087dd4:intel/coverage.py','exec'),coverage.__dict__)
module=types.ModuleType('brambleloop.creative.origin_repro')
module.__package__='brambleloop.creative'
tree=ast.parse(source('creative/intake.py'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_gap_for','advance_gap')]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'e087dd4:intake:selected-exact-functions','exec'),module.__dict__)
from brambleloop.core.db import Database, Base
from brambleloop.core.models import CoverageGap, MjsMissionEvent
from sqlalchemy import select
db=Database('sqlite:///:memory:',scratch=True)
Base.metadata.create_all(db.engine)
a=coverage.upsert(db,benchmark_key='benchmark-a',arena='arena-a',pod='blankets')
b=coverage.upsert(db,benchmark_key='benchmark-b',arena='arena-b',pod='blankets')
with db.session() as s:
 event=MjsMissionEvent(benchmark_key='benchmark-b',listing_ref='listing-b',fingerprint='b'*64,pod='blankets',arena='arena-b',gap_id=b,steps={'coverage':{'gap':b}})
 s.add(event);s.flush(); event_id=event.id
result=module.advance_gap(db,'blankets','certified',reason='product-b certified',product_slug='product-b')
with db.session() as s:
 rows=[{'id':r.id,'benchmark':r.benchmark_key,'state':r.state,'product_slug':r.product_slug} for r in s.scalars(select(CoverageGap).order_by(CoverageGap.id))]
assert rows[0]['state']=='certified' and rows[1]['state']=='uncovered',rows
print(json.dumps({'source_sha':'e087dd4','event_id':event_id,'event_origin_gap':b,'result':result,'rows':rows},indent=2))
db.engine.dispose()
