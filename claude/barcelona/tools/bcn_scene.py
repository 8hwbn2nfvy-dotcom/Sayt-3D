"""Ролик: AMR24 на трассе Барселона-Каталония. Сцена, анимация и рендер в Blender Cycles.

Таймлайн (секунды):
  0–2      машина стоит на старте, камера сзади-сбоку, впереди стартовые огни
  2,3,4,5,6 загораются 5 красных огней; с первым огнём машина разбирается (как в Лего-ролике)
  5.4–6.4  машина собирается
  7        огни гаснут — старт; дальше один полный круг с места по модели скорости (track_build.py)
  финиш +3 машина сбрасывает скорость, ролик кончается
Единицы — метры; x восток, y север, z вверх.
Запуск: python tools/bcn_scene.py [--frames 0,300] [--samples 16] [--scale 100]  → build/frames/NNNN.png
затем:  python3 tools/overlay.py  → табло секторов поверх кадров и web/video.mp4
"""
import argparse
import json
import math
import os
import sys
import time

import bpy  # первым
import addon_utils
import mathutils
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, '..', 'real-f1', 'tools'))
import car_setup  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--frames', default='')
ap.add_argument('--samples', type=int, default=12)
ap.add_argument('--scale', type=int, default=100)
ap.add_argument('--save-blend', default='')
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])

FPS = 30
T_LIGHTS = [2.0, 3.0, 4.0, 5.0, 6.0]
T_GO = 7.0
T_FLY, T_ASM0, T_ASM1 = 1.2, 5.4, 6.4     # разбор: разлёт 1.2 с; сборка 5.4–6.4 с
AFTER = 3.0
ROAD_W = 12.5                              # ширина трассы, м
KERB_W = 1.4
CAR_BACK = 2.9                             # центр машины позади линии старта (нос ≈ на линии)
CAR_SCALE = 5.61 / 28.0                    # разлёт частей задан для Лего-масштаба (28 единиц) → метры
HDRI_ROT = 0.0
COAT = 0.5                                 # лак краски                             # поворот панорамы неба вокруг вертикали, градусы

T = np.load(os.path.join(ROOT, 'build', 'track.npz'))
P2, Z, KAPPA, TCUM, DS, L = T['pts'], T['z'], T['kappa'], T['tcum'], float(T['ds']), float(T['L'])
NPT = len(P2)
P3 = np.column_stack([P2, Z])
LAP = float(T['lap'])
N = int(round((T_GO + LAP + AFTER) * FPS))
INFO = {'fps': FPS, 'frames': N, 't_go': T_GO, 'lap': LAP, 'sectors': T['sectors'].tolist(), 't_lights': T_LIGHTS}
json.dump(INFO, open(os.path.join(ROOT, 'build', 'timeline.json'), 'w'))


# ---------- путь ----------
def smooth_closed(a, sigma):
    """Гауссово сглаживание по кругу (БПФ), sigma — в точках трассы."""
    k = np.fft.fftfreq(len(a)); f = np.exp(-2 * (math.pi * k * sigma) ** 2)
    if a.ndim == 1:
        return np.real(np.fft.ifft(np.fft.fft(a) * f))
    return np.stack([np.real(np.fft.ifft(np.fft.fft(a[:, i]) * f)) for i in range(a.shape[1])], axis=1)


# Направление трассы: центральная разность, сглаженная (σ = 6 м), затем курс и уклон как плавные функции пути.
# Раньше направление бралось по ближайшей точке без интерполяции — на поворотах машина дёргалась ступеньками.
_TAN = smooth_closed((np.roll(P3, -1, 0) - np.roll(P3, 1, 0)) / (2 * DS), 6)
HEAD = np.unwrap(np.arctan2(_TAN[:, 1], _TAN[:, 0]))
SLOPE = np.arctan2(_TAN[:, 2], np.hypot(_TAN[:, 0], _TAN[:, 1]))
HEAD_TURN = HEAD[-1] + (HEAD[1] - HEAD[0]) - HEAD[0]          # полный оборот курса за круг (±2π)


def frame_at(s):
    """Плавные курс (рад, без скачков между кругами) и уклон дороги на расстоянии s."""
    f = s / DS
    lap = math.floor(f / NPT); f -= lap * NPT
    i = int(f); a = f - i; j = (i + 1) % NPT
    hj = HEAD[j] + (HEAD_TURN if j == 0 else 0.0)
    return HEAD[i] * (1 - a) + hj * a + lap * HEAD_TURN, SLOPE[i] * (1 - a) + SLOPE[j] * a


