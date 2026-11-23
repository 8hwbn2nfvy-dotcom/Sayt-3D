"""Библиотека моделей окружения из Poly Haven (CC0) → assets/lib.blend.

Каждая модель — своя коллекция (имя = id модели), её начало координат — в основании модели (z = 0), длина в метрах.
Слишком тяжёлые модели упрощаются (Decimate) до TARGET треугольников (деревья в оригинале 1–3 млн).
Запуск: python tools/build_assets.py   (Python с bpy)
"""
import glob
import os

import bpy  # первым
import addon_utils
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, '..', 'assets')
TARGET = {'island_tree_01': 400_000, 'island_tree_02': 400_000, 'tree_small_02': 400_000, 'shrub_01': 40_000, 'concrete_road_barrier': 6_000,
          'modular_chainlink_fence': 30_000}

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable('io_scene_gltf2', default_set=True)
sc = bpy.context.scene
for f in sorted(glob.glob(os.path.join(A, 'models', '*', '*_1k.gltf'))):
    mid = os.path.basename(os.path.dirname(f))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    for o in meshes:
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
        if o.data.users > 1:
            o.data = o.data.copy()
        o.data.transform(o.matrix_world); o.matrix_world = mathutils.Matrix.Identity(4)
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    if mid in TARGET and tris > TARGET[mid]:
        ratio = TARGET[mid] / tris
        for o in meshes:
            m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = ratio
            with bpy.context.temp_override(object=o, active_object=o):
                bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.update()
    zmin = min((o.matrix_world @ mathutils.Vector(c)).z for o in meshes for c in o.bound_box)
    for o in meshes:
        o.data.transform(mathutils.Matrix.Translation((0, 0, -zmin)))
    col = bpy.data.collections.new(mid)
    sc.collection.children.link(col)
    for o in meshes:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
    t2 = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    print(f'{mid:28s} треугольников {tris:>9d} → {t2:>9d}', flush=True)

for im in bpy.data.images:
    im.pack()
out = os.path.join(A, 'lib.blend')
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
print('готово:', out, f'{os.path.getsize(out) / 2**20:.0f} МБ')
