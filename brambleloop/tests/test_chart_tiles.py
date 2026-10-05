"""Full-fabric coverage and unchanged readability floors; local render checks."""
import sys,unittest,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from brambleloop.products.builder import for_slug
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.publish import pdf,charts

class ChartTiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cir=for_slug("cloudline-baby-blanket");cls.fingerprint=cls.cir.fingerprint
        cls.twin=build_twin(cls.cir,compile_cir(cls.cir));cls.art=pdf._chart_art(cls.cir,cls.twin)

    def test_every_stitch_and_colour_once_including_all_border_rows(self):
        grid,colors=self.twin.chart_grid(),self.twin.color_grid();got={}
        for t in self.art["tiles"]:
            for ri,row in enumerate(t["grids"][0],t["row_start"]-1):
                for ci,st in enumerate(row,t["column_start"]-1):
                    self.assertNotIn((ri,ci),got)
                    got[ri,ci]=(st,t["grids"][1][ri-t["row_start"]+1][ci-t["column_start"]+1])
        self.assertEqual(got,{(r,c):(st,colors[r][c]) for r,row in enumerate(grid) for c,st in enumerate(row)})
        self.assertEqual(self.cir.fingerprint,self.fingerprint)
        self.assertEqual(len(got),6930)

    def test_every_tile_meets_existing_floor_in_reserved_image_area(self):
        self.assertFalse(self.art["problems"])
        for tile in self.art["tiles"]:
            image=tile["chart"]
            scale=min(1,(pdf.PAGE_W-2*pdf.MARGIN)/image.width,pdf.CHART_TILE_HEIGHT/image.height)
            self.assertGreaterEqual(min(charts.flat_type_px(32).values())*scale,pdf.MIN_BODY_PT)
            self.assertGreaterEqual(tile["cell_mm"],pdf.CHART_MIN_CELL_MM)
            self.assertLessEqual(image.height*scale,pdf.CHART_TILE_HEIGHT+1e-8)

    def test_legend_footer_is_wrapped_inside_its_actual_image(self):
        bounds=[];original=charts.ImageDraw.Draw
        def draw(image):
            d=original(image);old=d.text
            def text(xy,value,*a,**kw):
                box=d.textbbox(xy,value,font=kw.get("font"),anchor=kw.get("anchor"))
                bounds.append((box,image.size));return old(xy,value,*a,**kw)
            d.text=text;return d
        with patch.object(charts.ImageDraw,"Draw",side_effect=draw):
            charts.render_legend(self.cir,self.twin)
        assert bounds, 'the legend drew no text, so nothing was checked'
        for (x0,y0,x1,y1),(w,h) in bounds:
            self.assertGreaterEqual(x0,0);self.assertGreaterEqual(y0,0)
            self.assertLessEqual(x1,w);self.assertLessEqual(y1,h)

    def test_global_row_parity_and_columns_do_not_restart_on_tile(self):
        calls=[];original=charts.ImageDraw.Draw
        def draw(image):
            d=original(image);old=d.text
            def text(xy,value,*a,**kw):calls.append((xy,str(value),kw));return old(xy,value,*a,**kw)
            d.text=text;return d
        with patch.object(charts.ImageDraw,"Draw",side_effect=draw):
            charts.render_chart(self.cir,self.twin,charts.ChartSpec(cell_px=32),
                grids=([["sc","sc"],["sc","sc"]],[["cream","cream"],["cream","cream"]]),
                row_offset=41,column_offset=97,show_columns=True,caption="Tile")
        even=next(c for c in calls if c[1]=="42")
        odd=next(c for c in calls if c[1]=="43")
        self.assertEqual(even[2]["anchor"],"rm")
        self.assertEqual(odd[2]["anchor"],"lm")
        self.assertLess(even[0][0],odd[0][0])
        self.assertTrue({"98","99"}.issubset({c[1] for c in calls}))

if __name__=="__main__":unittest.main()