def at(s):
    """Точка, направление (единичное, 3D), нормаль влево (2D) и кривизна на расстоянии s по трассе (по кругу)."""
    f = (s / DS) % NPT
    i = int(f); a = f - i; j = (i + 1) % NPT
    p = P3[i] * (1 - a) + P3[j] * a
    h, sl = frame_at(s)
    d = np.array([math.cos(h) * math.cos(sl), math.sin(h) * math.cos(sl), math.sin(sl)])
    left = np.array([-math.sin(h), math.cos(h), 0.0])
    return p, d, left, KAPPA[i] * (1 - a) + KAPPA[j] * a


def smooth_time(a, sigma):
    """Сглаживание по кадрам без запаздывания (гаусс, края — повтор крайних значений)."""
    a = np.asarray(a, float)
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    pad = np.concatenate([np.repeat(a[:1], r, 0), a, np.repeat(a[-1:], r, 0)])
    if a.ndim == 1:
        return np.convolve(pad, k, 'valid')
    return np.stack([np.convolve(pad[:, i], k, 'valid') for i in range(a.shape[1])], axis=1)


def dist_at(t):
    """Пройденное расстояние от линии старта (может быть < 0 до старта и > L после финиша)."""
    if t < T_GO:
        return -CAR_BACK
    u = t - T_GO
    if u <= LAP:
        return -CAR_BACK + float(np.interp(u, TCUM, np.arange(len(TCUM)) * DS))
    v_end = DS / (TCUM[-1] - TCUM[-2])   # скорость на линии финиша
    w = u - LAP
    dec = 9.0
    tt = min(w, v_end / dec)
    return -CAR_BACK + L + v_end * tt - dec * tt * tt / 2


def smooth(x):
    x = min(1, max(0, x)); return x * x * (3 - 2 * x)


def ease_out(x):
    x = min(1, max(0, x)); return 1 - (1 - x) ** 3


def explode(t):
    t0 = T_LIGHTS[0]
    if t < t0:
        return 0.0
    if t < t0 + T_FLY:
        return ease_out((t - t0) / T_FLY)
    if t < T_ASM0:
        return 1.0
    return 1 - smooth((t - T_ASM0) / (T_ASM1 - T_ASM0))


# ---------- сцена ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable('io_scene_gltf2', default_set=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, N - 1
col = sc.collection


