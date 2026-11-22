"""Облегчённая модель AMR24 для страницы (three.js): web/tools/amr24_web.glb.

Те же части для разбора, что в видео (car_setup.py). В узлах записаны параметры разлёта (extras):
  part_<имя>: dir (оси Blender: x вперёд, y влево, z вверх), dist, spread, wheel
  детали:      rel (смещение центра детали от центра части, оси Blender), layer (слой колеса)
Облегчение: сетки крупнее LIMIT треугольников упрощаются (Decimate), текстуры ужимаются до TEX px;
затем tools/glb_webp.py пересжимает картинки в WebP (экспортёр Blender не пишет одноканальные WebP).
Запуск: python tools/export_web_glb.py [--ratio 0.2] [--tex 1024] [--limit 800]
"""
import argparse
import os
import sys

import bpy  # первым
import addon_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_setup

ap = argparse.ArgumentParser()
ap.add_argument('--ratio', type=float, default=0.2)
ap.add_argument('--tex', type=int, default=1024)
ap.add_argument('--limit', type=int, default=800)
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, '..', 'web', 'tools', 'amr24_web.glb')

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable('io_scene_gltf2', default_set=True)
root, parts = car_setup.import_car(os.path.join(here, '..', 'model', 'amr24.glb'))
car_setup.fix_materials(root.children_recursive)

layer_of = {'TYRE_': 0, 'wheel_': 1, 'disc_': 2, 'tether_': 3}
tris0 = tris1 = 0
for name, info in parts.items():
    h = info['holder']
    h['dir'] = list(info['dir']); h['dist'] = info['dist']; h['spread'] = info['spread']; h['wheel'] = name.startswith('wheel')
    for o, rel in info['members']:
        o['rel'] = list(rel)
        o['layer'] = next((v for k, v in layer_of.items() if o.name.startswith(k)), 1)
        n = sum(len(p.vertices) - 2 for p in o.data.polygons)
        tris0 += n
        if n > args.limit:
            m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = args.ratio
            bpy.context.view_layer.objects.active = o
            with bpy.context.temp_override(object=o, active_object=o):
                bpy.ops.object.modifier_apply(modifier=m.name)
        tris1 += sum(len(p.vertices) - 2 for p in o.data.polygons)
print(f'треугольников: {tris0} → {tris1}')

for im in bpy.data.images:
    if im.size[0] > args.tex:
        im.scale(args.tex, max(1, round(im.size[1] * args.tex / im.size[0])))

bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False, export_extras=True,
                          export_image_format='AUTO',  # в WebP пересжимает tools/glb_webp.py

                          export_apply=True, export_animations=False, export_cameras=False, export_lights=False)
print('готово:', out, f'{os.path.getsize(out) / 1024 / 1024:.1f} МБ')
