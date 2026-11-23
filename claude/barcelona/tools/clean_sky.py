"""Убирает из панорамы неба 1K одиночные яркие точки (похожи на звёзды) → *_1k_clean.exr (её видит камера, bcn_env.world_hdri).
Точка = пиксель ярче медианы соседей 5×5 в 1.35 раза (+0.05); заменяется средним соседей.
Запуск: python tools/clean_sky.py   (Python с bpy)
"""
import os

import bpy
import numpy as np

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'hdri')
im = bpy.data.images.load(os.path.join(A, 'kloppenheim_07_puresky_1k.exr'))
w, h = im.size
a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
lum = a[..., :3].mean(-1)
sh = [(dy, dx) for dy in range(-2, 3) for dx in range(-2, 3) if (dy, dx) != (0, 0)]
pad = np.pad(lum, 2, mode='edge')
med = np.median(np.stack([pad[2 + dy:2 + dy + h, 2 + dx:2 + dx + w] for dy, dx in sh]), 0)
mask = lum > med * 1.35 + 0.05
padc = np.pad(a[..., :3], ((2, 2), (2, 2), (0, 0)), mode='edge')
avg = np.mean([padc[2 + dy:2 + dy + h, 2 + dx:2 + dx + w] for dy, dx in sh], 0)
a[..., :3][mask] = avg[mask]
out = bpy.data.images.new('clean', w, h, float_buffer=True)
out.pixels[:] = a.ravel()
out.filepath_raw = os.path.join(A, 'kloppenheim_07_puresky_1k_clean.exr'); out.file_format = 'OPEN_EXR'; out.save()
print('убрано точек:', int(mask.sum()))