def mesh_obj(name, verts, faces, uvs=None, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    if uvs is not None:
        uv = me.uv_layers.new(name='UVMap')
        loop_uv = [uvs[vi] for poly in me.polygons for vi in poly.vertices]
        uv.data.foreach_set('uv', [c for u in loop_uv for c in u])
    for p in me.polygons:
        p.use_smooth = True
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    return ob


def ribbon(name, off0, off1, across, zlift, mat, mask=None, step=1):
    """Лента вдоль трассы между боковыми смещениями off0..off1 (м, + влево). UV: u поперёк 0..1, v — метры вдоль."""
    idx = [i for i in range(0, NPT, step) if mask is None or mask[i]]
    verts, uvs, faces = [], [], []
    seg_start = []
    prev = None
    for k, i in enumerate(idx):
        p, d, left, _ = at(i * DS)
        if prev is None or i - prev > step:
            seg_start.append(k)
        prev = i
        for a in range(across + 1):
            u = a / across
            off = off0 + (off1 - off0) * u
            q = p + left * off
            verts.append((q[0], q[1], q[2] + zlift))
            uvs.append((u, i * DS))
    starts = set(seg_start)
    closed = mask is None and step == 1
    m = len(idx)
    for k in range(m - (0 if closed else 1)):
        k2 = (k + 1) % m
        if k2 in starts and not (closed and k2 == 0):
            continue
        for a in range(across):
            v0 = k * (across + 1) + a; v1 = k2 * (across + 1) + a
            faces.append((v0, v1, v1 + 1, v0 + 1))
    return mesh_obj(name, verts, faces, uvs, mat)


def nodes_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes['Principled BSDF']


# асфальт: зерно, пятна, накатанная резина ближе к середине, белые линии по краям
asph, nt, b = nodes_mat('asphalt')
tc = nt.nodes.new('ShaderNodeTexCoord')
uvn = nt.nodes.new('ShaderNodeUVMap')
sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(uvn.outputs['UV'], sep.inputs[0])
big = nt.nodes.new('ShaderNodeTexNoise'); big.inputs['Scale'].default_value = 0.08; big.inputs['Detail'].default_value = 6
nt.links.new(tc.outputs['Object'], big.inputs['Vector'])
grain = nt.nodes.new('ShaderNodeTexVoronoi'); grain.inputs['Scale'].default_value = 90
nt.links.new(tc.outputs['Object'], grain.inputs['Vector'])
fine = nt.nodes.new('ShaderNodeTexNoise'); fine.inputs['Scale'].default_value = 260; fine.inputs['Detail'].default_value = 3
nt.links.new(tc.outputs['Object'], fine.inputs['Vector'])
ramp = nt.nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].color = (0.40, 0.40, 0.42, 1); ramp.color_ramp.elements[1].color = (0.75, 0.75, 0.76, 1)
mix_n = nt.nodes.new('ShaderNodeMath'); mix_n.operation = 'MULTIPLY_ADD'
nt.links.new(big.outputs['Fac'], mix_n.inputs[0]); mix_n.inputs[1].default_value = 0.9; mix_n.inputs[2].default_value = 0.0
add2 = nt.nodes.new('ShaderNodeMath'); add2.operation = 'MULTIPLY_ADD'
nt.links.new(fine.outputs['Fac'], add2.inputs[0]); add2.inputs[1].default_value = 0.4; nt.links.new(mix_n.outputs[0], add2.inputs[2])
nt.links.new(add2.outputs[0], ramp.inputs['Fac'])
# фототекстура асфальта (Poly Haven asphalt_02, плитка 3 м) поверх процедурной основы
amap = nt.nodes.new('ShaderNodeMapping'); amap.inputs['Scale'].default_value = (1 / 3, 1 / 3, 1 / 3)
nt.links.new(tc.outputs['Object'], amap.inputs['Vector'])
atex = {}
for key, colr in (('diff', True), ('nor', False), ('rough', False)):
    tn = nt.nodes.new('ShaderNodeTexImage')
    tdir = os.path.join(ROOT, 'assets', 'tex', 'asphalt_02')
    tn.image = bpy.data.images.load(os.path.join(tdir, next(x for x in os.listdir(tdir) if f'_{key}_' in x)))
    if not colr:
        tn.image.colorspace_settings.name = 'Non-Color'
    nt.links.new(amap.outputs['Vector'], tn.inputs['Vector']); atex[key] = tn
# резина: полоса u≈0.35..0.65 темнее
rub = nt.nodes.new('ShaderNodeMapRange'); rub.interpolation_type = 'SMOOTHSTEP'
dist = nt.nodes.new('ShaderNodeMath'); dist.operation = 'ABSOLUTE'
sub = nt.nodes.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'; sub.inputs[1].default_value = 0.5
nt.links.new(sep.outputs['X'], sub.inputs[0]); nt.links.new(sub.outputs[0], dist.inputs[0])
nt.links.new(dist.outputs[0], rub.inputs['Value']); rub.inputs['From Min'].default_value = 0.12; rub.inputs['From Max'].default_value = 0.28
rub.inputs['To Min'].default_value = 0.62; rub.inputs['To Max'].default_value = 1.0
dark = nt.nodes.new('ShaderNodeMix'); dark.data_type = 'RGBA'; dark.blend_type = 'MULTIPLY'; dark.inputs['Factor'].default_value = 1.0
aphoto = nt.nodes.new('ShaderNodeMix'); aphoto.data_type = 'RGBA'; aphoto.blend_type = 'MULTIPLY'; aphoto.inputs['Factor'].default_value = 1.0
nt.links.new(atex['diff'].outputs['Color'], aphoto.inputs['A']); nt.links.new(ramp.outputs['Color'], aphoto.inputs['B'])
nt.links.new(aphoto.outputs['Result'], dark.inputs['A'])
dark.inputs['Factor'].default_value = 1.0
comb = nt.nodes.new('ShaderNodeCombineColor'); [nt.links.new(rub.outputs[0], comb.inputs[k]) for k in range(3)]
nt.links.new(comb.outputs[0], dark.inputs['B'])
# белые линии: |u-0.5| > 0.475
line_m = nt.nodes.new('ShaderNodeMath'); line_m.operation = 'GREATER_THAN'; line_m.inputs[1].default_value = 0.474
nt.links.new(dist.outputs[0], line_m.inputs[0])
wear = nt.nodes.new('ShaderNodeMath'); wear.operation = 'MULTIPLY'
nt.links.new(line_m.outputs[0], wear.inputs[0]); nt.links.new(big.outputs['Fac'], wear.inputs[1])
wear2 = nt.nodes.new('ShaderNodeMath'); wear2.operation = 'MULTIPLY_ADD'; wear2.inputs[1].default_value = 0.6
nt.links.new(line_m.outputs[0], wear2.inputs[0]); nt.links.new(wear.outputs[0], wear2.inputs[2])
wclamp = nt.nodes.new('ShaderNodeClamp'); nt.links.new(wear2.outputs[0], wclamp.inputs[0])
col_mix = nt.nodes.new('ShaderNodeMix'); col_mix.data_type = 'RGBA'
nt.links.new(wclamp.outputs[0], col_mix.inputs['Factor']); nt.links.new(dark.outputs['Result'], col_mix.inputs['A'])
col_mix.inputs['B'].default_value = (0.75, 0.75, 0.73, 1)
nt.links.new(col_mix.outputs['Result'], b.inputs['Base Color'])
rr = nt.nodes.new('ShaderNodeMapRange'); nt.links.new(atex['rough'].outputs['Color'], rr.inputs['Value'])
rr.inputs['To Min'].default_value = 0.55; rr.inputs['To Max'].default_value = 0.95
nt.links.new(rr.outputs[0], b.inputs['Roughness'])
anm = nt.nodes.new('ShaderNodeNormalMap'); anm.inputs['Strength'].default_value = 0.8
nt.links.new(atex['nor'].outputs['Color'], anm.inputs['Color'])
bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.2; bump.inputs['Distance'].default_value = 0.004
nt.links.new(grain.outputs['Distance'], bump.inputs['Height']); nt.links.new(anm.outputs['Normal'], bump.inputs['Normal'])
nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])

