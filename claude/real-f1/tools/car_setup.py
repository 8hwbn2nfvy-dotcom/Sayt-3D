"""Загрузка модели AMR24 в Blender и подготовка к ролику (используется из render_real.py).

- Масштаб: машина вытягивается до длины CAR_LEN единиц сцены (1 единица = 1 шип Лего,
  такой же масштаб, как у Лего-ролика: трасса, камера, коробка и таймлайн подходят без переделок).
- Нос смотрит в +X, колёса стоят на земле (z = 0).
- Детали собираются в части для разбора (как у Лего): у каждой части свой пустой объект-«держатель»,
  у каждого колеса — «ось», вокруг которой оно крутится.
"""
import math
import re

import bpy
import mathutils

CAR_LEN = 28.0  # длина машины в единицах сцены (Лего-машинка была ≈28 шипов)

# Части для разбора: имя → (признак в имени объекта, направление разлёта в осях Blender: x вперёд, y влево, z вверх)
# Порядок важен: первое совпадение выигрывает.
PARTS = [
    ('wheelFL', r'(_fl\b|_fl_|_LF_|_lf_)', (0.35, 1, 0.35)),
    ('wheelFR', r'(_fr\b|_fr_|_RF_|_rf_)', (0.35, -1, 0.35)),
    ('wheelRL', r'(_bl\b|_bl_|_LR_|_lr_)', (-0.35, 1, 0.35)),
    ('wheelRR', r'(_br\b|_br_|_RR_|_rr_)', (-0.35, -1, 0.35)),
    ('frontWing', r'^(frontwing|frontflap|frontspoiler)', (1, 0, 0.15)),
    ('nose', r'^nosecone', (1, 0, 0.7)),
    ('rearWing', r'^(rearwing|Rain_Lights)', (-1, 0, 0.45)),
    ('cockpit', r'^(hal|windscreen|steering|cockpit|driver_surroun|MIRROR|wing_mirror|LED_|am_wheel|mix_dial|tyre_dial|LOD_A_INT)', (0.3, 0, 1)),
    ('sidepodL', r'^sidepod_fl', (0, 1, 0.4)),
    ('sidepodR', r'^sidepod_fr', (0, -1, 0.4)),
    ('engineCover', r'^topcanopy', (-0.3, 0, 1)),
    ('floor', r'^(floor_damage|diffuser)', (0, 0, -0.15)),
    ('body', r'.', (0, 0, 1)),
]
DIST = {'wheelFL': 8, 'wheelFR': 8, 'wheelRL': 8, 'wheelRR': 8, 'frontWing': 7, 'nose': 6, 'rearWing': 7,
        'cockpit': 5.5, 'sidepodL': 6, 'sidepodR': 6, 'engineCover': 6, 'floor': 1.5, 'body': 2.5}
SPREAD = {'body': 0.35, 'cockpit': 0.35, 'engineCover': 0.3, 'floor': 0.2}  # насколько расходятся детали внутри части


def wheel_key(name):
    """Колёсные детали: шина, диск, тормоз. Подвеска (suspension) остаётся с кузовом."""
    return re.search(r'^(wheel_|disc_|TYRE_|tether_)', name) is not None


def part_of(name):
    for part, pat, _ in PARTS:
        if part.startswith('wheel'):
            if wheel_key(name) and re.search(pat, name):
                return part
            continue
        if re.search(pat, name):
            return part
    return 'body'


def bbox(objs):
    bpy.context.view_layer.update()  # bound_box кэшируется: без обновления после правки вершин он старый
    mn = mathutils.Vector((1e9,) * 3); mx = -mn
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
    return mn, mx


