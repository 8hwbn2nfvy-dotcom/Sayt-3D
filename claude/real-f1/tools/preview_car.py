"""Пробный кадр: одна машина AMR24 в студии (проверка масштаба, частей и материалов)."""
import os, sys, math
import bpy, addon_utils, mathutils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_setup

out = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable('io_scene_gltf2', default_set=True)
root, parts = car_setup.import_car(os.path.join(os.path.dirname(__file__), '..', 'model', 'amr24.glb'))
car_setup.fix_materials(root.children_recursive)
sc = bpy.context.scene
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (26, -30, 12); cam.data.lens = 50
cam.rotation_euler = (mathutils.Vector((0, 0, 2.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
L = bpy.data.lights.new('sb', 'AREA'); L.size = 30; L.energy = 90000
lo = bpy.data.objects.new('sb', L); sc.collection.objects.link(lo); lo.location = (8, -14, 40)
lo.rotation_euler = (mathutils.Vector((0, 0, 0)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=400)
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.02, 0.022, 0.025, 1)
sc.render.engine = 'CYCLES'; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.view_settings.view_transform = 'AgX'
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