# бордюры: красно-белые полосы по 2 м
kerb, nt, b = nodes_mat('kerb')
uvn = nt.nodes.new('ShaderNodeUVMap'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(uvn.outputs['UV'], sep.inputs[0])
dv = nt.nodes.new('ShaderNodeMath'); dv.operation = 'MULTIPLY'; dv.inputs[1].default_value = 0.5
nt.links.new(sep.outputs['Y'], dv.inputs[0])
fr = nt.nodes.new('ShaderNodeMath'); fr.operation = 'FRACT'; nt.links.new(dv.outputs[0], fr.inputs[0])
st = nt.nodes.new('ShaderNodeMath'); st.operation = 'GREATER_THAN'; st.inputs[1].default_value = 0.5; nt.links.new(fr.outputs[0], st.inputs[0])
km = nt.nodes.new('ShaderNodeMix'); km.data_type = 'RGBA'; nt.links.new(st.outputs[0], km.inputs['Factor'])
km.inputs['A'].default_value = (0.55, 0.035, 0.03, 1); km.inputs['B'].default_value = (0.78, 0.78, 0.76, 1)
nt.links.new(km.outputs['Result'], b.inputs['Base Color'])
b.inputs['Roughness'].default_value = 0.45

white, _, b = nodes_mat('paint_white'); b.inputs['Base Color'].default_value = (0.78, 0.78, 0.76, 1); b.inputs['Roughness'].default_value = 0.5
sys.path.insert(0, HERE)
import bcn_env  # noqa: E402
runoff = bcn_env.pbr('runoff', 'asphalt_02', 3.0, tint=(0.85, 0.85, 0.8, 1), rough_mul=1.1)[0]
metal, _, b = nodes_mat('gantry'); b.inputs['Base Color'].default_value = (0.08, 0.085, 0.09, 1); b.inputs['Roughness'].default_value = 0.35; b.inputs['Metallic'].default_value = 0.8
gravel = bcn_env.pbr('gravel', 'gravel', 2.0, tint=(1.0, 0.92, 0.8, 1), bump=1.2)[0]
grass = bcn_env.pbr('grass', 'aerial_grass_rock', 10.0, tint=(0.85, 0.9, 0.75, 1))[0]
stand_concrete = bcn_env.pbr('stand_concrete', 'concrete', 2.5)[0]

# дорога, обочины, бордюры
ribbon('road', -ROAD_W / 2, ROAD_W / 2, 10, 0.0, asph)
curve = np.abs(KAPPA) > 1 / 170.0
mask = np.zeros(NPT, bool)
for i in np.nonzero(curve)[0]:
    for k in range(-25, 26):
        mask[(i + k) % NPT] = True
ribbon('kerb_L', ROAD_W / 2, ROAD_W / 2 + KERB_W, 2, 0.03, kerb, mask)
ribbon('kerb_R', -ROAD_W / 2 - KERB_W, -ROAD_W / 2, 2, 0.03, kerb, mask)
ribbon('runoff_L', ROAD_W / 2, ROAD_W / 2 + 9, 3, -0.02, runoff, None, 2)
ribbon('runoff_R', -ROAD_W / 2 - 9, -ROAD_W / 2, 3, -0.02, runoff, None, 2)
# гравийные ловушки за бордюрами на поворотах
ribbon('gravel_L', ROAD_W / 2 + KERB_W + 3, ROAD_W / 2 + KERB_W + 16, 3, 0.01, gravel, mask, 2)
ribbon('gravel_R', -ROAD_W / 2 - KERB_W - 16, -ROAD_W / 2 - KERB_W - 3, 3, 0.01, gravel, mask, 2)

# линия старта и клетка поула
p0, d0, l0, _ = at(0.0)


def flat_quad(name, center, fwd, left, half_len, half_w, z=0.012, mat=white):
    c = np.array(center)
    vs = [c + fwd * a + left * b_ + np.array([0, 0, z]) for a, b_ in ((-half_len, -half_w), (half_len, -half_w), (half_len, half_w), (-half_len, half_w))]
    return mesh_obj(name, vs, [(0, 1, 2, 3)], None, mat)


flat_quad('start_line', p0, d0, l0, 0.3, ROAD_W / 2)
pb, db, lb, _ = at(-CAR_BACK)
pole_c = pb + lb * 0.0
flat_quad('grid_front', pole_c + db * 3.2, db, lb, 0.08, 1.2)
flat_quad('grid_side_L', pole_c + db * 2.7 + lb * 1.2, db, lb, 0.6, 0.06)
flat_quad('grid_side_R', pole_c + db * 2.7 - lb * 1.2, db, lb, 0.6, 0.06)

# стартовые огни: портал над линией, 5 секций по 2 красные лампы, светят назад на стартовую решётку
gz = 5.8
for side in (-1, 1):
    base = p0 + l0 * side * (ROAD_W / 2 + 2.2)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(base[0], base[1], base[2] + gz / 2))
    post = bpy.context.object; post.scale = (0.35, 0.35, gz); post.data.materials.append(metal); post.name = 'gantry_post'
