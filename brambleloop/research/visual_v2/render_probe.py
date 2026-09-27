"""Blender 4.5 background renderer for the routing probe, no API calls.

Run: blender --background --factory-startup --python render_probe.py
Uses existing out/routing_probe.npz only. Schematic routes stay authoritative.
Render is a diagnostic of B/C feasibility; no stitch or realism certification.
"""
import hashlib
import json
import time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
start = time.perf_counter()
data = np.load(OUT / "routing_probe.npz")
points = data["points_mm"]
geom_before = hashlib.sha256(points.tobytes()).hexdigest()
meta = json.loads((OUT / "geometry_manifest.json").read_text())
assert geom_before == meta["points_array_sha256"]
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

mat = bpy.data.materials.new("cream_acrylic_UNCALIBRATED")
mat.use_nodes = True
nodes, links = mat.node_tree.nodes, mat.node_tree.links
bsdf = nodes.get('Principled BSDF')
rgb = np.array([250, 246, 235])/255
linear = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
bsdf.inputs['Base Color'].default_value = (*linear, 1)
bsdf.inputs['Roughness'].default_value = .82
bsdf.inputs['Sheen Weight'].default_value = .32
# Deterministic procedural micro-bump; explicitly NOT a calibrated fibre model.
tex = nodes.new('ShaderNodeTexNoise')
tex.inputs['Scale'].default_value = 1800
tex.inputs['Detail'].default_value = 2
bump = nodes.new('ShaderNodeBump')
bump.inputs['Strength'].default_value = .18
bump.inputs['Distance'].default_value = .00009
links.new(tex.outputs['Fac'], bump.inputs['Height'])
links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
curve = bpy.data.curves.new("all_17424_cell_carriers", 'CURVE')
curve.dimensions = '3D'
curve.resolution_u = 1
curve.bevel_depth = .00085
curve.bevel_resolution = 2
curve.use_fill_caps = True
for pts in points:
    spl = curve.splines.new('POLY')
    spl.points.add(len(pts)-1)
    v = np.c_[pts/1000, np.ones(len(pts))].ravel()
    spl.points.foreach_set('co', v)
obj = bpy.data.objects.new("product_routing_probe_NOT_certified_yarn", curve)
bpy.context.collection.objects.link(obj)
obj.data.materials.append(mat)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'  # portable baseline; do not silently require a GPU
scene.cycles.samples = 32
scene.cycles.seed = 271828
scene.cycles.use_denoising = False  # no image-domain denoiser moving microstructure
scene.render.threads_mode = 'FIXED'
scene.render.threads = 8
scene.render.resolution_x = 1024
scene.render.resolution_y = 1536
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
scene.view_settings.view_transform = 'Standard'
scene.world.color = (.12,.12,.12)

def light(name, location, energy, size):
    ld = bpy.data.lights.new(name,'AREA'); ld.energy=energy; ld.shape='DISK'; ld.size=size
    lo = bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(lo); lo.location=location
    lo.rotation_euler = (Vector((.45,.644,0))-lo.location).to_track_quat('-Z','Y').to_euler()
light('window_left',(-.6,.9,1.5),190,1.2)
light('soft_fill',(.8,.1,1.8),50,1.5)
camera = bpy.data.cameras.new('fixed_orthographic')
co = bpy.data.objects.new('fixed_orthographic',camera); bpy.context.collection.objects.link(co)
co.location=(.45,meta['dimensions_mm'][1]/2000,2)
camera.type='ORTHO'; camera.ortho_scale=1.5
camera.lens=50
scene.camera=co

# Same geometry / camera for all passes. The normal/depth EXR is retained locally;
# hashes and the exact camera are durable, lightweight PNGs provided for review.
layer = scene.view_layers[0]
layer.use_pass_z=True; layer.use_pass_normal=True; layer.use_pass_diffuse_color=True
scene.use_nodes=True
nodes=scene.node_tree.nodes; links=scene.node_tree.links; nodes.clear()
rl=nodes.new('CompositorNodeRLayers'); composite=nodes.new('CompositorNodeComposite')
links.new(rl.outputs['Image'],composite.inputs['Image'])
file=nodes.new('CompositorNodeOutputFile'); file.base_path=str(OUT/'passes_')
file.format.file_format='OPEN_EXR_MULTILAYER'; file.format.color_depth='32'; file.file_slots.clear()
for name, output in [('Beauty','Image'),('Depth','Depth'),('Normal','Normal'),('Albedo','DiffCol')]:
    file.file_slots.new(name); links.new(rl.outputs[output],file.inputs[name])
png=nodes.new('CompositorNodeOutputFile'); png.base_path=str(OUT)
png.format.file_format='PNG'; png.format.color_mode='RGB'; png.format.color_depth='16'; png.file_slots.clear()
scale=nodes.new('CompositorNodeMixRGB'); scale.blend_type='MULTIPLY'; scale.inputs[0].default_value=1; scale.inputs[2].default_value=(.5,.5,.5,1)
offset=nodes.new('CompositorNodeMixRGB'); offset.blend_type='ADD'; offset.inputs[0].default_value=1; offset.inputs[2].default_value=(.5,.5,.5,1)
links.new(rl.outputs['Normal'],scale.inputs[1]); links.new(scale.outputs[0],offset.inputs[1])
depth=nodes.new('CompositorNodeMath'); depth.operation='SUBTRACT'; depth.inputs[0].default_value=2
links.new(rl.outputs['Depth'],depth.inputs[1])
gain=nodes.new('CompositorNodeMath'); gain.operation='MULTIPLY'; gain.inputs[1].default_value=125; gain.use_clamp=True
links.new(depth.outputs[0],gain.inputs[0])
for name,output in [('normal_preview_',offset.outputs[0]),('height_preview_',gain.outputs[0]),('albedo_',rl.outputs['DiffCol'])]:
    png.file_slots.new(name);links.new(output,png.inputs[name])
scene.render.filepath=str(OUT/'product_probe.png')
bpy.ops.render.render(write_still=True)
render_seconds=time.perf_counter()-start
# Save portable scene locally (excluded from git because regeneration is scripted).
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'routing_probe.blend'))
record={
    'renderer':'Blender '+bpy.app.version_string, 'engine':'Cycles CPU', 'samples':32, 'denoising':False,
    'render_seconds_including_setup':round(render_seconds,3), 'resolution':[1024,1536],
    'camera':{'position_m':list(co.location),'type':'ORTHO','scale_m':1.5,'rotation_radians':list(co.rotation_euler)},
    'points_array_sha256_before':geom_before,'points_array_sha256_after':hashlib.sha256(points.tobytes()).hexdigest(),
    'render_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'product_png_sha256':hashlib.sha256((OUT/'product_probe.png').read_bytes()).hexdigest(),
    'geometry_carriers':len(curve.splines), 'path_points':int(np.prod(points.shape[:2])),
    'material':'one frozen cream colour; roughness/sheen/noise parameters are uncalibrated presentation choices',
    'pass_note':'Raw world normals, camera depth in metres and diffuse albedo in passes_0001.exr; PNG previews are display-transformed and are not calibrated normal/depth data',
    'photographic_judge':'UNKNOWN - no paid call; schematic disconnected carriers are not certified stitch topology',
    'spend_usd':0,
}
(OUT/'render_record.json').write_text(json.dumps(record,indent=2), encoding="utf-8", newline="\n")
print(json.dumps(record,indent=2))