def import_car(path):
    """Импорт, нормализация и разбиение на части. Возвращает (car_root, parts), parts[имя] = dict."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    # снимаем иерархию Sketchfab, сохраняя положение, и «запекаем» трансформации в сетки
    for o in meshes:
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
        if o.data.users > 1:
            o.data = o.data.copy()  # своя копия сетки, иначе общая растянется дважды
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    mn, mx = bbox(meshes)
    size = mx - mn
    length_axis = max(range(3), key=lambda i: size[i])
    s = CAR_LEN / size[length_axis]
    # нос там, где переднее крыло
    fw = [o for o in meshes if o.name.startswith('frontwing')]
    fmn, fmx = bbox(fw)
    front_sign = 1 if (fmn[length_axis] + fmx[length_axis]) / 2 > (mn[length_axis] + mx[length_axis]) / 2 else -1
    center = (mn + mx) / 2
    # поворот: ось длины со знаком «вперёд» → +X
    fwd = mathutils.Vector((0, 0, 0)); fwd[length_axis] = front_sign
    rot = fwd.rotation_difference(mathutils.Vector((1, 0, 0))).to_matrix().to_4x4()
    M = rot @ mathutils.Matrix.Scale(s, 4) @ mathutils.Matrix.Translation(-center)
    for o in meshes:
        o.data.transform(M @ o.matrix_world)
        o.matrix_world = mathutils.Matrix.Identity(4)
    mn, mx = bbox(meshes)
    for o in meshes:
        o.data.transform(mathutils.Matrix.Translation((0, 0, -mn.z)))
    mn, mx = bbox(meshes)
    print(f'машина: масштаб ×{s:.1f}, размер {tuple(round(v, 2) for v in (mx - mn))}')

    # наклейки decal_all_* лежат на разных частях: отдаём каждую части с ближайшей деталью
    def centre(o):
        return sum((o.matrix_world @ mathutils.Vector(v) for v in o.bound_box), mathutils.Vector()) / 8
    bpy.context.view_layer.update()
    assign = {o.name: part_of(o.name) for o in meshes if not o.name.startswith('decal_all')}
    solid = [(centre(o), assign[o.name]) for o in meshes if o.name in assign]
    for o in meshes:
        if o.name.startswith('decal_all'):
            c = centre(o)
            assign[o.name] = min(solid, key=lambda sc: (sc[0] - c).length)[1]

    root = bpy.data.objects.new('car_root', None)
    bpy.context.scene.collection.objects.link(root)
    parts = {}
    for part, _, d in PARTS:
        members = [o for o in meshes if assign[o.name] == part]
        if not members:
            continue
        pmn, pmx = bbox(members)
        c = (pmn + pmx) / 2
        if part.startswith('wheel'):
            tyres = [o for o in members if o.name.startswith('TYRE_')] or members
            tmn, tmx = bbox(tyres)
            c = (tmn + tmx) / 2
        holder = bpy.data.objects.new('part_' + part, None)
        bpy.context.scene.collection.objects.link(holder)
        holder.parent = root
        holder.location = c
        spin = bpy.data.objects.new('spin_' + part, None)
        bpy.context.scene.collection.objects.link(spin)
        spin.parent = holder
        info = {'holder': holder, 'spin': spin, 'center': c.copy(), 'dir': mathutils.Vector(d).normalized(),
                'dist': DIST[part], 'spread': SPREAD.get(part, 0.25), 'members': []}
        for o in members:
            oc = sum((mathutils.Vector(v) for v in o.bound_box), mathutils.Vector()) / 8
            o.data.transform(mathutils.Matrix.Translation(-c))  # деталь относительно держателя
            o.parent = spin
            info['members'].append((o, oc - c))
        if part.startswith('wheel'):
            info['radius'] = (tmx.z - tmn.z) / 2
        parts[part] = info
        print(f'  {part:12s} деталей {len(members):3d}  центр {tuple(round(v, 2) for v in c)}')
    return root, parts


def image_has_alpha(im):
    """True, если у текстуры есть реально прозрачные места (проверяем каждый 97-й пиксель)."""
    if im is None or im.channels < 4:
        return False
    px = im.pixels[:]
    return any(px[i] < 0.98 for i in range(3, len(px), 4 * 97))


def fix_materials(objs):
    """Материалы из файла: только цвет и матовая поверхность. Подключаем прозрачность и задаём лак/карбон/резину.
    Трогаем только материалы деталей машины objs (трасса и коробка настраиваются отдельно)."""
    alpha_cache = {}
    mats = {s.material for o in objs if o.type == 'MESH' for s in o.material_slots if s.material}
    for m in mats:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not b:
            continue
        tex = b.inputs['Base Color'].links[0].from_node if b.inputs['Base Color'].is_linked else None
        im = getattr(tex, 'image', None)
        if im is not None:
            if im.name not in alpha_cache:
                alpha_cache[im.name] = image_has_alpha(im)
            if alpha_cache[im.name] and not b.inputs['Alpha'].is_linked:
                nt.links.new(tex.outputs['Alpha'], b.inputs['Alpha'])
        n = m.name.lower()

        def setv(k, v):
            if k in b.inputs:
                b.inputs[k].default_value = v
        if 'tire' in n or 'tyre' in n:
            setv('Roughness', 0.62); setv('Specular IOR Level', 0.3)
        elif 'carbon' in n:
            setv('Roughness', 0.38); setv('Coat Weight', 0.6); setv('Coat Roughness', 0.12)
        elif 'glass' in n or 'lcd' in n:
            setv('Roughness', 0.05); setv('Transmission Weight', 0.9)
        elif 'metal' in n or 'disc' in n or 'mirror' in n:
            setv('Roughness', 0.25); setv('Metallic', 0.9)
        elif 'light' in n:
            setv('Roughness', 0.3)
        else:  # краска, наклейки, детали ливреи: лак
            setv('Roughness', 0.32); setv('Coat Weight', 1.0); setv('Coat Roughness', 0.04)
    print('прозрачность подключена у текстур:', sorted(k for k, v in alpha_cache.items() if v))