bpy.ops.mesh.primitive_cube_add(size=1, location=(p0[0], p0[1], p0[2] + gz))
beam = bpy.context.object; beam.scale = (0.5, ROAD_W + 4.8, 0.45); beam.data.materials.append(metal); beam.name = 'gantry_beam'
beam.rotation_euler = (0, 0, math.atan2(d0[1], d0[0]))
panel_c = p0 + np.array([0, 0, gz - 0.95]) - d0 * 0.3
bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(panel_c))
panel = bpy.context.object; panel.scale = (0.35, 3.6, 1.2); panel.rotation_euler = beam.rotation_euler; panel.data.materials.append(metal); panel.name = 'lights_panel'
lamp_mats = []
for k in range(5):
    m, nt, bb = nodes_mat(f'lamp_{k}')
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (1.0, 0.02, 0.01, 1)
    mixs = nt.nodes.new('ShaderNodeMixShader'); out = nt.nodes['Material Output']
    nt.links.new(bb.outputs['BSDF'], mixs.inputs[1]); nt.links.new(em.outputs['Emission'], mixs.inputs[2])
    nt.links.new(mixs.outputs['Shader'], out.inputs['Surface'])
    bb.inputs['Base Color'].default_value = (0.08, 0.01, 0.01, 1); bb.inputs['Roughness'].default_value = 0.2
    em.inputs['Strength'].default_value = 0.0
    mixs.inputs['Fac'].default_value = 1.0
    lamp_mats.append(em)
    for row in (0.28, -0.28):
        off = (k - 2) * 0.7
        c = panel_c + l0 * off + np.array([0, 0, row]) - d0 * 0.19
        bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=0.05, location=tuple(c))
        lamp = bpy.context.object
        lamp.rotation_euler = (0, math.pi / 2, math.atan2(d0[1], d0[0]))
        lamp.data.materials.append(m); lamp.name = f'lamp_{k}'
for k, em in enumerate(lamp_mats):
    # огонь k горит с T_LIGHTS[k] до T_GO; ключи только в моменты переключения, переход ступенькой
    for f, val in ((0, 0.0), (round(T_LIGHTS[k] * FPS), 60.0), (round(T_GO * FPS), 0.0)):
        em.inputs['Strength'].default_value = val * 0.25
        em.inputs['Strength'].keyframe_insert('default_value', frame=f)
    act = em.id_data.animation_data.action
    for fc in act.fcurve_ensure_for_datablock(em.id_data, em.inputs['Strength'].path_from_id('default_value')).keyframe_points:
        fc.interpolation = 'CONSTANT'

