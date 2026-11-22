"""Рендер video.mp4 в Blender Cycles (трассировка лучей) из сцены, выгруженной страницей.

Шаги:
  1. node tools/export_gltf.mjs ../blender_build      → scene.glb + timeline.json (тот же таймлайн, что у страницы)
  2. python tools/blender_render.py ../blender_build [--frames 0,270] [--samples 64] [--scale 100]
     → ../blender_build/frames/0000.png …, затем ffmpeg собирает web/video.mp4 (только при полном рендере)
Нужен Python-модуль bpy (Blender как библиотека): pip install bpy==5.3.0 (Python 3.13).

Один источник света: большой мягкий «софтбокс» над сценой. Остальное — материалы:
пластик Лего с лёгким лаком и скруглёнными (на рендере) рёбрами, резина шин, шершавый асфальт, картон коробки.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time

import bpy  # первым: он добавляет в путь модули Blender (addon_utils и др.)
import addon_utils
import mathutils

ap = argparse.ArgumentParser()
ap.add_argument('build')
ap.add_argument('--frames', default='')          # «0,270,390» — только эти кадры (проба)
ap.add_argument('--samples', type=int, default=32)
ap.add_argument('--scale', type=int, default=100)  # % от 1920×1080
ap.add_argument('--video', default='')            # куда собрать mp4 после полного рендера
ap.add_argument('--car-module', default='')       # путь к модулю с install(sc, tl, frame0): заменить Лего-машинку другой моделью
ap.add_argument('--frames-dir', default='frames')  # папка кадров внутри build
ap.add_argument('--key-follow', action='store_true')  # во время езды софтбокс светит со стороны камеры
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])

build = os.path.abspath(args.build)
tl = json.load(open(os.path.join(build, 'timeline.json')))
FPS, N = tl['fps'], tl['frames']

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable('io_scene_gltf2', default_set=True)
sc = bpy.context.scene
sc.render.fps = FPS
bpy.ops.import_scene.gltf(filepath=os.path.join(build, 'scene.glb'))

# --- время: находим, с какого кадра importer поставил ключи ---
def all_fcurves():
    for a in bpy.data.actions:
        # в Blender 5 F-кривые лежат в слоях/полосах действия
        if hasattr(a, 'layers') and a.layers:
            for layer in a.layers:
                for strip in layer.strips:
                    for cb in strip.channelbags:
                        yield from cb.fcurves
        elif hasattr(a, 'fcurves'):
            yield from a.fcurves


keys = [kp.co.x for fc in all_fcurves() for kp in fc.keyframe_points]
k0, k1 = min(keys), max(keys)
print(f'ключи анимации: кадры {k0:.1f}…{k1:.1f}')
sc.frame_start = round(k0)
sc.frame_end = round(k0) + N - 1
for fc in all_fcurves():
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'

# --- другая машина вместо Лего (claude/real-f1/tools/real_car.py) ---
if args.car_module:
    sys.path.insert(0, os.path.dirname(os.path.abspath(args.car_module)))
    import importlib
    importlib.import_module(os.path.splitext(os.path.basename(args.car_module))[0]).install(sc, tl, sc.frame_start)

# --- камера ---
cam = next(o for o in sc.objects if o.type == 'CAMERA')
sc.camera = cam
cam.data.clip_start, cam.data.clip_end = 0.3, 1000
cam.data.sensor_fit = 'VERTICAL'
cam.data.angle_y = math.radians(tl['camera']['fov'])

# --- материалы ---
def principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def setv(bsdf, name, v):
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = v


def add_bevel(mat, radius):
    nt = mat.node_tree
    bsdf = principled(mat)
    if bsdf.inputs['Normal'].is_linked:
        return
    bev = nt.nodes.new('ShaderNodeBevel')
    bev.inputs['Radius'].default_value = radius
    bev.samples = 4
    nt.links.new(bev.outputs['Normal'], bsdf.inputs['Normal'])


def asphalt(mat):
    nt = mat.node_tree
    bsdf = principled(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    noise = nt.nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 1.6; noise.inputs['Detail'].default_value = 12
    nt.links.new(tc.outputs['Object'], noise.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (0.012, 0.0125, 0.014, 1)
    ramp.color_ramp.elements[1].color = (0.026, 0.027, 0.030, 1)
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    grain = nt.nodes.new('ShaderNodeTexNoise'); grain.inputs['Scale'].default_value = 40; grain.inputs['Detail'].default_value = 8
    nt.links.new(tc.outputs['Object'], grain.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.25; bump.inputs['Distance'].default_value = 0.02
    nt.links.new(grain.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    setv(bsdf, 'Roughness', 0.85)


done = set()
for ob in sc.objects:
    if ob.type != 'MESH':
        continue
    name = ob.name
    for slot in ob.material_slots:
        mat = slot.material
        if not mat or mat.name in done:
            continue
        done.add(mat.name)
        bsdf = principled(mat)
        if not bsdf:
            continue
        rough = bsdf.inputs['Roughness'].default_value
        if name.startswith('blk_'):
            if rough >= 0.7:                       # шины
                setv(bsdf, 'Roughness', 0.62)
                setv(bsdf, 'Specular IOR Level', 0.35)
            else:                                   # пластик Лего (и наклейки на нём)
                setv(bsdf, 'Roughness', 0.22)
                setv(bsdf, 'Coat Weight', 0.35)
                setv(bsdf, 'Coat Roughness', 0.06)
                add_bevel(mat, 0.035)
        elif name == 'road':
            asphalt(mat)
        elif name == 'ground':
            setv(bsdf, 'Roughness', 0.95)
            bsdf.inputs['Base Color'].default_value = (0.004, 0.0045, 0.005, 1)
        elif name.startswith('kerbs') or name == 'line':
            setv(bsdf, 'Roughness', 0.55)
            add_bevel(mat, 0.05)
        elif name.startswith('box'):
            setv(bsdf, 'Roughness', 0.42)
            setv(bsdf, 'Coat Weight', 0.15)        # глянцевая печать на картоне
            add_bevel(mat, 0.08)

# --- коробка: прозрачность по кадрам (проявление с 11-й секунды) ---
box = bpy.data.objects.get('box_mesh')
alpha = tl['boxAlpha']
for slot in box.material_slots:
    mat = slot.material
    bsdf = principled(mat)
    inp = bsdf.inputs['Alpha']
    if inp.is_linked:
        for l in list(inp.links):
            mat.node_tree.links.remove(l)
    for i, a in enumerate(alpha):
        if i == 0 or i == N - 1 or abs(a - alpha[i - 1]) > 1e-4 or abs(a - alpha[min(N - 1, i + 1)]) > 1e-4:
            inp.default_value = a
            inp.keyframe_insert('default_value', frame=sc.frame_start + i)
box.visible_shadow = True

# --- свет: один большой мягкий софтбокс над сценой ---
ko = tl['keyOffset']                               # смещение света в координатах страницы (Y вверх)
center = (0.0, 13.0, 0.0)                          # середина между машинкой и коробкой (Blender: Z вверх)
light_data = bpy.data.lights.new('softbox', 'AREA')
light_data.shape = 'RECTANGLE'
light_data.size, light_data.size_y = 34, 22
light_data.energy = 120000
light_data.color = (1.0, 0.97, 0.93)
light = bpy.data.objects.new('softbox', light_data)
sc.collection.objects.link(light)
light.location = (center[0] + ko[0], center[1] - ko[2], center[2] + ko[1])
d = [center[i] - light.location[i] for i in range(3)]
light.rotation_euler = (0, 0, 0)
light.rotation_euler = mathutils.Vector(d).to_track_quat('-Z', 'Y').to_euler()

# --- софтбокс во время езды (12–15 с): плавно уходит к камере и светит на машину спереди-сбоку от зрителя ---
if args.key_follow:
    base_loc, base_aim = light.location.copy(), mathutils.Vector(center)
    root = bpy.data.objects.get('car_root') or bpy.data.objects.get('car')
    locs, rots = [], []
    smooth = lambda x: (lambda c: c * c * (3 - 2 * c))(min(1, max(0, x)))
    for i in range(N):
        t = i / FPS
        k = smooth((t - 12) / 0.6) * (1 - smooth((t - 14.2) / 0.8))
        sc.frame_set(sc.frame_start + i)
        cam_p = cam.matrix_world.translation
        car_p = root.matrix_world.translation if root else base_aim
        loc = base_loc.lerp(cam_p + mathutils.Vector((0, 0, 22)), k)
        aim = base_aim.lerp(car_p + mathutils.Vector((0, 0, 2)), k)
        locs.append(loc.copy())
        rots.append((aim - loc).to_track_quat('-Z', 'Y').to_euler())
    for i in range(N):
        light.location = locs[i]; light.rotation_euler = rots[i]
        light.keyframe_insert('location', frame=sc.frame_start + i)
        light.keyframe_insert('rotation_euler', frame=sc.frame_start + i)

# --- мир: почти чёрный фон, чуть заметный отсвет для отражений ---
world = bpy.data.worlds.new('studio')
sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.010, 0.011, 0.013, 1)
bg.inputs['Strength'].default_value = 1.0

# --- рендер ---
r = sc.render
r.engine = 'CYCLES'
cy = sc.cycles
cy.device = 'CPU'
cy.samples = args.samples
cy.use_adaptive_sampling = True
cy.adaptive_threshold = 0.04
cy.use_denoising = True
cy.denoiser = 'OPENIMAGEDENOISE'
cy.max_bounces = 6
cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 2, 3, 1, 8
cy.blur_glossy = 0.5
r.use_motion_blur = True
r.motion_blur_shutter = 0.2
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, args.scale
r.image_settings.file_format = 'PNG'
r.image_settings.color_depth = '8'
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'
r.use_persistent_data = True

out = os.path.join(build, args.frames_dir)
os.makedirs(out, exist_ok=True)
frames = [int(x) for x in args.frames.split(',')] if args.frames else list(range(N))
t0 = time.time()
for i, f in enumerate(frames):
    r.filepath = os.path.join(out, f'{f:04d}.png')
    if not args.frames and os.path.exists(r.filepath):
        continue  # уже отрендерен (можно продолжить после обрыва)
    sc.frame_set(sc.frame_start + f)
    ts = time.time()
    bpy.ops.render.render(write_still=True)
    print(f'кадр {f} ({i + 1}/{len(frames)}) за {time.time() - ts:.1f} с, всего {(time.time() - t0) / 60:.1f} мин', flush=True)

if not args.frames and args.video:
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(out, '%04d.png'),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-r', str(FPS),
                    '-movflags', '+faststart', args.video], check=True)
    print('готово:', args.video)
