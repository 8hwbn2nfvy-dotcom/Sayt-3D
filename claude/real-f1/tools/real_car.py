"""Замена Лего-машинки на модель AMR24 в сцене Лего-ролика (вызывается из lego-f1/web/tools/blender_render.py --car-module).

Сцена (трасса, коробка, камера) и таймлайн — те же, что у страницы Лего-ролика.
Из timeline.json берутся по кадрам: разобранность (explode 0…1), угол колёс, положение и поворот машины.
Разлёт частей, покачивание и вращение — те же правила, что у Лего-машинки (index.src.html: poseAt).
"""
import math
import os
import random

import bpy
import mathutils

import car_setup

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'model', 'amr24.glb')
LIFT = 2.2      # на сколько вся разобранная машина поднимается над землёй (как у Лего)
JITTER = 0.9    # разброс деталей внутри части при разборе


def _bake(obj, path, size, rows, frame0):
    """Записывает по ключу на каждый кадр: rows[i] — значение (len = size) на кадре frame0 + i."""
    if obj.animation_data is None:
        obj.animation_data_create()
    act = obj.animation_data.action
    if act is None:
        act = bpy.data.actions.new(obj.name + '_anim')
        obj.animation_data.action = act
    n = len(rows)
    for k in range(size):
        fc = act.fcurve_ensure_for_datablock(obj, path, index=k)
        fc.keyframe_points.add(n)
        co = []
        for i, r in enumerate(rows):
            co += [frame0 + i, r[k]]
        fc.keyframe_points.foreach_set('co', co)
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()


def install(sc, tl, frame0):
    # 1. убираем Лего-машинку (узел car и всё под ним)
    lego = bpy.data.objects.get('car')
    if lego:
        for o in list(lego.children_recursive) + [lego]:
            bpy.data.objects.remove(o, do_unlink=True)
    # 2. ставим AMR24
    root, parts = car_setup.import_car(MODEL)
    car_setup.fix_materials(root.children_recursive)
    for o in root.children_recursive:
        if o.type == 'MESH':
            o.visible_shadow = True

    N = tl['frames']
    fps = tl['fps']
    E, W, P = tl['explode'], tl['wheel'], tl['carPose']
    # машина целиком: координаты страницы (x, y вверх, z) → Blender (x, -z, y); поворот вокруг вертикали тот же
    _bake(root, 'location', 3, [(p[0], -p[2], p[1]) for p in P], frame0)
    _bake(root, 'rotation_euler', 3, [(0, 0, p[3]) for p in P], frame0)

    rnd = random.Random(77245)
    for name, info in parts.items():
        holder, spin = info['holder'], info['spin']
        axis = mathutils.Vector((rnd.random() - 0.5, rnd.random() - 0.5, rnd.random() - 0.5)).normalized()
        amp = 0.35 if name.startswith('wheel') else 0.22 + rnd.random() * 0.12
        phase = rnd.random() * math.pi * 2
        locs, rots = [], []
        for i in range(N):
            t, e = i / fps, E[i]
            bob = math.sin(t * 1.9 + phase) * 0.35 * e
            p = info['center'] + info['dir'] * info['dist'] * e + mathutils.Vector((0, 0, LIFT * e + bob))
            wob = e * amp * (0.75 + 0.25 * math.sin(t * 1.3 + phase))
            locs.append(tuple(p))
            rots.append(tuple(mathutils.Quaternion(axis, wob).to_euler()))
        holder.rotation_mode = 'XYZ'
        _bake(holder, 'location', 3, locs, frame0)
        _bake(holder, 'rotation_euler', 3, rots, frame0)
        if name.startswith('wheel'):
            # колесо катится вперёд (+X) — поворот вокруг оси Y со знаком «+»; у страницы знак обратный (ось Z three.js)
            _bake(spin, 'rotation_euler', 3, [(0, -W[i], 0) for i in range(N)], frame0)
            side = 1 if info['center'].y > 0 else -1
            order = {'TYRE_': 0, 'wheel_': 1, 'disc_': 2, 'tether_': 3}
            for o, rel in info['members']:
                layer = next((v for k, v in order.items() if o.name.startswith(k)), 1)
                _bake(o, 'location', 3, [(0, side * (layer - 1.2) * 0.9 * E[i], 0) for i in range(N)], frame0)
        else:
            for o, rel in info['members']:
                j = mathutils.Vector((rnd.random() - 0.5, rnd.random() - 0.5, rnd.random() - 0.5))
                rows = [tuple(rel * info['spread'] * E[i] + j * JITTER * E[i]) for i in range(N)]
                _bake(o, 'location', 3, rows, frame0)
    print('AMR24 установлена, частей:', len(parts))
    return root
