import sys, os, json, hashlib, re
from pathlib import Path
sys.path[:0]=[str(Path("../runtime-build2").resolve()),str(Path("brambleloop/src").resolve())]
os.environ["BRAMBLELOOP_FONT_PATH"]="C:/Users/Jacob McKenna/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/share/fonts/DejaVuSans.ttf"
from brambleloop.products.builder import for_slug
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.publish import pdf
from pypdf import PdfReader
cir=for_slug("cloudline-baby-blanket");fingerprint=cir.fingerprint
twin=build_twin(cir,compile_cir(cir));art=pdf._chart_art(cir,twin)
grid,colors=twin.chart_grid(),twin.color_grid();rebuilt={};duplicate=[]
for tile in art["tiles"]:
 for ri,row in enumerate(tile["grids"][0],tile["row_start"]-1):
  for ci,stitch in enumerate(row,tile["column_start"]-1):
   if (ri,ci) in rebuilt:duplicate.append((ri,ci))
   rebuilt[ri,ci]=(stitch,tile["grids"][1][ri-tile["row_start"]+1][ci-tile["column_start"]+1])
expected={(ri,ci):(stitch,colors[ri][ci]) for ri,row in enumerate(grid) for ci,stitch in enumerate(row)}
assert rebuilt==expected and not duplicate
out=Path("output/pdf");out.mkdir(parents=True,exist_ok=True)
result={"fingerprint":fingerprint,"rows":len(grid),"columns":len(grid[0]),"cells":len(expected),"tiles":len(art["tiles"]),"exact_coverage":True,"duplicates":len(duplicate),"minimum_cell_mm":min(t["cell_mm"] for t in art["tiles"]),"minimum_type_pt":min(t["minimum_type_pt"] for t in art["tiles"]),"cell_floor_mm":pdf.CHART_MIN_CELL_MM,"ranges":[{k:t[k] for k in ("row_start","row_end","column_start","column_end")} for t in art["tiles"]],"documents":{}}
for term in ("US","UK"):
 doc=pdf.build_pattern_pdf(cir,terminology=term)
 dest=out/f"cloudline-tiled-{term}.pdf";dest.write_bytes(doc.pdf_bytes)
 pages=PdfReader(dest).pages
 charts=[i+1 for i,p in enumerate(pages) if re.search(r"Tile \d+ of \d+:",p.extract_text() or "")]
 result["documents"][term]={"pages":doc.pages,"problems":doc.problems,"chart_pages":charts,"sha256":hashlib.sha256(doc.pdf_bytes).hexdigest()}
assert cir.fingerprint==fingerprint
Path("codex/chart_tiles/result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k!="ranges"},indent=2))
