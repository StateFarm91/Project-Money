import sys,json,re
from pathlib import Path
sys.path[:0]=[str(Path("../runtime-build2").resolve()),str(Path("brambleloop/src").resolve())]
from pypdf import PdfReader
from brambleloop.publish import pdf,charts
out={}
for term in ("US","UK"):
 reader=PdfReader(f"output/pdf/cloudline-tiled-{term}.pdf")
 records=[]
 for number,page in enumerate(reader.pages,1):
  text=page.extract_text() or ""
  match=re.search(r"Tile (\d+) of (\d+):",text)
  if not match:continue
  matrices=[]
  def visitor(op,args,cm,tm):
   if op==b"Do":matrices.append(list(cm))
  page.extract_text(visitor_operand_before=visitor)
  assert len(matrices)==1,(number,matrices)
  a,b,c,d,x,y=matrices[0];image=page.images[0].image
  scale=min(a/image.width,d/image.height)
  minimum=min(charts.flat_type_px(32).values())*scale
  assert minimum>=pdf.MIN_BODY_PT
  assert x>=pdf.MARGIN-.01 and y>=pdf.MARGIN-.01
  assert x+a<=pdf.PAGE_W-pdf.MARGIN+.01 and y+d<=pdf.PAGE_H-pdf.MARGIN+.01
  records.append({"page":number,"tile":int(match[1]),"minimum_type_pt":minimum,"image_bounds":[x,y,x+a,y+d]})
 assert len(records)==20
 out[term]={"tile_count":len(records),"min_printed_type_pt":min(r["minimum_type_pt"] for r in records),"pages":records}
Path("codex/chart_tiles/pdf_measurements.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
print({k:{"tiles":v["tile_count"],"min_pt":v["min_printed_type_pt"]} for k,v in out.items()})
