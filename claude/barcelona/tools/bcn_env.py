"""Окружение трассы для bcn_scene.py: материалы на фототекстурах, небо, ограждения, трибуны, деревья.

Ресурсы — Poly Haven (CC0): assets/hdri, assets/tex (2k), assets/lib.blend (модели, собирает build_assets.py).
Множество одинаковых объектов (отбойники, забор, шины, стулья, деревья) ставится копиями-«инстансами»
через Geometry Nodes: точки с атрибутами rot/scl → Instance on Points. Память почти не растёт.
Единицы — метры; x восток, y север, z вверх.
"""
import math
import os

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, '..', 'assets')


# ---------- материалы ----------
def _img(path, color=True):
    im = bpy.data.images.load(path, check_existing=True)
    if not color:
        im.colorspace_settings.name = 'Non-Color'
    return im


def pbr(name, tex, scale, coords='Object', tint=None, rough_mul=1.0, bump=1.0):
    """Материал по набору фототекстур tex (diff/nor/rough). scale — размер плитки в метрах.
    coords: 'Object' (по положению в мире; для земли и трибун) или 'UV' (для лент вдоль трассы: v — метры)."""
    d = os.path.join(A, 'tex', tex)
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / scale, 1 / scale, 1 / scale)
    nt.links.new(tc.outputs['Object' if coords == 'Object' else 'UV'], mp.inputs['Vector'])
    out = {}
    for key, color in (('diff', True), ('nor', False), ('rough', False)):
        f = [x for x in os.listdir(d) if f'_{key}_' in x]
        if not f:
            continue
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = _img(os.path.join(d, f[0]), color)
        nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
        out[key] = t
    col = out['diff'].outputs['Color']
    if tint is not None:
        mul = nt.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs['Factor'].default_value = 1
        nt.links.new(col, mul.inputs['A']); mul.inputs['B'].default_value = tint
        col = mul.outputs['Result']
    nt.links.new(col, b.inputs['Base Color'])
    if 'rough' in out:
        rm = nt.nodes.new('ShaderNodeMath'); rm.operation = 'MULTIPLY'; rm.inputs[1].default_value = rough_mul
        nt.links.new(out['rough'].outputs['Color'], rm.inputs[0]); nt.links.new(rm.outputs[0], b.inputs['Roughness'])
    if 'nor' in out:
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = bump
        nt.links.new(out['nor'].outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    m['_color_socket'] = col.node.name + ':' + col.name
    return m, nt, b, col


def world_hdri(sc, strength=1.0, rotation=0.0):
    """Облачное небо (Poly Haven kloppenheim_07_puresky): и фон, и весь свет, и отражения."""
    w = bpy.data.worlds.new('overcast'); sc.world = w; w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(os.path.join(A, 'hdri', 'kloppenheim_07_puresky_4k.hdr'))
    tc = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value = (0, 0, rotation)
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], env.inputs['Vector'])
    # камера видит небо из уменьшенной панорамы 1K (одиночные яркие пиксели 4K похожи на звёзды) с обрезкой ярких мест;
    # свет и отражения — от полной 4K
    env_cam = nt.nodes.new('ShaderNodeTexEnvironment')
    env_cam.image = bpy.data.images.load(os.path.join(A, 'hdri', 'kloppenheim_07_puresky_1k_clean.exr'))   # без ярких точек (tools/clean_sky.py)
    nt.links.new(mp.outputs['Vector'], env_cam.inputs['Vector'])
    cl = nt.nodes.new('ShaderNodeVectorMath'); cl.operation = 'MINIMUM'; cl.inputs[1].default_value = (1.6, 1.6, 1.6)
    nt.links.new(env_cam.outputs['Color'], cl.inputs[0])
    lp = nt.nodes.new('ShaderNodeLightPath')
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs['Factor'])
    nt.links.new(env.outputs['Color'], mx.inputs['A']); nt.links.new(cl.outputs['Vector'], mx.inputs['B'])
    nt.links.new(mx.outputs['Result'], nt.nodes['Background'].inputs['Color'])
    nt.nodes['Background'].inputs['Strength'].default_value = strength