# земля с рельефом (низкое качество — так и задумано)
terr = T['terrain']
lon0, lat0 = float(T['lon0']), float(T['lat0'])
R_E = 6378137.0
xmin, ymin = P2.min(0) - 400; xmax, ymax = P2.max(0) + 400
res = 12.0
gx = np.arange(xmin, xmax, res); gy = np.arange(ymin, ymax, res)
GX, GY = np.meshgrid(gx, gy)
lon = lon0 + np.degrees(GX / (R_E * math.cos(math.radians(lat0)))); lat = lat0 + np.degrees(GY / R_E)
# та же формула, что в track_build.load_terrain
sys.path.insert(0, HERE)
import track_build  # noqa: E402
hfun, _ = track_build.load_terrain()
hraw = hfun(lon, lat)
hstart = float(hfun(np.array([lon0]), np.array([lat0]))[0])
# дорога ниже/выше рельефа → землю у трассы подгоняем к дороге
flat = GX.ravel(); flatY = GY.ravel()
near_d = np.full(flat.shape, 1e9); near_z = np.zeros(flat.shape)
for s0 in range(0, NPT, 400):
    seg = P3[s0:s0 + 400]
    dd = (flat[:, None] - seg[None, :, 0]) ** 2 + (flatY[:, None] - seg[None, :, 1]) ** 2
    k = dd.argmin(1); m_ = dd[np.arange(len(k)), k]
    better = m_ < near_d
    near_d[better] = m_[better]; near_z[better] = seg[k[better], 2]
near_d = np.sqrt(near_d).reshape(GX.shape); near_z = near_z.reshape(GX.shape)
zt = hraw - hstart + (Z[0] - 0)
w = np.clip((near_d - (ROAD_W / 2 + 30)) / 45, 0, 1); w = w * w * (3 - 2 * w)   # под ограждениями и трибунами земля ровная
zt = (near_z - 0.25) * (1 - w) + zt * w
ny, nx = zt.shape
verts = np.column_stack([GX.ravel(), GY.ravel(), zt.ravel()])
faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
mesh_obj('terrain', verts, faces, None, grass)

# лёгкая облачность: панорама неба даёт фон, мягкий свет и отражения (солнце за облаками, отдельной лампы нет)
bcn_env.world_hdri(sc, strength=1.0, rotation=math.radians(HDRI_ROT))

# окружение: ограждения, трибуны, деревья
env_col = bpy.data.collections.new('environment'); sc.collection.children.link(env_col)
nb, nf, nt_ = bcn_env.barriers(at, L, DS, mask, ROAD_W, env_col)
seat_colors = [(0.02, 0.18, 0.11, 1), (0.6, 0.6, 0.58, 1), (0.03, 0.08, 0.25, 1), (0.45, 0.04, 0.03, 1), (0.55, 0.42, 0.05, 1)]
bcn_env.recolor_random(bcn_env.lib_collection('plastic_monobloc_chair_01'), seat_colors)
ns = bcn_env.grandstand('stand_main', at, -330.0, 330.0, 1, ROAD_W, stand_concrete, metal, env_col, rows=18)
ns += bcn_env.grandstand('stand_t1', at, 640.0, 860.0, 1, ROAD_W, stand_concrete, metal, env_col, rows=14)
ns += bcn_env.grandstand('stand_final', at, L - 560.0, L - 360.0, 1, ROAD_W, stand_concrete, metal, env_col, rows=14)
_zi = lambda x, y: np.array([zt[int(np.clip((yy - gy[0]) / res, 0, ny - 1)), int(np.clip((xx - gx[0]) / res, 0, nx - 1))] for xx, yy in zip(x, y)])
_ni = lambda x, y: np.array([near_d[int(np.clip((yy - gy[0]) / res, 0, ny - 1)), int(np.clip((xx - gx[0]) / res, 0, nx - 1))] for xx, yy in zip(x, y)])
ntr = bcn_env.trees(P2, _zi, _ni, xmin + 50, xmax - 50, ymin + 50, ymax - 50, env_col)
print(f'окружение: отбойников {nb}, звеньев сетки {nf}, шин {nt_}, мест на трибунах {ns}, деревьев {ntr}', flush=True)

