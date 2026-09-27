"""Blender diagnostic only. Geometry failures remain visible; no beauty qualification."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
HERE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument("--tag",required=True);a=ap.parse_args(sys.argv[sys.argv.index("--")+1:])
out=HERE/"out"/a.tag
m=json.loads((out/"geometry.json").read_text());data=np.load(out/"centerline.npz");p=data["points_mm"]
assert hashlib.sha256(p.tobytes()).hexdigest()==m["centerline_sha256"]
started=time.perf_counter()
bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
curve=bpy.data.curves.new("authoritative_dense_centerline","CURVE")
curve.dimensions="3D";curve.resolution_u=1;curve.bevel_depth=m["yarn_diameter_mm"]*.0005;curve.bevel_resolution=3;curve.use_fill_caps=True
s=curve.splines.new("POLY");s.points.add(len(p)-1);v=np.column_stack([p*.001,np.ones(len(p))]);s.points.foreach_set("co",v.ravel())
obj=bpy.data.objects.new("coupon_diagnostic",curve);bpy.context.collection.objects.link(obj)
mat=bpy.data.materials.new("neutral_diagnostic_no_photoreal_claim");mat.use_nodes=True
bs=mat.node_tree.nodes.get("Principled BSDF");bs.inputs["Base Color"].default_value=(.59,.64,.66,1);bs.inputs["Roughness"].default_value=.8
obj.data.materials.append(mat)
scene=bpy.context.scene;scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=32;scene.cycles.use_denoising=False;scene.cycles.seed=927
scene.render.threads_mode="FIXED";scene.render.threads=8;scene.render.resolution_x=1000;scene.render.resolution_y=1200;scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG";scene.render.image_settings.color_mode="RGBA";scene.render.film_transparent=True
scene.view_settings.view_transform="Standard";scene.view_settings.look="None"
world=bpy.data.worlds.new("diagnostic_world");scene.world=world;world.use_nodes=True
world.node_tree.nodes["Background"].inputs[0].default_value=(.16,.16,.16,1)
world.node_tree.nodes["Background"].inputs[1].default_value=.45
target=Vector((.025,.045,0))
bpy.ops.object.camera_add(location=(.025,.009,.19));cam=bpy.context.object;cam.rotation_euler=(target-cam.location).to_track_quat("-Z","Y").to_euler();cam.data.type="ORTHO";cam.data.ortho_scale=.115;scene.camera=cam
for i,(loc,power,size) in enumerate([((-.04,.02,.14),6,.12),((.10,.08,.08),3,.08)]):
    bpy.ops.object.light_add(type="AREA",location=loc);light=bpy.context.object;light.data.energy=power;light.data.shape="DISK";light.data.size=size;light.rotation_euler=(target-light.location).to_track_quat("-Z","Y").to_euler()
scene.render.filepath=str(out/"diagnostic.png");bpy.ops.render.render(write_still=True)
record={"tag":a.tag,"renderer":bpy.app.version_string,"centerline_sha256":m["centerline_sha256"],"seconds":round(time.perf_counter()-started,3),
        "diagnostic_png_sha256":hashlib.sha256((out/"diagnostic.png").read_bytes()).hexdigest(),
        "rendered_curve":"POLY over exactly measured dense centerline","diameter_mm":m["yarn_diameter_mm"],
        "material":"neutral diagnostic, no fibres, no product realism claim","spend_usd":0}
(out/"render.json").write_text(json.dumps(record,indent=2),encoding="utf-8",newline="\n")
print(json.dumps(record))