# ---------- инстансы ----------
_lib_loaded = False


def lib_collection(name):
    global _lib_loaded
    if not _lib_loaded:
        with bpy.data.libraries.load(os.path.join(A, 'lib.blend'), link=False) as (src, dst):
            dst.collections = list(src.collections)
        _lib_loaded = True
    return bpy.data.collections[name]


def coll_height(name):
    c = lib_collection(name)
    zs = [v.co.z for o in c.objects if o.type == 'MESH' for v in o.data.vertices]
    return max(zs) if zs else 1.0


def instancer(name, coll, pts, rots, scales, parent_col):
    """Объект-облако точек; Geometry Nodes ставит на каждую точку копию коллекции coll с поворотом rot и масштабом scl."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, p)) for p in pts], [], [])
    ra = me.attributes.new('rot', 'FLOAT_VECTOR', 'POINT'); ra.data.foreach_set('vector', np.asarray(rots, np.float32).ravel())
    sa = me.attributes.new('scl', 'FLOAT_VECTOR', 'POINT'); sa.data.foreach_set('vector', np.asarray(scales, np.float32).ravel())
    ob = bpy.data.objects.new(name, me); parent_col.objects.link(ob)
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = ng.nodes.new('NodeGroupInput'); go = ng.nodes.new('NodeGroupOutput')
    ci = ng.nodes.new('GeometryNodeCollectionInfo'); ci.inputs['Collection'].default_value = coll
    iop = ng.nodes.new('GeometryNodeInstanceOnPoints')
    r = ng.nodes.new('GeometryNodeInputNamedAttribute'); r.data_type = 'FLOAT_VECTOR'; r.inputs['Name'].default_value = 'rot'
    s = ng.nodes.new('GeometryNodeInputNamedAttribute'); s.data_type = 'FLOAT_VECTOR'; s.inputs['Name'].default_value = 'scl'
    ng.links.new(gi.outputs[0], iop.inputs['Points'])
    ng.links.new(ci.outputs['Instances'], iop.inputs['Instance'])
    ng.links.new(r.outputs['Attribute'], iop.inputs['Rotation'])
    ng.links.new(s.outputs['Attribute'], iop.inputs['Scale'])
    ng.links.new(iop.outputs['Instances'], go.inputs[0])
    mod = ob.modifiers.new('inst', 'NODES'); mod.node_group = ng
    return ob


def recolor_random(coll, colors):
    """Каждой копии — свой цвет из списка (Object Info → Random), например разноцветные стулья трибун."""
    for o in coll.objects:
        for sl in o.material_slots:
            m = sl.material
            if not m or m.get('_recolored'):
                continue
            nt = m.node_tree; b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
            oi = nt.nodes.new('ShaderNodeObjectInfo')
            ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.color_ramp.interpolation = 'CONSTANT'
            el = ramp.color_ramp.elements
            for i, c in enumerate(colors):
                if i < len(el):
                    el[i].position = i / len(colors); el[i].color = c
                else:
                    e = el.new(i / len(colors)); e.color = c
            nt.links.new(oi.outputs['Random'], ramp.inputs['Fac'])
            nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
            m['_recolored'] = True


# ---------- ограждения ----------
def along(at, s0, s1, step, offset, zoff=0.0):
    """Точки вдоль трассы от s0 до s1 с шагом step на боковом смещении offset (м, + влево); поворот по ходу трассы."""
    pts, rots = [], []
    s = s0
    while s < s1:
        p, d, left, _ = at(s)
        q = p + left * offset
        pts.append((q[0], q[1], q[2] + zoff)); rots.append((0.0, 0.0, math.atan2(d[1], d[0])))
        s += step
    return pts, rots


def runs(mask, ds):
    """Непрерывные отрезки (s0, s1) по маске точек трассы (маска по кругу)."""
    n = len(mask); out = []; i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i * ds, j * ds)); i = j
        else:
            i += 1
    return out


def _part_collection(name, src_obj, shift):
    """Коллекция из одной детали набора (например, секция сетки), сдвинутой так, чтобы её начало было в 0."""
    c = bpy.data.collections.new(name)
    o = bpy.data.objects[src_obj].copy(); o.data = o.data.copy()
    o.data.transform(__import__('mathutils').Matrix.Translation(shift))
    c.objects.link(o)
    return c


def barriers(at, L, ds, corner_mask, road_w, col):
    """Бетонные отбойники вдоль всей трассы (на прямых ближе, в поворотах — за гравием), сетка над ними,
    шинные стены перед отбойниками в поворотах. Модели Poly Haven: длинная сторона отбойника — ось X."""
    bar = lib_collection('concrete_road_barrier'); tyre = lib_collection('old_tyre')
    lib_collection('modular_chainlink_fence')                       # загрузить набор деталей сетки
    panel = _part_collection('fence_panel', 'modular_chainlink_fence', (2.495, 0.0, 0.0))   # секция 0.93 м, центр в 0
    post = _part_collection('fence_post', 'modular_chainlink_fence_post', (1.0, -1.005, 0.0))
    near = road_w / 2 + 11.0
    far = road_w / 2 + 20.0

    def off_at(s, side):
        i = int(s / ds) % len(corner_mask)
        return side * (far if corner_mask[i] else near), corner_mask[i]

    pts, rots, fpts, frots, ppts, prots, tpts, trots = [], [], [], [], [], [], [], []
    for side in (1, -1):
        for step, kind in ((1.55, 'bar'), (0.93, 'panel'), (2.79, 'post'), (0.62, 'tyre')):
            s = 0.0
            while s < L:
                off, corner = off_at(s, side)
                p, d, left, _ = at(s)
                yaw = math.atan2(d[1], d[0])
                if kind == 'bar':
                    q = p + left * off
                    pts.append((q[0], q[1], q[2] - 0.05)); rots.append((0.0, 0.0, yaw))
                elif kind in ('panel', 'post'):
                    q = p + left * (off + side * 0.45)
                    (fpts if kind == 'panel' else ppts).append((q[0], q[1], q[2] + 0.75))
                    (frots if kind == 'panel' else prots).append((0.0, 0.0, yaw))
                elif corner:                                        # шинная стена: 2 ряда × 3 яруса
                    for row in (0, 1):
                        q = p + left * (off - side * (0.75 + row * 0.62))
                        for lvl in range(3):
                            tpts.append((q[0], q[1], q[2] + lvl * 0.16)); trots.append((math.pi / 2, 0.0, yaw))
                s += step
    instancer('barriers', bar, pts, rots, [(1, 1, 1)] * len(pts), col)
    instancer('fence', panel, fpts, frots, [(1, 1, 1)] * len(fpts), col)
    instancer('fence_posts', post, ppts, prots, [(1, 1, 1)] * len(ppts), col)
    instancer('tyres', tyre, tpts, trots, [(1, 1, 1)] * len(tpts), col)
    return len(pts), len(fpts), len(tpts)


# ---------- трибуны ----------
def grandstand(name, at, s0, s1, side, road_w, concrete, metal, col, rows=16):
    """Ступенчатая бетонная трибуна вдоль трассы с рядами разноцветных стульев и навесом."""
    chair = lib_collection('plastic_monobloc_chair_01')
    start = road_w / 2 + 24.0
    step_d, step_h = 0.85, 0.42
    verts, faces = [], []
    cpts, crots = [], []
    ss = np.arange(s0, s1, 2.0)
    prof = []
    for r in range(rows + 1):                                   # профиль ступенек: (смещение, высота)
        prof += [(start + r * step_d, r * step_h), (start + r * step_d, (r + 1) * step_h)]
    prof += [(start + (rows + 1) * step_d, (rows + 1) * step_h), (start + (rows + 1) * step_d, 0.0), (start, 0.0)]
    np_ = len(prof)
    for k, s in enumerate(ss):
        p, d, left, _ = at(s)
        for off, h in prof:
            q = p + left * side * off
            verts.append((q[0], q[1], q[2] + h - 0.3))
        if k:
            a0 = (k - 1) * np_; a1 = k * np_
            for j in range(np_):
                j2 = (j + 1) % np_
                faces.append((a0 + j, a0 + j2, a1 + j2, a1 + j) if side > 0 else (a0 + j, a1 + j, a1 + j2, a0 + j2))
        # стулья на каждой ступеньке через 0.55 м
        if k < len(ss) - 1:
            yaw = math.atan2(d[1], d[0]) + (math.pi / 2 if side > 0 else -math.pi / 2) + math.pi
            for r in range(rows):
                for t in (0.0, 0.55, 1.1, 1.65):
                    pp, dd, ll, _ = at(s + t)
                    q = pp + ll * side * (start + r * step_d + 0.45)
                    cpts.append((q[0], q[1], q[2] + (r + 1) * step_h - 0.3)); crots.append((0.0, 0.0, yaw))
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    ob = bpy.data.objects.new(name, me); col.objects.link(ob); ob.data.materials.append(concrete)
    instancer(name + '_seats', chair, cpts, crots, [(1, 1, 1)] * len(cpts), col)
    # навес: тонкая плита над верхними рядами + колонны
    rverts, rfaces = [], []
    for k, s in enumerate(ss):
        p, d, left, _ = at(s)
        for off in (start + rows * step_d * 0.35, start + (rows + 2) * step_d):
            q = p + left * side * off
            rverts.append((q[0], q[1], q[2] + (rows + 1) * step_h + 4.2))
        if k:
            a0 = (k - 1) * 2; a1 = k * 2
            rfaces.append((a0, a0 + 1, a1 + 1, a1))
    rm = bpy.data.meshes.new(name + '_roof'); rm.from_pydata(rverts, [], rfaces); rm.update()
    ro = bpy.data.objects.new(name + '_roof', rm); col.objects.link(ro); ro.data.materials.append(metal)
    sol = ro.modifiers.new('t', 'SOLIDIFY'); sol.thickness = 0.35
    for s in np.arange(s0 + 3, s1, 18.0):
        p, d, left, _ = at(s)
        q = p + left * side * (start + (rows + 1.5) * step_d)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=(rows + 1) * step_h + 4.5, location=(q[0], q[1], q[2] + ((rows + 1) * step_h + 4.5) / 2 - 0.3))
        c = bpy.context.object; c.data.materials.append(metal)
        for cc in list(c.users_collection):
            cc.objects.unlink(c)
        col.objects.link(c)
    return len(cpts)


# ---------- деревья ----------
def trees(P2, zt_fn, near_fn, xmin, xmax, ymin, ymax, col, n=3200, seed=7):
    """Деревья и кусты по рельефу: не ближе 30 м к трассе (за ограждениями) и не дальше 420 м."""
    rng = np.random.RandomState(seed)
    kinds = [('island_tree_01', 0.30, (8, 13)), ('island_tree_02', 0.25, (6, 10)), ('tree_small_02', 0.25, (6, 11)),
             ('searsia_lucida', 0.12, (3, 5)), ('shrub_01', 0.08, (1.2, 2.2))]
    xs = rng.uniform(xmin, xmax, n * 4); ys = rng.uniform(ymin, ymax, n * 4)
    dn = near_fn(xs, ys)
    keep = (dn > 30) & (dn < 420)
    xs, ys = xs[keep][:n], ys[keep][:n]
    zs = zt_fn(xs, ys)
    probs = np.array([k[1] for k in kinds]); probs /= probs.sum()
    pick = rng.choice(len(kinds), size=len(xs), p=probs)
    total = 0
    for ki, (cid, _, (h0, h1)) in enumerate(kinds):
        sel = pick == ki
        if not sel.any():
            continue
        h = coll_height(cid)
        sc_ = rng.uniform(h0, h1, sel.sum()) / h
        pts = np.column_stack([xs[sel], ys[sel], zs[sel] - 0.1])
        rots = np.column_stack([np.zeros(sel.sum()), np.zeros(sel.sum()), rng.uniform(0, 2 * math.pi, sel.sum())])
        instancer('trees_' + cid, lib_collection(cid), pts, rots, np.column_stack([sc_, sc_, sc_]), col)
        total += sel.sum()
    return total