# ---------- машина ----------
car_setup.CAR_LEN = 5.61
root, parts = car_setup.import_car(os.path.join(ROOT, '..', 'real-f1', 'model', 'amr24.glb'))
car_setup.fix_materials(root.children_recursive)
# лак краски: под облачным небом отражение мягкое; база чуть матовее, чтобы цвет оставался зелёным
for m in {sl.material for o in root.children_recursive if o.type == 'MESH' for sl in o.material_slots if sl.material}:
    bb = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bb and bb.inputs['Coat Weight'].default_value > 0.9:
        bb.inputs['Coat Weight'].default_value = COAT
        bb.inputs['Coat Roughness'].default_value = 0.06
        bb.inputs['Roughness'].default_value = 0.35
    elif bb and 'carbon' in m.name.lower():   # карбон: тёмный полуглянец, без серебристого отблеска неба
        bb.inputs['Coat Weight'].default_value = 0.25
        bb.inputs['Roughness'].default_value = 0.5


def bake(obj, path, size, rows):
    if obj.animation_data is None:
        obj.animation_data_create()
    act = obj.animation_data.action or bpy.data.actions.new(obj.name + '_anim')
    obj.animation_data.action = act
    for k in range(size):
        fc = act.fcurve_ensure_for_datablock(obj, path, index=k)
        fc.keyframe_points.add(len(rows))
        fc.keyframe_points.foreach_set('co', [c for i, r in enumerate(rows) for c in (i, r[k])])
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()


times = [f / FPS for f in range(N)]
S = [dist_at(t) for t in times]
E = [explode(t) for t in times]
V = np.gradient(np.array(S), 1 / FPS)                    # скорость, м/с
ACC = smooth_time(np.gradient(V, 1 / FPS), 4)             # продольное ускорение, м/с²
car_loc, yaw_, pitch_, kap_ = [], [], [], []
for t, s in zip(times, S):
    p, d, left, kap = at(s)
    h, sl = frame_at(s)
    car_loc.append(tuple(p)); yaw_.append(h); pitch_.append(-sl); kap_.append(kap)
kap_ = smooth_time(kap_, 3)
lat = V ** 2 * kap_                                       # боковое ускорение (+ влево)
roll = smooth_time(np.clip(0.0032 * lat, -0.035, 0.035), 5)          # крен наружу поворота, до 2°
dive = smooth_time(np.clip(-0.0011 * ACC, -0.012, 0.03), 5)          # клевок носом при торможении
car_rot = [(roll[f], pitch_[f] + dive[f], yaw_[f]) for f in range(N)]
steer = [math.atan(3.6 * kap_[f]) * (1.0 if times[f] >= T_GO else 0.0) for f in range(N)]
bake(root, 'location', 3, car_loc)
bake(root, 'rotation_euler', 3, car_rot)
np.savez(os.path.join(ROOT, 'build', 'motion.npz'), t=np.array(times), s=np.array(S), v=V, acc=ACC, lat=lat, explode=np.array(E))

# колёса: угол качения = путь / радиус (+ раскрутка при разборе)
spin_ex = np.cumsum([9 * e / FPS for e in E])
rng = np.random.RandomState(77245)
for name, info in parts.items():
    holder, spin = info['holder'], info['spin']
    axis = mathutils.Vector(rng.rand(3) - 0.5).normalized()
    amp = 0.35 if name.startswith('wheel') else 0.22 + rng.rand() * 0.12
    phase = rng.rand() * math.pi * 2
    locs, rots = [], []
    for f, (t, e) in enumerate(zip(times, E)):
        bob = math.sin(t * 1.9 + phase) * 0.35 * e * CAR_SCALE
        p = info['center'] + info['dir'] * info['dist'] * CAR_SCALE * e + mathutils.Vector((0, 0, (2.2 * CAR_SCALE) * e + bob))
        wob = e * amp * (0.75 + 0.25 * math.sin(t * 1.3 + phase))
        q = mathutils.Quaternion(axis, wob)
        if name in ('wheelFL', 'wheelFR'):
            q = mathutils.Quaternion((0, 0, 1), steer[f]) @ q
        locs.append(tuple(p)); rots.append(tuple(q.to_euler()))
    holder.rotation_mode = 'XYZ'
    bake(holder, 'location', 3, locs)
    bake(holder, 'rotation_euler', 3, rots)
    if name.startswith('wheel'):
        r = info['radius']
        bake(spin, 'rotation_euler', 3, [(0, (S[f] + CAR_BACK) / r + spin_ex[f], 0) for f in range(N)])
        side = 1 if info['center'].y > 0 else -1
        order = {'TYRE_': 0, 'wheel_': 1, 'disc_': 2, 'tether_': 3}
        for o, rel in info['members']:
            layer = next((v for k, v in order.items() if o.name.startswith(k)), 1)
            bake(o, 'location', 3, [(0, side * (layer - 1.2) * 0.9 * CAR_SCALE * e, 0) for e in E])
    else:
        for o, rel in info['members']:
            j = mathutils.Vector(rng.rand(3) - 0.5)
            bake(o, 'location', 3, [tuple(rel * info['spread'] * e + j * 0.9 * CAR_SCALE * e) for e in E])

