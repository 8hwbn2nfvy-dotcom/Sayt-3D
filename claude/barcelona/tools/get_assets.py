"""Скачивает ресурсы окружения и голос (их нет в репозитории: ~500 МБ, lib.blend > 100 МБ).

Poly Haven (CC0): небо kloppenheim_07_puresky (4K HDR + 1K EXR), текстуры 2K (asphalt_02, aerial_grass_rock, gravel,
concrete, sparse_grass), модели glTF 1K (деревья, кусты, отбойник, сетка, шина, стул).
Piper (голос en_US-joe-medium, датасет CC0) с Hugging Face rhasspy/piper-voices.
Затем: python tools/build_assets.py (lib.blend) и python tools/clean_sky.py (небо без точек).
Запуск: python3 tools/get_assets.py
"""
import json
import os
import subprocess

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
UA = 'lego-f1-render/1.0'


def api(i):
    return json.loads(subprocess.run(['curl', '-s', '-A', UA, f'https://api.polyhaven.com/files/{i}'], capture_output=True, text=True, check=True).stdout)


def get(url, out):
    out = os.path.join(A, out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not os.path.exists(out):
        subprocess.run(['curl', '-sL', '-A', UA, '-o', out, url], check=True)


f = api('kloppenheim_07_puresky')
get(f['hdri']['4k']['hdr']['url'], 'hdri/kloppenheim_07_puresky_4k.hdr')
get(f['hdri']['1k']['exr']['url'], 'hdri/kloppenheim_07_puresky_1k.exr')
for t in ('asphalt_02', 'aerial_grass_rock', 'gravel', 'concrete', 'sparse_grass'):
    f = api(t)
    for k, key in (('Diffuse', 'diff'), ('nor_gl', 'nor'), ('Rough', 'rough'), ('Displacement', 'disp')):
        if k in f and '2k' in f[k]:
            get(f[k]['2k']['jpg']['url'], f'tex/{t}/{t}_{key}_2k.jpg')
for m in ('island_tree_01', 'island_tree_02', 'tree_small_02', 'searsia_lucida', 'shrub_01', 'shrub_03',
          'concrete_road_barrier', 'modular_chainlink_fence', 'old_tyre', 'plastic_monobloc_chair_01'):
    g = api(m)['gltf']['1k']['gltf']
    get(g['url'], f'models/{m}/{m}_1k.gltf')
    for rel, inc in g.get('include', {}).items():
        get(inc['url'], f'models/{m}/{rel}')
hf = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/'
for n in ('en_US-joe-medium.onnx', 'en_US-joe-medium.onnx.json', 'MODEL_CARD'):
    get(hf + n, f'voice/{n}')
print('готово')
