"""Actual PDF text bounds and fail-closed chart diagnostics; synthetic local checks."""
import io, sys, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from brambleloop.publish import pdf
from brambleloop.products.builder import for_slug
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin

class LayoutBounds(unittest.TestCase):
    def test_key_value_wrap_retains_text_and_separates_actual_pdf_runs(self):
        d=pdf._Doc("layout");d.new_page()
        key="BLOCKING PINS AND A SURFACE"
        value="for pinning the piece out damp to the finished measurements"
        d.kv(key,value);d.kv("NEXT", "next row")
        page=PdfReader(io.BytesIO(d.finish())).pages[0];runs=[]
        def visit(text,cm,tm,font,size):
            text=text.strip()
            if text:runs.append((text,tm[4],tm[5],font["/BaseFont"].removeprefix("/"),size))
        extracted=page.extract_text(visitor_text=visit)
        body=[r for r in runs if not r[0].startswith("page ")]
        # Two key/value pairs were drawn; a page that extracted to nothing would pass every
        # bound below vacuously, so the body is required to hold at least those four runs.
        self.assertGreaterEqual(len(body),4,body)
        for text,x,y,font,size in body:
            self.assertGreaterEqual(size,9)
            self.assertGreaterEqual(x,pdf.MARGIN-.01)
            self.assertLessEqual(x+stringWidth(text,font,size),pdf.PAGE_W-pdf.MARGIN+.01)
        labels=[r for r in body if r[3]=="Helvetica-Bold" and r[0]!="NEXT"]
        vals=[r for r in body if r[3]=="Helvetica" and r[0]!="next row"]
        self.assertEqual(" ".join(r[0] for r in labels),key)
        self.assertEqual(" ".join(r[0] for r in vals),value)
        for text,x,y,font,size in labels:
            for v,vx,vy,vf,vs in vals:
                if abs(y-vy)<1:self.assertLess(x+stringWidth(text,font,size),vx)
        next_y=next(r[2] for r in body if r[0]=="NEXT")
        self.assertLess(next_y,min(r[2] for r in labels+vals))

    def test_oversize_url_keeps_every_character_inside_printable_width(self):
        d=pdf._Doc("url");d.new_page()
        url="https://publications.aap.org/pediatrics/article/150/1/e2022057991/188305/Evidence-Base-for-2022-Updated-Recommendations-for"
        lines=pdf._wrap(d.c,url,"Helvetica",9,pdf.PAGE_W-2*pdf.MARGIN)
        self.assertEqual("".join(lines),url);self.assertGreater(len(lines),1)
        d.para(url,size=9);runs=[]
        def visit(text,cm,tm,font,size):
            if text.strip() and not text.startswith("page "):runs.append((text.strip(),tm[4],size))
        PdfReader(io.BytesIO(d.finish())).pages[0].extract_text(visitor_text=visit)
        self.assertEqual("".join(r[0] for r in runs),url)
        for text,x,size in runs:self.assertLessEqual(x+stringWidth(text,"Helvetica",size),pdf.PAGE_W-pdf.MARGIN+.01)

    def test_impossible_chart_floor_is_structured_refusal_not_exception(self):
        cir=for_slug("cloudline-baby-blanket");twin=build_twin(cir,compile_cir(cir))
        with patch.object(pdf,"CHART_MIN_CELL_MM",50.0):art=pdf._chart_art(cir,twin)
        self.assertTrue(any(p.startswith("PDF_CHART_CELL_BELOW_BRAND_MINIMUM") for p in art["problems"]))
        self.assertIn("mm on the page",art["problems"][0]);self.assertNotIn("tiles",art)

if __name__=="__main__":
    # One line per test, starting OK or FAIL, which is what the suite harness counts.
    failed=0
    for name in unittest.defaultTestLoader.getTestCaseNames(LayoutBounds):
        result=unittest.TestResult()
        LayoutBounds(name).run(result)
        problems=result.failures+result.errors
        if problems or not result.wasSuccessful():
            failed+=1
            print(f"FAIL {name} {problems[0][1].strip().splitlines()[-1] if problems else ''}")
        else:
            print(f"OK   {name}")
    sys.exit(1 if failed else 0)