# ---------- камера ----------
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); col.objects.link(cam); sc.camera = cam
cam.data.lens = 26; cam.data.clip_start = 0.1; cam.data.clip_end = 4000
cam.data.sensor_fit = 'HORIZONTAL'
raw_pos, raw_tgt = [], []
for t, s in zip(times, S):
    p, d, left, _ = at(s)
    h, _ = frame_at(s)
    # старт: камера сбоку у машины; пока детали висят, плавно облетает назад (90° → 180° от носа)
    ang = math.radians(90 + 90 * smooth((t - 2.6) / 4.0))
    r = 7.6 + 2.0 * smooth((t - 1.8) / 1.4) - 2.4 * smooth((t - 5.2) / 1.6)
    hgt = 1.15 + 0.5 * smooth((t - 1.8) / 1.4) + 0.4 * smooth((t - 5.2) / 1.6)
    c = p + np.array([0, 0, 0.75])
    a_pos = c + r * np.array([math.cos(h + ang), math.sin(h + ang), 0.0]) + np.array([0, 0, hgt - 0.75])
    a_tgt = c + d * (5.5 * smooth((t - 4.5) / 2.5)) + np.array([0, 0, 0.25 * smooth((t - 4.5) / 2.5)])
    # гонка: позади машины по трассе, чуть выше
    pc, _, _, _ = at(s - 7.2)
    pt, _, _, _ = at(s + 14.0)
    b_pos = pc + np.array([0, 0, 2.05])
    b_tgt = pt + np.array([0, 0, 0.9])
    k = smooth((t - (T_GO - 0.4)) / 0.9)
    raw_pos.append(a_pos * (1 - k) + b_pos * k)
    raw_tgt.append(a_tgt * (1 - k) + b_tgt * k)
cpos = smooth_time(raw_pos, 4)
ctgt = smooth_time(raw_tgt, 6)
cam_loc, cam_rot = [], []
for f in range(N):
    cam_loc.append(tuple(cpos[f]))
    cam_rot.append(mathutils.Vector(ctgt[f] - cpos[f]).to_track_quat('-Z', 'Y').to_euler())
for i in range(1, N):  # без скачков угла
    for k in range(3):
        a, b_ = cam_rot[i - 1][k], cam_rot[i][k]
        while b_ - a > math.pi: b_ -= 2 * math.pi
        while b_ - a < -math.pi: b_ += 2 * math.pi
        cam_rot[i][k] = b_
bake(cam, 'location', 3, cam_loc)
bake(cam, 'rotation_euler', 3, [tuple(r) for r in cam_rot])

# ---------- рендер ----------
r = sc.render
r.engine = 'CYCLES'
cy = sc.cycles
cy.device = 'CPU'
cy.samples = args.samples
cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.05
cy.use_denoising = True; cy.denoiser = 'OPENIMAGEDENOISE'
cy.max_bounces = 5
cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 2, 2, 1, 6
cy.blur_glossy = 0.6
r.use_motion_blur = True; r.motion_blur_shutter = 0.3
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, args.scale
r.image_settings.file_format = 'PNG'; r.image_settings.color_depth = '8'
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'
sc.view_settings.exposure = 0.9
r.use_persistent_data = True
if args.save_blend:
    bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)

out = os.path.join(ROOT, 'build', 'frames')
os.makedirs(out, exist_ok=True)
frames = [int(x) for x in args.frames.split(',')] if args.frames else list(range(N))
print(f'кадров в ролике: {N} ({N / FPS:.1f} с); круг {LAP:.2f} с', flush=True)
t0 = time.time()
for i, f in enumerate(frames):
    r.filepath = os.path.join(out, f'{f:04d}.png')
    if not args.frames and os.path.exists(r.filepath):
        continue
    sc.frame_set(f)
    ts = time.time()
    bpy.ops.render.render(write_still=True)
    print(f'кадр {f} ({i + 1}/{len(frames)}) за {time.time() - ts:.1f} с, всего {(time.time() - t0) / 60:.1f} мин', flush=True)
